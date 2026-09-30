"""Ventas (sesión 06): el carrito es una `Venta` persistida en estado
`en_curso`. `_recalcular` es el ÚNICO lugar donde se calculan los importes de
una venta (precio vivo, descuentos, promoción, pagos y totales); confirmar y
anular mueven stock solo vía `services.stock.aplicar_movimiento`.

Orden de locks: primero la fila de la venta (`bloquear_venta`) y después, al
confirmar/anular, cada producto en orden de producto_id ascendente (lo hace
`aplicar_movimiento`). Nunca al revés, para no cruzarse en un deadlock."""
import secrets
from collections import Counter
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import lazyload

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import ahora_db, filtro_texto, paginar, rango_fechas
from app.models import EstadoVenta, TipoMovimientoStock, Usuario, Venta, VentaItem, VentaPago
from app.schemas.ventas import MONTO_MAXIMO, ProductoVenta, VentaResponse
from app.services import categorias as servicio_categorias
from app.services import clientes as servicio_clientes
from app.services import medios_pago as servicio_medios
from app.services import turnos as servicio_turnos
from app.services.descuentos import aplicar_descuentos, resolver_porcentaje, validar_tope
from app.services.productos import buscar_por_codigo, obtener_producto
from app.services.promociones import mejor_promocion, promociones_aplicables, simular
from app.services.stock import aplicar_movimiento

MAX_MEDIOS_DE_PAGO = 2
ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # A-Z0-9 sin I, O, 0, 1
LARGO_CODIGO = 4
INTENTOS_CODIGO = 20
TAMANO_MAXIMO = 100
CANTIDAD_MAXIMA = 999   # por pedido: tope de sanidad (el tope real es el stock)


# --- Lectura y locks ------------------------------------------------------------

def obtener_venta(db, venta_id: int) -> Venta:
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise NoEncontrado("Venta no encontrada")
    return venta


def bloquear_venta(db, venta_id: int) -> Venta:
    """`SELECT ... FOR UPDATE` de la fila de la venta POR ID (sin relaciones:
    cliente, promoción y anulada_por van con LEFT OUTER JOIN y Postgres no
    permite bloquear ese lado) y relectura con `populate_existing`."""
    db.execute(select(Venta.id).where(Venta.id == venta_id).with_for_update())
    venta = db.get(Venta, venta_id, populate_existing=True)
    if venta is None:
        raise NoEncontrado("Venta no encontrada")
    return venta


def venta_en_curso(db, usuario) -> Venta | None:
    return db.scalar(select(Venta).where(Venta.usuario_id == usuario.id, Venta.estado == EstadoVenta.EN_CURSO))


def _venta_propia_en_curso(db, autor, venta_id: int) -> Venta:
    """Toda operación sobre el carrito empieza acá: el lock evita que dos
    pestañas del mismo usuario pisen el mismo carrito."""
    venta = bloquear_venta(db, venta_id)
    if venta.estado is not EstadoVenta.EN_CURSO:
        raise ReglaDeNegocio("La venta ya no está en curso")
    if venta.usuario_id != autor.id:
        raise SinPermiso("Solo quien inició la venta puede operarla")
    return venta


def _item_de(venta: Venta, item_id: int) -> VentaItem:
    item = next((i for i in venta.items if i.id == item_id), None)
    if item is None:
        raise NoEncontrado("Ítem no encontrado en esta venta")
    return item


def _clave_linea(item: VentaItem) -> tuple:
    """Unidades del mismo producto con el mismo descuento = una línea del carrito."""
    return (item.producto_id, item.descuento_item, item.motivo_descuento_id)


def lineas(venta: Venta) -> list[list[VentaItem]]:
    """Unidades agrupadas en líneas, en el orden de su primera unidad."""
    grupos: dict[tuple, list[VentaItem]] = {}
    for item in sorted(venta.items, key=lambda i: i.orden):
        grupos.setdefault(_clave_linea(item), []).append(item)
    return list(grupos.values())


def _turno_para_operar(db, autor, ip) -> int:
    """Turno de caja en el que se cobra/anula: el abierto de HOY (409 si no
    hay o si quedó abierto uno de un día anterior). Suma a quien opera."""
    return servicio_turnos.turno_para_operar(db, autor, ip).id


# --- Núcleo: recálculo ------------------------------------------------------------

def _habilita_sin_interes(venta: Venta) -> bool:
    """Algún ítem con un motivo de descuento que habilita cuotas sin interés
    aunque el monto no llegue al mínimo del plan."""
    return any(i.motivo_descuento and i.motivo_descuento.habilita_cuotas_sin_interes for i in venta.items)


def _medio_ids(venta: Venta) -> set[int]:
    return {p.medio_de_pago_id for p in venta.pagos}


def _elegibles(venta: Venta) -> list[VentaItem]:
    """Ítems que pueden entrar en una promoción: los que no tienen descuento manual."""
    return [i for i in venta.items if not i.descuento_item]


def _normalizar_pagos(db, venta: Venta, cobrable: Decimal, *, estricto: bool) -> bool:
    """Decisión 5: con 1 pago su monto es lo cobrable; con 2, el segundo es el
    resto. Recalcula el recargo de cada uno. Si algo deja de valer: estricto →
    400 con el motivo; si no → borra los pagos. Devuelve False si los borró."""
    if not venta.pagos:
        return True
    problema = None
    if cobrable <= 0:
        problema = "No hay nada para cobrar"
    else:
        montos = [cobrable] if len(venta.pagos) == 1 else [venta.pagos[0].monto, cobrable - venta.pagos[0].monto]
        if montos[-1] <= 0:
            problema = "El primer pago ya cubre todo: sacá el segundo medio de pago"
        habilita = _habilita_sin_interes(venta)
        for pago, monto in zip(venta.pagos, montos):
            if problema:
                break
            medio, plan = pago.medio_de_pago, pago.plan_cuotas
            if not medio.activo:
                problema = f"El medio de pago '{medio.nombre}' está inactivo"
            elif plan is not None and plan not in servicio_medios.planes_disponibles(medio, monto, habilita):
                problema = f"El plan de {plan.cuotas} cuotas no está disponible para {monto}"
            else:
                pago.monto = monto
                pago.recargo = servicio_medios.calcular_recargo(monto, plan)
                pago.monto_total = monto + pago.recargo
    if problema is None:
        return True
    if estricto:
        raise DatoInvalido(problema)
    venta.pagos.clear()
    return False


def _recalcular(db, venta: Venta, *, estricto: bool = False) -> None:
    """ÚNICO lugar donde se calculan los importes de una venta en curso."""
    # 1. Precio vivo: relee cada producto (decisión 3) y recalcula sin
    #    promociones. precio_unitario queda como base "sin promo" que usa
    #    promociones.simular: por eso se resetea ANTES de elegir la promoción.
    for item in venta.items:
        producto = item.producto
        item.precio_lista = producto.precio_venta
        item.costo_unitario = producto.costo_en_pesos
        item.precio_unitario = aplicar_descuentos(producto.precio_venta, producto.descuento_producto,
                                                  Decimal("0"))
        item.en_promocion = False
        item.precio_final = (aplicar_descuentos(producto.precio_venta, producto.descuento_producto,
                                                item.descuento_item)
                             if item.descuento_item else item.precio_unitario)
    # 2. Promoción: la manual si sigue aplicando; si no, la de mayor ahorro.
    elegibles = _elegibles(venta)
    aplicables = promociones_aplicables(db, venta.cliente_id, ahora_db().date(), _medio_ids(venta))
    if venta.promocion_a_mano and (venta.promocion_id is None or any(p.id == venta.promocion_id for p in aplicables)):
        promo = next((p for p in aplicables if p.id == venta.promocion_id), None)
    else:
        venta.promocion_a_mano = False
        promo = mejor_promocion(db, aplicables, elegibles)
    venta.promocion_id = promo.id if promo else None
    venta.promocion = promo
    if promo:
        _, finales, en_promo = simular(db, promo, elegibles)
        for item in elegibles:
            if item.id in en_promo:
                item.precio_final, item.en_promocion = finales[item.id], True
    # 3. Totales sin recargo.
    venta.subtotal = sum((i.precio_lista for i in venta.items), Decimal("0"))
    cobrable = sum((i.precio_final for i in venta.items), Decimal("0"))
    venta.descuento_total = venta.subtotal - cobrable
    # 4. Pagos: se normalizan (decisión 5) y se recalcula su recargo. Si se
    #    borraron, la promoción elegida pudo depender de esos medios de pago
    #    (alcance medio_de_pago): se recalcula una vez más ya sin pagos.
    if not _normalizar_pagos(db, venta, cobrable, estricto=estricto):
        return _recalcular(db, venta)
    venta.recargo_total = sum((p.recargo for p in venta.pagos), Decimal("0"))
    venta.total = cobrable + venta.recargo_total
    if venta.subtotal > MONTO_MAXIMO or venta.total > MONTO_MAXIMO:
        raise DatoInvalido("La venta supera el importe máximo permitido")
    db.flush()


# --- Flujo del carrito ------------------------------------------------------------

def iniciar_venta(db, autor, ip) -> Venta:
    """Devuelve la venta en curso del autor o abre una nueva. Ante dos POST
    simultáneos, el UNIQUE parcial uq_ventas_en_curso_usuario hace fallar al
    segundo (IntegrityError → 409 en el handler global)."""
    existente = venta_en_curso(db, autor)
    if existente is not None:
        return existente
    numero = f"V-{db.scalar(select(func.nextval('ventas_numero_seq'))):06d}"
    venta = Venta(usuario_id=autor.id, numero=numero)
    db.add(venta)
    db.flush()
    db.refresh(venta)
    registrar_auditoria(db, accion="venta.iniciar", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_nuevo={"numero": venta.numero}, ip_origen=ip)
    return venta


def _validar_cantidad(cantidad: int, *, permite_cero: bool) -> None:
    minimo = 0 if permite_cero else 1
    if not isinstance(cantidad, int) or not minimo <= cantidad <= CANTIDAD_MAXIMA:
        raise DatoInvalido(f"La cantidad tiene que estar entre {minimo} y {CANTIDAD_MAXIMA}")


def _validar_stock(venta: Venta, producto, agregar: int) -> None:
    """Decisión del usuario: la venta nunca supera el stock (stock infinito: sin tope)."""
    if producto.stock_infinito:
        return
    cargadas = sum(1 for i in venta.items if i.producto_id == producto.id)
    if cargadas + agregar > producto.stock:
        if producto.stock <= 0:
            raise ReglaDeNegocio(f"No hay stock de '{producto.descripcion}'.")
        raise ReglaDeNegocio(f"Solo quedan {producto.stock} unidades de '{producto.descripcion}'.")


def _nueva_unidad(venta: Venta, producto, *, descuento=Decimal("0"), motivo=None, modificado=False) -> VentaItem:
    orden = max((i.orden for i in venta.items), default=0) + 1
    # Los precios los completa _recalcular; acá solo para no violar NOT NULL.
    item = VentaItem(
        producto_id=producto.id, producto=producto, orden=orden,
        precio_lista=producto.precio_venta, precio_unitario=producto.precio_venta,
        precio_final=producto.precio_venta, costo_unitario=producto.costo_en_pesos,
        descuento_item=descuento, motivo_descuento_id=motivo.id if motivo else None, motivo_descuento=motivo,
        porcentaje_modificado=modificado, en_promocion=False,
    )
    venta.items.append(item)
    return item


def _carrito_cambio(venta: Venta) -> None:
    """Cambió el carrito: la promoción elegida a mano deja de valer (se elige
    la mejor de nuevo). La Task 2 suma acá el reset del descuento general."""
    venta.promocion_a_mano = False


def agregar_item(db, autor, venta_id: int, *, codigo: str | None = None, producto_id: int | None = None,
                 cantidad: int = 1, ip=None) -> Venta:
    """Agrega `cantidad` unidades sin descuento (caen en la línea sin
    descuento del producto). 409 si superan el stock. Sin auditoría por ítem."""
    if (codigo is None) == (producto_id is None):
        raise DatoInvalido("Indicá el código o el producto (uno de los dos)")
    _validar_cantidad(cantidad, permite_cero=False)
    venta = _venta_propia_en_curso(db, autor, venta_id)
    producto = buscar_por_codigo(db, codigo) if codigo is not None else obtener_producto(db, producto_id)
    if not producto.activo:
        raise ReglaDeNegocio(f"'{producto.descripcion}' está inactivo")
    _validar_stock(venta, producto, cantidad)
    for _ in range(cantidad):
        _nueva_unidad(venta, producto)
    db.flush()   # los ítems necesitan id: promociones.simular indexa por item.id
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta


def cambiar_cantidad(db, autor, venta_id: int, item_id: int, cantidad: int, ip=None) -> Venta:
    """Fija la cantidad de la línea del ítem: sube con el mismo descuento de la
    línea, baja quitando las últimas unidades, 0 quita la línea."""
    _validar_cantidad(cantidad, permite_cero=True)
    venta = _venta_propia_en_curso(db, autor, venta_id)
    item = _item_de(venta, item_id)
    linea = [i for i in venta.items if _clave_linea(i) == _clave_linea(item)]
    diferencia = cantidad - len(linea)
    if diferencia > 0:
        _validar_stock(venta, item.producto, diferencia)
        for _ in range(diferencia):
            _nueva_unidad(venta, item.producto, descuento=item.descuento_item, motivo=item.motivo_descuento,
                          modificado=item.porcentaje_modificado)
    else:
        for sobrante in sorted(linea, key=lambda i: i.orden, reverse=True)[:-diferencia]:
            venta.items.remove(sobrante)
    db.flush()
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta


def quitar_item(db, autor, venta_id: int, item_id: int) -> Venta:
    venta = _venta_propia_en_curso(db, autor, venta_id)
    item = _item_de(venta, item_id)
    venta.items.remove(item)
    db.flush()
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta


def asociar_cliente(db, autor, venta_id: int, cliente_id: int | None) -> Venta:
    venta = _venta_propia_en_curso(db, autor, venta_id)
    cliente = None
    if cliente_id is not None:
        cliente = servicio_clientes.obtener_cliente(db, cliente_id)
        if not cliente.activo:
            raise ReglaDeNegocio(f"El cliente '{cliente.nombre}' está inactivo")
    # FK y relación: _recalcular lee cliente_id antes del flush y la
    # respuesta lee la relación.
    venta.cliente_id = cliente.id if cliente else None
    venta.cliente = cliente
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta


def aplicar_descuento_item(db, autor, venta_id: int, item_id: int, motivo_id: int | None, porcentaje,
                           ip) -> Venta:
    """El permiso `venta.descuento` lo chequea el router. Aplica a toda la
    línea del ítem (mismo producto y mismo descuento): las unidades que
    queden con el mismo descuento se vuelven a unir solas en una línea."""
    venta = _venta_propia_en_curso(db, autor, venta_id)
    item = _item_de(venta, item_id)
    linea = [i for i in venta.items if _clave_linea(i) == _clave_linea(item)]
    if any(i.en_promocion for i in linea):
        raise ReglaDeNegocio("Este producto está en una promoción: no admite otro descuento")
    motivo, valor, modificado = None, Decimal("0"), False
    if motivo_id is not None:
        motivo, valor, modificado = resolver_porcentaje(db, motivo_id, porcentaje)
        validar_tope(db, item.producto.descuento_producto, valor, item.producto.descripcion)
    antes = {"item_ids": [i.id for i in linea], "descuento_item": item.descuento_item,
             "motivo_descuento_id": item.motivo_descuento_id}
    for unidad in linea:
        unidad.descuento_item = valor
        unidad.motivo_descuento_id = motivo.id if motivo else None
        unidad.motivo_descuento = motivo
        unidad.porcentaje_modificado = modificado
    _carrito_cambio(venta)
    _recalcular(db, venta)
    registrar_auditoria(db, accion="venta.descuento", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_anterior=antes,
                        estado_nuevo={"item_ids": [i.id for i in linea], "descuento_item": valor,
                                      "motivo_descuento_id": motivo.id if motivo else None},
                        ip_origen=ip)
    return venta


def elegir_promocion(db, autor, venta_id: int, promocion_id: int | None) -> Venta:
    """`None` = "sin promoción" a mano. Dura hasta el próximo cambio del carrito."""
    venta = _venta_propia_en_curso(db, autor, venta_id)
    if promocion_id is not None:
        aplicables = promociones_aplicables(db, venta.cliente_id, ahora_db().date(), _medio_ids(venta))
        if not any(p.id == promocion_id for p in aplicables):
            raise ReglaDeNegocio("Esa promoción no aplica a esta venta")
    venta.promocion_id = promocion_id
    venta.promocion_a_mano = True
    _recalcular(db, venta)
    return venta


def _campo(pago, nombre: str):
    """Los pagos llegan como dicts o como PagoDatos (schema)."""
    return pago[nombre] if isinstance(pago, dict) else getattr(pago, nombre)


def registrar_pagos(db, autor, venta_id: int, pagos: list) -> Venta:
    """Reemplaza los pagos. El monto del único pago y el del segundo los fija
    el backend (decisión 5); solo cuenta el del primero de dos."""
    if len(pagos) > MAX_MEDIOS_DE_PAGO:
        raise DatoInvalido("Hasta 2 medios de pago")
    venta = _venta_propia_en_curso(db, autor, venta_id)
    nuevos = []
    for pago in pagos:
        medio = servicio_medios.obtener_medio(db, _campo(pago, "medio_de_pago_id"))
        if not medio.activo:
            raise ReglaDeNegocio(f"El medio de pago '{medio.nombre}' está inactivo")
        plan = None
        plan_id = _campo(pago, "plan_cuotas_id")
        if plan_id is not None:
            plan = servicio_medios.obtener_plan(db, plan_id)
            if plan.medio_de_pago_id != medio.id:
                raise DatoInvalido("El plan no corresponde a ese medio de pago")
            if not plan.activo:
                raise DatoInvalido("Ese plan de cuotas no está activo")
            if not medio.soporta_cuotas:
                raise DatoInvalido(f"'{medio.nombre}' no se cobra en cuotas")
        monto = Decimal(_campo(pago, "monto"))
        if monto <= 0:
            raise DatoInvalido("El monto del pago tiene que ser mayor a 0")
        nuevos.append(VentaPago(medio_de_pago_id=medio.id, medio_de_pago=medio, plan_cuotas_id=plan_id,
                                plan_cuotas=plan, monto=monto, recargo=Decimal("0"), monto_total=monto))
    venta.pagos.clear()
    venta.pagos.extend(nuevos)
    _recalcular(db, venta, estricto=True)
    return venta


def recalcular(db, autor, venta_id: int) -> Venta:
    """Relee precios (decisión 3): lo llama la pantalla tras un 409 de confirmar."""
    venta = _venta_propia_en_curso(db, autor, venta_id)
    _recalcular(db, venta)
    return venta


# --- Cierre: confirmar, descartar, anular ------------------------------------------

def _movimientos_por_producto(venta: Venta) -> list[tuple[int, int]]:
    """[(producto_id, unidades)] en orden de producto_id ascendente (evita deadlocks)."""
    return sorted(Counter(i.producto_id for i in venta.items).items())


def _generar_codigo(db) -> str:
    for _ in range(INTENTOS_CODIGO):
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))
        if db.scalar(select(Venta.id).where(Venta.codigo_cambio == codigo)) is None:
            return codigo
    raise ReglaDeNegocio("No se pudo generar el código de cambio: reintentá")


def confirmar_venta(db, autor, venta_id: int, total_esperado: Decimal, ip) -> Venta:
    venta = _venta_propia_en_curso(db, autor, venta_id)
    turno_id = _turno_para_operar(db, autor, ip)
    _recalcular(db, venta)
    if not venta.items:
        raise ReglaDeNegocio("La venta no tiene productos")
    if not venta.pagos or sum((p.monto for p in venta.pagos), Decimal("0")) != venta.cobrable:
        raise ReglaDeNegocio("Cargá los medios de pago para cubrir el total")
    if venta.total != total_esperado:
        raise ReglaDeNegocio("Los precios cambiaron mientras cargabas la venta: revisá el total y volvé a confirmar.")
    # Decisión del usuario: la venta nunca deja el stock en negativo. El
    # producto queda bloqueado (aplicar_movimiento) mientras se aplica el
    # movimiento: si otra venta se llevó stock en el medio, 409 acá.
    for producto_id, unidades in _movimientos_por_producto(venta):
        aplicar_movimiento(db, autor, tipo=TipoMovimientoStock.VENTA, producto_id=producto_id, cantidad=-unidades,
                           referencia_venta_id=venta.id, ip_origen=ip)
    venta.codigo_cambio = _generar_codigo(db)
    venta.confirmada_en = ahora_db()
    venta.turno_id = turno_id
    venta.estado = EstadoVenta.CONFIRMADA
    db.flush()
    nuevo = snapshot(venta)
    nuevo["items"] = [{"producto_id": i.producto_id, "precio_final": i.precio_final} for i in venta.items]
    nuevo["pagos"] = [{"medio_de_pago_id": p.medio_de_pago_id, "plan_cuotas_id": p.plan_cuotas_id,
                       "monto": p.monto, "recargo": p.recargo, "monto_total": p.monto_total} for p in venta.pagos]
    registrar_auditoria(db, accion="venta.confirmada", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_nuevo=nuevo, ip_origen=ip)
    return venta


def descartar_venta(db, autor, venta_id: int, ip) -> None:
    venta = _venta_propia_en_curso(db, autor, venta_id)
    registrar_auditoria(db, accion="venta.descartar", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_anterior={"numero": venta.numero, "subtotal": venta.subtotal,
                                         "items": len(venta.items)},
                        ip_origen=ip)
    db.delete(venta)
    db.flush()


def anular_venta(db, autor, venta_id: int, motivo: str, ip) -> Venta:
    """Anulación total. La puede hacer cualquiera con el permiso (no hace falta
    ser quien vendió). Los pagos NO se tocan: quedan como historia."""
    venta = bloquear_venta(db, venta_id)
    if venta.estado is EstadoVenta.EN_CURSO:
        raise ReglaDeNegocio("Una venta en curso se descarta, no se anula")
    if venta.estado is EstadoVenta.ANULADA:
        raise ReglaDeNegocio("La venta ya está anulada")
    motivo = (motivo or "").strip()
    if not 1 <= len(motivo) <= 500:
        raise DatoInvalido("El motivo de anulación es obligatorio (hasta 500 caracteres)")
    turno_id = _turno_para_operar(db, autor, ip)
    antes = snapshot(venta)
    for producto_id, unidades in _movimientos_por_producto(venta):
        aplicar_movimiento(db, autor, tipo=TipoMovimientoStock.ANULACION_VENTA, producto_id=producto_id,
                           cantidad=unidades, referencia_venta_id=venta.id, ip_origen=ip)
    venta.anulada_en = ahora_db()
    venta.anulada_por_id = autor.id
    venta.anulada_por = autor
    venta.motivo_anulacion = motivo
    venta.turno_anulacion_id = turno_id
    venta.estado = EstadoVenta.ANULADA
    db.flush()
    registrar_auditoria(db, accion="venta.anular", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_anterior=antes,
                        estado_nuevo={"estado": venta.estado, "anulada_en": venta.anulada_en,
                                      "anulada_por_id": venta.anulada_por_id,
                                      "motivo_anulacion": venta.motivo_anulacion,
                                      "turno_anulacion_id": venta.turno_anulacion_id},
                        ip_origen=ip)
    return venta


# --- Consultas para la pantalla ------------------------------------------------------

def medios_para_venta(db, venta: Venta, monto: Decimal | None) -> list[dict]:
    """[{medio, planes}]: medios activos (por nombre) con los planes que
    habilita `monto` (por defecto, lo cobrable de la venta)."""
    base = monto or venta.cobrable
    habilita = _habilita_sin_interes(venta)
    return [{"medio": m, "planes": servicio_medios.planes_disponibles(m, base, habilita)}
            for m in servicio_medios.listar_medios(db, activo=True)]


def promociones_para_venta(db, venta: Venta) -> list[dict]:
    """[{promocion, ahorro}] de las promociones aplicables. No toca la venta:
    simula sobre los elegibles (su precio_unitario ya es la base sin promo)."""
    elegibles = _elegibles(venta)
    return [{"promocion": p, "ahorro": simular(db, p, elegibles)[0]}
            for p in promociones_aplicables(db, venta.cliente_id, ahora_db().date(), _medio_ids(venta))]


def listar_ventas(db, *, cliente_id=None, usuario_id=None, estado=None, numero=None, codigo_cambio=None,
                  total_desde=None, total_hasta=None, fecha_desde=None, fecha_hasta=None,
                  pagina: int = 1, tamano: int = 10) -> tuple[list[Venta], int]:
    fecha = func.coalesce(Venta.confirmada_en, Venta.created_at)
    condiciones = []
    if cliente_id is not None:
        condiciones.append(Venta.cliente_id == cliente_id)
    if usuario_id is not None:
        condiciones.append(Venta.usuario_id == usuario_id)
    if estado is not None:
        condiciones.append(Venta.estado == estado)
    if numero and numero.strip():
        condiciones.append(filtro_texto(Venta.numero, numero))
    if codigo_cambio and codigo_cambio.strip():
        condiciones.append(Venta.codigo_cambio == codigo_cambio.strip().upper())
    if total_desde is not None:
        condiciones.append(Venta.total >= total_desde)
    if total_hasta is not None:
        condiciones.append(Venta.total <= total_hasta)
    condiciones.extend(rango_fechas(fecha, fecha_desde, fecha_hasta))
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Venta).where(*condiciones))
    # Cliente y usuario van joined y pagos selectin (lazy del modelo); los
    # ítems no hacen falta en el resumen.
    ventas = db.scalars(
        select(Venta).options(lazyload(Venta.items)).where(*condiciones)
        .order_by(fecha.desc(), Venta.id.desc()).offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(ventas), total


def vendedores(db) -> list[Usuario]:
    """Usuarios activos para el filtro "Vendedor" del resumen (decisión 11)."""
    return list(db.scalars(
        select(Usuario).where(Usuario.activo.is_(True)).order_by(func.lower(Usuario.nombre), Usuario.id)
    ).all())


# --- Respuestas ------------------------------------------------------------------------

def a_respuesta(db, venta: Venta) -> VentaResponse:
    return VentaResponse.desde(venta, servicio_categorias.caminos(db), lineas(venta))


def a_productos_venta(db, productos) -> list[ProductoVenta]:
    rutas = servicio_categorias.caminos(db)
    return [ProductoVenta.desde(p, rutas[p.categoria_id]) for p in productos]
