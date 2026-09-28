"""Auditorías de inventario (conteos): un conteo en curso a la vez, ítems
contados producto por producto y, al cerrar, un ajuste de stock
(`services.stock.aplicar_movimiento`) por cada diferencia distinta de cero.

El stock se sigue tocando SOLO a través de `aplicar_movimiento`: esta capa
nunca escribe `productos.stock` directamente."""
from datetime import date

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db, normalizar_texto, paginar, rango_fechas
from app.models import AuditoriaInventario, AuditoriaItem, EstadoAuditoriaInventario, TipoMovimientoStock
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import stock as servicio_stock

TAMANO_MAXIMO = 100


def obtener_auditoria(db, auditoria_id: int, bloquear: bool = False) -> AuditoriaInventario:
    """Sin bloquear: lectura simple. Bloqueando: mismo patrón que
    `services.stock.aplicar_movimiento` (FOR UPDATE por id + populate_existing),
    porque `usuario` va joined y Postgres no bloquea ese lado del join."""
    if bloquear:
        db.execute(select(AuditoriaInventario.id).where(AuditoriaInventario.id == auditoria_id).with_for_update())
        auditoria = db.get(AuditoriaInventario, auditoria_id, populate_existing=True)
    else:
        auditoria = db.get(AuditoriaInventario, auditoria_id)
    if auditoria is None:
        raise NoEncontrado("Auditoría no encontrada")
    return auditoria


def en_curso(db) -> AuditoriaInventario | None:
    return db.scalar(select(AuditoriaInventario).where(AuditoriaInventario.estado == EstadoAuditoriaInventario.EN_CURSO))


def _exigir_en_curso(auditoria: AuditoriaInventario) -> None:
    if auditoria.estado is not EstadoAuditoriaInventario.EN_CURSO:
        raise ReglaDeNegocio("El conteo ya está cerrado.")


def iniciar(db, autor, datos, ip) -> AuditoriaInventario:
    if en_curso(db) is not None:
        raise ReglaDeNegocio("Ya hay un conteo en curso.")
    if datos.filtro_categoria_id is not None:
        servicio_categorias.obtener_categoria(db, datos.filtro_categoria_id)
    auditoria = AuditoriaInventario(
        usuario_id=autor.id, filtro_categoria_id=datos.filtro_categoria_id, notas=normalizar_texto(datos.notas),
        fecha_inicio=ahora_db(),
    )
    db.add(auditoria)
    # Si dos altas llegan a la vez, ambas pasan el chequeo de arriba y el
    # índice único parcial (una sola en curso) salta acá: el handler de
    # IntegrityError lo convierte en 409.
    db.flush()
    db.refresh(auditoria)
    registrar_auditoria(db, accion="auditoria_inventario.iniciar", entidad="auditoria_inventario",
                        entidad_id=auditoria.id, usuario_id=autor.id, estado_nuevo=auditoria, ip_origen=ip)
    return auditoria


def registrar_items(db, autor, auditoria: AuditoriaInventario, items: list, ip) -> list[AuditoriaItem]:
    """Upsert por producto: si ya había un ítem de ese producto en esta
    auditoría, se sobreescribe `cantidad_contada` y se vuelve a capturar
    `cantidad_sistema` (foto del stock AHORA, no la de la primera vez).
    Productos repetidos dentro del mismo pedido: gana el último. Todo se
    valida antes de escribir nada."""
    auditoria = obtener_auditoria(db, auditoria.id, bloquear=True)
    _exigir_en_curso(auditoria)

    por_producto: dict[int, int] = {}
    for item in items:
        por_producto[item.producto_id] = item.cantidad_contada

    productos = {}
    for producto_id in por_producto:
        producto = servicio_productos.obtener_producto(db, producto_id)
        if producto.stock_infinito:
            raise DatoInvalido(f"'{producto.descripcion}' tiene stock infinito: no se puede contar.")
        productos[producto_id] = producto

    existentes = {
        item.producto_id: item
        for item in db.scalars(
            select(AuditoriaItem).where(
                AuditoriaItem.auditoria_id == auditoria.id, AuditoriaItem.producto_id.in_(por_producto)
            )
        ).all()
    }

    resultado = []
    for producto_id, cantidad_contada in por_producto.items():
        producto = productos[producto_id]
        item = existentes.get(producto_id)
        if item is None:
            item = AuditoriaItem(auditoria_id=auditoria.id, producto_id=producto_id,
                                 cantidad_sistema=producto.stock, cantidad_contada=cantidad_contada)
            db.add(item)
        else:
            item.cantidad_sistema = producto.stock
            item.cantidad_contada = cantidad_contada
        resultado.append(item)
    db.flush()
    for item in resultado:
        db.refresh(item)
    # `auditoria.items` (selectin) puede haber quedado cargada de ANTES de
    # este alta (ej. desde `iniciar`, sin ítems); se refresca para que quien
    # tenga la misma instancia en memoria (reportes, `finalizar`) vea los
    # ítems recién agregados sin tener que volver a pedir la auditoría.
    db.refresh(auditoria, attribute_names=["items"])

    registrar_auditoria(
        db, accion="auditoria_inventario.items", entidad="auditoria_inventario", entidad_id=auditoria.id,
        usuario_id=autor.id,
        estado_nuevo={"items": [{"producto_id": pid, "cantidad_contada": c} for pid, c in por_producto.items()]},
        ip_origen=ip,
    )
    return resultado


def _obtener_item_de(db, auditoria: AuditoriaInventario, item_id: int) -> AuditoriaItem:
    item = db.get(AuditoriaItem, item_id)
    if item is None or item.auditoria_id != auditoria.id:
        raise NoEncontrado("Ítem no encontrado")
    return item


def editar_item(db, autor, auditoria: AuditoriaInventario, item_id: int, cantidad_contada: int, ip) -> AuditoriaItem:
    auditoria = obtener_auditoria(db, auditoria.id, bloquear=True)
    _exigir_en_curso(auditoria)
    item = _obtener_item_de(db, auditoria, item_id)
    antes = snapshot(item)
    item.cantidad_contada = cantidad_contada
    db.flush()
    db.refresh(item)
    registrar_auditoria(db, accion="auditoria_inventario.item_editar", entidad="auditoria_item", entidad_id=item.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=item, ip_origen=ip)
    return item


def eliminar_item(db, autor, auditoria: AuditoriaInventario, item_id: int, ip) -> None:
    auditoria = obtener_auditoria(db, auditoria.id, bloquear=True)
    _exigir_en_curso(auditoria)
    item = _obtener_item_de(db, auditoria, item_id)
    antes = snapshot(item)
    db.delete(item)
    db.flush()
    # Igual que registrar_items: quien tenga esta instancia (el router) no ve el ítem borrado.
    db.refresh(auditoria, attribute_names=["items"])
    registrar_auditoria(db, accion="auditoria_inventario.item_eliminar", entidad="auditoria_item", entidad_id=item_id,
                        usuario_id=autor.id, estado_anterior=antes, ip_origen=ip)


def finalizar(db, autor, auditoria: AuditoriaInventario, ip) -> AuditoriaInventario:
    """Cierra el conteo: por cada ítem con diferencia (contado - sistema) el
    stock se ajusta a lo contado vía `aplicar_movimiento`. Si alguno no se
    puede aplicar (ej. se vendió con faltante entre el conteo y el cierre y
    el ajuste dejaría el stock negativo), la excepción sube sin tocar el
    estado de la auditoría: no queda ningún ajuste aplicado a mitad de camino
    ni la auditoría queda cerrada (el rollback de la transacción completa lo
    hace quien llama, igual que en cualquier otro service)."""
    auditoria = obtener_auditoria(db, auditoria.id, bloquear=True)
    _exigir_en_curso(auditoria)
    items = list(auditoria.items)
    if not items:
        raise ReglaDeNegocio("Registrá al menos un producto antes de cerrar el conteo.")

    ajustes = 0
    for item in items:
        diferencia = item.diferencia
        if diferencia != 0:
            servicio_stock.aplicar_movimiento(
                db, autor, tipo=TipoMovimientoStock.AJUSTE_AUDITORIA, producto_id=item.producto_id,
                cantidad=diferencia, auditoria_id=auditoria.id, notas=f"Conteo #{auditoria.id}", ip_origen=ip,
            )
            ajustes += 1

    auditoria.estado = EstadoAuditoriaInventario.CERRADA
    auditoria.fecha_fin = ahora_db()
    db.flush()
    db.refresh(auditoria)
    registrar_auditoria(db, accion="auditoria_inventario.cerrar", entidad="auditoria_inventario",
                        entidad_id=auditoria.id, usuario_id=autor.id, estado_nuevo={"ajustes": ajustes}, ip_origen=ip)
    return auditoria


def listar(db, *, estado: EstadoAuditoriaInventario | None = None, desde: date | None = None,
          hasta: date | None = None, pagina: int = 1, tamano: int = 10) -> tuple[list[AuditoriaInventario], int]:
    condiciones = []
    if estado is not None:
        condiciones.append(AuditoriaInventario.estado == estado)
    condiciones.extend(rango_fechas(AuditoriaInventario.fecha_inicio, desde, hasta))
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(AuditoriaInventario).where(*condiciones))
    auditorias = db.scalars(
        select(AuditoriaInventario).where(*condiciones)
        .order_by(AuditoriaInventario.fecha_inicio.desc(), AuditoriaInventario.id.desc())
        .offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(auditorias), total
