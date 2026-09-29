"""Promociones de ventas (sesión 06): 2x1, 3x2 y descuento por porcentaje.

`services.ventas._recalcular` (Task 4) consume exactamente `promociones_aplicables`,
`simular` y `mejor_promocion` con estas firmas: no cambiarlas sin avisar."""
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db, filtro_texto, nombre_libre, normalizar_texto
from app.models import (
    Categoria, Cliente, ClientePromocion, MedioDePago, PAGAS_POR_GRUPO, Producto, Promocion,
    PromocionAlcance, TAMANO_GRUPO, TipoAlcancePromocion, TipoPromocion,
)
from app.services import categorias as servicio_categorias
from app.services.descuentos import aplicar_descuentos

# Alcances que restringen a qué PRODUCTOS aplica la promo (a diferencia de
# MEDIO_DE_PAGO, que restringe el medio de pago, no el producto).
_ALCANCES_DE_PRODUCTOS = {
    TipoAlcancePromocion.PRODUCTO, TipoAlcancePromocion.CATEGORIA,
    TipoAlcancePromocion.TODOS_PRODUCTOS, TipoAlcancePromocion.TODOS_CATEGORIAS,
}
# Equivalentes entre sí (categoria_id de Producto es NOT NULL: "todas las
# categorías" y "todos los productos" alcanzan exactamente lo mismo).
_ALCANCES_TODOS = {TipoAlcancePromocion.TODOS_PRODUCTOS, TipoAlcancePromocion.TODOS_CATEGORIAS}


# --- Matemática de promociones de grupo (2x1 / 3x2) --------------------------

def unidades_gratis(cantidad: int, promo: Promocion) -> int:
    tamano = TAMANO_GRUPO[promo.tipo]
    return (cantidad // tamano) * (tamano - PAGAS_POR_GRUPO[promo.tipo])


def elegir_unidades_gratis(items, promo) -> tuple[set[int], set[int]]:
    """Grupos completos por precio DESC (orden de carga como desempate); en
    cada grupo quedan gratis las más baratas DEL GRUPO.
    Ej. 2x1 con [100, 90, 80, 70, 60] → grupos [100,90] [80,70] → gratis 90 y 70."""
    tamano = TAMANO_GRUPO[promo.tipo]
    gratis_por_grupo = tamano - PAGAS_POR_GRUPO[promo.tipo]
    ordenados = sorted(items, key=lambda i: (-i.precio_unitario, i.orden))
    completos = len(ordenados) // tamano * tamano
    en_grupo, gratis = set(), set()
    for inicio in range(0, completos, tamano):
        grupo = ordenados[inicio:inicio + tamano]
        en_grupo.update(i.id for i in grupo)
        gratis.update(i.id for i in grupo[-gratis_por_grupo:])
    return en_grupo, gratis


# --- Alcance (a qué productos y con qué medios de pago rige) -----------------

def productos_alcanzados(db, promo: Promocion) -> set[int] | None:
    """`None` = alcanza a todos los productos: ya sea porque la promo tiene un
    alcance TODOS_* o porque solo tiene alcance de medio de pago (sin ningún
    alcance de productos)."""
    alcances_producto = [a for a in promo.alcances if a.tipo_alcance in _ALCANCES_DE_PRODUCTOS]
    if not alcances_producto or any(a.tipo_alcance in _ALCANCES_TODOS for a in alcances_producto):
        return None
    ids: set[int] = set()
    for alcance in alcances_producto:
        if alcance.tipo_alcance is TipoAlcancePromocion.PRODUCTO:
            ids.add(alcance.referencia_id)
        else:   # CATEGORIA: la rama completa (incluye subcategorías)
            rama = servicio_categorias.rama_de_ids(db, alcance.referencia_id)
            ids.update(db.scalars(select(Producto.id).where(Producto.categoria_id.in_(rama))).all())
    return ids


def aplica_con_medios(promo, medio_ids: set[int]) -> bool:
    """Decisión de producto: rige solo si TODOS los pagos son de medios
    alcanzados. Sin pagos cargados (medio_ids vacío) no bloquea. Sin alcance de
    medio, o con referencia 0, rige con cualquiera."""
    medios = {a.referencia_id for a in promo.alcances if a.tipo_alcance is TipoAlcancePromocion.MEDIO_DE_PAGO}
    if not medios or 0 in medios or not medio_ids:
        return True
    return medio_ids <= medios


def _vigente_hoy_sql(dia: date):
    return and_(
        Promocion.activo.is_(True),
        or_(Promocion.fecha_inicio.is_(None), Promocion.fecha_inicio <= dia),
        or_(Promocion.fecha_fin.is_(None), dia <= Promocion.fecha_fin),
    )


def promociones_aplicables(db, cliente_id: int | None, dia: date, medio_ids: set[int]) -> list[Promocion]:
    """Activas, vigentes hoy, que rigen con los medios de pago cargados y, si
    son exclusivas de ciertos clientes (tienen filas en cliente_promociones),
    solo si `cliente_id` es uno de ellos (sin cliente → no se ofrecen)."""
    vigentes = list(db.scalars(select(Promocion).where(_vigente_hoy_sql(dia)).order_by(Promocion.id)).all())
    if not vigentes:
        return []
    ids = [p.id for p in vigentes]
    exclusivas = set(db.scalars(
        select(ClientePromocion.promocion_id).where(ClientePromocion.promocion_id.in_(ids)).distinct()
    ).all())
    permitidas_del_cliente: set[int] = set()
    if cliente_id is not None and exclusivas:
        permitidas_del_cliente = set(db.scalars(
            select(ClientePromocion.promocion_id).where(
                ClientePromocion.cliente_id == cliente_id, ClientePromocion.promocion_id.in_(exclusivas)
            )
        ).all())
    resultado = []
    for promo in vigentes:
        if promo.id in exclusivas and promo.id not in permitidas_del_cliente:
            continue
        if not aplica_con_medios(promo, medio_ids):
            continue
        resultado.append(promo)
    return resultado


# --- Simulación (cuánto ahorra cada promo sobre un carrito) ------------------

def simular(db, promo, items) -> tuple[Decimal, dict[int, Decimal], set[int]]:
    """(ahorro, precio_final_por_item_id, ids_en_promocion) sobre `items`
    (elegibles: sin descuento manual). No toca la base ni los items."""
    alcanzados = productos_alcanzados(db, promo)
    candidatos = [i for i in items if alcanzados is None or i.producto_id in alcanzados]
    finales: dict[int, Decimal] = {}
    en_promo: set[int] = set()
    if promo.tipo is TipoPromocion.PORCENTAJE:
        for i in candidatos:
            finales[i.id] = aplicar_descuentos(i.precio_lista, i.producto.descuento_producto,
                                               Decimal(promo.porcentaje_descuento))
            en_promo.add(i.id)
    else:
        en_grupo, gratis = elegir_unidades_gratis(candidatos, promo)
        for i in candidatos:
            if i.id in en_grupo:
                finales[i.id] = Decimal("0") if i.id in gratis else i.precio_unitario
                en_promo.add(i.id)
    ahorro = sum((i.precio_unitario - finales[i.id] for i in candidatos if i.id in finales), Decimal("0"))
    return ahorro, finales, en_promo


def mejor_promocion(db, candidatas, items) -> Promocion | None:
    """La de mayor ahorro; empate → menor id; `None` si ninguna ahorra > 0."""
    mejor, mejor_ahorro = None, Decimal("0")
    for promo in candidatas:
        ahorro, _, _ = simular(db, promo, items)
        if ahorro <= 0:
            continue
        if mejor is None or ahorro > mejor_ahorro or (ahorro == mejor_ahorro and promo.id < mejor.id):
            mejor, mejor_ahorro = promo, ahorro
    return mejor


# --- CRUD ---------------------------------------------------------------------

def obtener_promocion(db, promocion_id: int) -> Promocion:
    promo = db.get(Promocion, promocion_id)
    if promo is None:
        raise NoEncontrado("Promoción no encontrada")
    return promo


def listar_promociones(db, *, nombre: str | None = None, tipo: TipoPromocion | None = None,
                       rige_hoy: bool | None = None, activo: bool | None = None) -> list[Promocion]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(Promocion.nombre, nombre))
    if tipo is not None:
        condiciones.append(Promocion.tipo == tipo)
    if activo is not None:
        condiciones.append(Promocion.activo.is_(activo))
    if rige_hoy is not None:
        vigente = _vigente_hoy_sql(ahora_db().date())
        condiciones.append(vigente if rige_hoy else ~vigente)
    return list(db.scalars(
        select(Promocion).where(*condiciones).order_by(func.lower(Promocion.nombre))
    ).all())


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    return nombre_libre(db, Promocion, nombre, excepto_id=excepto_id,
                        mensaje_duplicado=lambda p: f"Ya existe la promoción '{p.nombre}'")


def _validar_fechas(fecha_inicio, fecha_fin) -> None:
    if fecha_inicio is not None and fecha_fin is not None and fecha_inicio > fecha_fin:
        raise DatoInvalido("La fecha de inicio no puede ser posterior a la fecha de fin")


def _validar_porcentaje_segun_tipo(tipo: TipoPromocion, porcentaje: int | None) -> None:
    if tipo is TipoPromocion.PORCENTAJE and porcentaje is None:
        raise DatoInvalido("El porcentaje de descuento es obligatorio en promociones de tipo porcentaje")
    if tipo is not TipoPromocion.PORCENTAJE and porcentaje is not None:
        raise DatoInvalido("El porcentaje de descuento solo aplica a promociones de tipo porcentaje")


def _validar_alcances(db, alcances_datos) -> list[tuple]:
    """Valida y normaliza `list[PromocionAlcanceDatos]` a `[(tipo_alcance,
    referencia_id), ...]`: al menos un alcance de productos, sin repetidos y
    cada referencia existente (0 vale sin chequeo para TODOS_*/MEDIO_DE_PAGO)."""
    if not any(a.tipo_alcance in _ALCANCES_DE_PRODUCTOS for a in alcances_datos):
        raise DatoInvalido("Elegí a qué productos alcanza")
    normalizados: list[tuple] = []
    vistos: set[tuple] = set()
    for alcance in alcances_datos:
        referencia_id = 0 if alcance.tipo_alcance in _ALCANCES_TODOS else alcance.referencia_id
        clave = (alcance.tipo_alcance, referencia_id)
        if clave in vistos:
            raise DatoInvalido("Hay alcances repetidos")
        vistos.add(clave)
        if alcance.tipo_alcance is TipoAlcancePromocion.PRODUCTO:
            if db.get(Producto, referencia_id) is None:
                raise NoEncontrado(f"No existe el producto {referencia_id}")
        elif alcance.tipo_alcance is TipoAlcancePromocion.CATEGORIA:
            if db.get(Categoria, referencia_id) is None:
                raise NoEncontrado(f"No existe la categoría {referencia_id}")
        elif alcance.tipo_alcance is TipoAlcancePromocion.MEDIO_DE_PAGO and referencia_id != 0:
            if db.get(MedioDePago, referencia_id) is None:
                raise NoEncontrado(f"No existe el medio de pago {referencia_id}")
        normalizados.append(clave)
    return normalizados


def _sincronizar_alcances(db, promo: Promocion, normalizados: list[tuple]) -> None:
    """Reemplaza los alcances de la promoción por los nuevos. La relación no
    tiene cascade delete-orphan (promocion_id es NOT NULL): cada alcance viejo
    se saca de la colección Y se borra explícitamente, y se flushea antes de
    insertar los nuevos para no chocar contra el UNIQUE si se repite alguno."""
    for alcance in list(promo.alcances):
        promo.alcances.remove(alcance)
        db.delete(alcance)
    db.flush()
    nuevos = [PromocionAlcance(tipo_alcance=tipo, referencia_id=referencia) for tipo, referencia in normalizados]
    promo.alcances.extend(nuevos)
    db.add_all(nuevos)
    db.flush()


def _snapshot_promocion(promo: Promocion) -> dict:
    """snapshot() de columnas + alcances (relación, no columna): la auditoría
    de promociones tiene que mostrar a qué quedó alcanzando cada alta/edición."""
    datos = snapshot(promo)
    datos["alcances"] = [{"tipo_alcance": a.tipo_alcance, "referencia_id": a.referencia_id} for a in promo.alcances]
    return datos


def crear_promocion(db, autor, datos, ip) -> Promocion:
    _validar_porcentaje_segun_tipo(datos.tipo, datos.porcentaje_descuento)
    _validar_fechas(datos.fecha_inicio, datos.fecha_fin)
    nombre = _nombre_libre(db, datos.nombre)
    normalizados = _validar_alcances(db, datos.alcances)
    promo = Promocion(
        nombre=nombre, nota=normalizar_texto(datos.nota), tipo=datos.tipo, activo=True,
        porcentaje_descuento=datos.porcentaje_descuento,
        fecha_inicio=datos.fecha_inicio, fecha_fin=datos.fecha_fin,
    )
    db.add(promo)
    db.flush()
    db.refresh(promo)
    _sincronizar_alcances(db, promo, normalizados)
    registrar_auditoria(db, accion="promocion.crear", entidad="promocion", entidad_id=promo.id,
                        usuario_id=autor.id, estado_nuevo=_snapshot_promocion(promo), ip_origen=ip)
    return promo


def editar_promocion(db, autor, promo: Promocion, datos, ip) -> Promocion:
    _validar_porcentaje_segun_tipo(datos.tipo, datos.porcentaje_descuento)
    _validar_fechas(datos.fecha_inicio, datos.fecha_fin)
    nombre = _nombre_libre(db, datos.nombre, excepto_id=promo.id)
    normalizados = _validar_alcances(db, datos.alcances)
    antes = _snapshot_promocion(promo)
    promo.nombre = nombre
    promo.nota = normalizar_texto(datos.nota)
    promo.tipo = datos.tipo
    promo.porcentaje_descuento = datos.porcentaje_descuento
    promo.fecha_inicio = datos.fecha_inicio
    promo.fecha_fin = datos.fecha_fin
    _sincronizar_alcances(db, promo, normalizados)
    db.flush()
    registrar_auditoria(db, accion="promocion.editar", entidad="promocion", entidad_id=promo.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=_snapshot_promocion(promo),
                        ip_origen=ip)
    return promo


def cambiar_estado_promocion(db, autor, promo: Promocion, activo: bool, ip) -> Promocion:
    if promo.activo is activo:
        return promo
    antes = _snapshot_promocion(promo)
    promo.activo = activo
    db.flush()
    registrar_auditoria(db, accion="promocion.activar" if activo else "promocion.desactivar",
                        entidad="promocion", entidad_id=promo.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=_snapshot_promocion(promo), ip_origen=ip)
    return promo


def catalogos(db) -> dict:
    """Catálogos para el formulario de promociones: productos y medios
    activos, y el camino completo de cada categoría (`categorias.caminos`)."""
    productos = db.scalars(
        select(Producto).where(Producto.activo.is_(True)).order_by(func.lower(Producto.descripcion))
    ).all()
    caminos = servicio_categorias.caminos(db)
    medios = db.scalars(
        select(MedioDePago).where(MedioDePago.activo.is_(True)).order_by(func.lower(MedioDePago.nombre))
    ).all()
    return {
        "productos": [{"id": p.id, "codigo": p.codigo_con_verificador, "descripcion": p.descripcion}
                     for p in productos],
        "categorias": [{"id": id_, "camino": camino}
                       for id_, camino in sorted(caminos.items(), key=lambda item: item[1].lower())],
        "medios": [{"id": m.id, "nombre": m.nombre} for m in medios],
    }


# --- Promociones exclusivas de un cliente ------------------------------------

def promociones_de_cliente(db, cliente_id: int) -> list[Promocion]:
    return list(db.scalars(
        select(Promocion).join(ClientePromocion, ClientePromocion.promocion_id == Promocion.id)
        .where(ClientePromocion.cliente_id == cliente_id)
        .order_by(func.lower(Promocion.nombre))
    ).all())


def asignar_a_cliente(db, autor, cliente: Cliente, promocion_id: int, ip) -> Promocion:
    promo = obtener_promocion(db, promocion_id)
    existente = db.scalar(select(ClientePromocion).where(
        ClientePromocion.cliente_id == cliente.id, ClientePromocion.promocion_id == promo.id
    ))
    if existente is not None:
        raise ReglaDeNegocio("El cliente ya tiene esa promoción")
    db.add(ClientePromocion(cliente_id=cliente.id, promocion_id=promo.id))
    db.flush()
    registrar_auditoria(db, accion="cliente.promocion_asignar", entidad="cliente", entidad_id=cliente.id,
                        usuario_id=autor.id, estado_nuevo={"promocion_id": promo.id, "promocion_nombre": promo.nombre},
                        ip_origen=ip)
    return promo


def quitar_de_cliente(db, autor, cliente: Cliente, promocion_id: int, ip) -> None:
    asignacion = db.scalar(select(ClientePromocion).where(
        ClientePromocion.cliente_id == cliente.id, ClientePromocion.promocion_id == promocion_id
    ))
    if asignacion is None:
        raise NoEncontrado("El cliente no tiene esa promoción")
    promo = obtener_promocion(db, promocion_id)
    db.delete(asignacion)
    db.flush()
    registrar_auditoria(db, accion="cliente.promocion_quitar", entidad="cliente", entidad_id=cliente.id,
                        usuario_id=autor.id,
                        estado_anterior={"promocion_id": promo.id, "promocion_nombre": promo.nombre}, ip_origen=ip)
