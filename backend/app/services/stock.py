"""Stock: aplicar_movimiento es el ÚNICO camino por el que cambia
productos.stock (Principio de producto: "el stock solo cambia vía
services.stock.aplicar_movimiento"). El resto de las funciones son ingresos,
mínimos y consultas (listado, alertas, resumen, movimientos)."""
from datetime import date

from sqlalchemy import func, or_, select

from app.core.auditoria import registrar_auditoria
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db, filtro_texto, paginar, rango_fechas, redondear
from app.models import BAJO_MINIMO_SQL, MovimientoStock, Producto, TipoMovimientoStock
from app.schemas.stock import StockResponse
from app.services import categorias as servicio_categorias
from app.services.productos import condiciones_codigo

TAMANO_MAXIMO = 100
STOCK_MAXIMO = 2_000_000_000

SIGNO_POR_TIPO = {
    TipoMovimientoStock.INGRESO_PROVEEDOR: 1, TipoMovimientoStock.ANULACION_VENTA: 1,
    TipoMovimientoStock.VENTA: -1, TipoMovimientoStock.BAJA: -1,
    TipoMovimientoStock.AJUSTE_AUDITORIA: 0,        # cualquier signo
}


def aplicar_movimiento(db, autor, *, tipo, producto_id, cantidad, motivo_baja_id=None, auditoria_id=None,
                       referencia_venta_id=None, permitir_faltante=False, notas=None, ip_origen=None):
    """ÚNICO camino por el que cambia productos.stock. Bloquea la fila del
    producto, valida, guarda el stock resultante y audita. Sin commit."""
    signo = SIGNO_POR_TIPO[tipo]
    if cantidad == 0 or (signo and (cantidad > 0) != (signo > 0)):
        raise DatoInvalido("La cantidad no corresponde al tipo de movimiento.")
    if permitir_faltante and tipo is not TipoMovimientoStock.VENTA:
        raise DatoInvalido("Solo una venta puede dejar el stock en negativo.")
    # FOR UPDATE directo sobre Producto falla: categoria y proveedor son joined
    # con LEFT OUTER JOIN y Postgres no permite bloquear ese lado del join.
    # Se bloquea la fila por id (sin relaciones) y se relee con populate_existing
    # (mismo patrón que app.services.producto_fotos._bloquear_producto).
    db.execute(select(Producto.id).where(Producto.id == producto_id).with_for_update())
    producto = db.get(Producto, producto_id, populate_existing=True)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    antes = producto.stock
    resultante = antes if producto.stock_infinito else antes + cantidad
    if not producto.stock_infinito:
        if cantidad < 0 and resultante < 0 and not permitir_faltante:
            raise ReglaDeNegocio(
                f"No hay stock suficiente de '{producto.descripcion}': hay {antes} y se piden {-cantidad}")
        if abs(resultante) > STOCK_MAXIMO:
            raise DatoInvalido("El stock resultante está fuera del rango permitido.")
    movimiento = MovimientoStock(tipo=tipo, producto_id=producto.id, cantidad=cantidad, stock_resultante=resultante,
                                 motivo_baja_id=motivo_baja_id, auditoria_id=auditoria_id,
                                 referencia_venta_id=referencia_venta_id, usuario_id=autor.id,
                                 timestamp=ahora_db(), notas=(notas or "").strip() or None)
    producto.stock = resultante
    db.add(movimiento)
    db.flush()
    registrar_auditoria(db, accion=f"stock.{tipo.value}", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_anterior={"stock": antes},
                        estado_nuevo={"stock": resultante, "cantidad": cantidad, "movimiento_id": movimiento.id},
                        ip_origen=ip_origen)
    return movimiento


def registrar_ingreso(db, autor, producto_id: int, cantidad: int, notas: str | None, ip: str | None) -> MovimientoStock:
    if not isinstance(cantidad, int) or cantidad <= 0:
        raise DatoInvalido("La cantidad debe ser un número entero mayor a 0.")
    return aplicar_movimiento(db, autor, tipo=TipoMovimientoStock.INGRESO_PROVEEDOR, producto_id=producto_id,
                              cantidad=cantidad, notas=notas, ip_origen=ip)


def definir_minimo(db, autor, producto_id: int, stock_minimo: int, ip: str | None) -> Producto:
    if stock_minimo < 0:
        raise DatoInvalido("El mínimo no puede ser negativo.")
    # Mismo lock que aplicar_movimiento (ver comentario ahí): por id, sin relaciones.
    db.execute(select(Producto.id).where(Producto.id == producto_id).with_for_update())
    producto = db.get(Producto, producto_id, populate_existing=True)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    if producto.stock_infinito:
        raise DatoInvalido("Un producto con stock infinito no lleva mínimo.")
    if producto.stock_minimo == stock_minimo:
        return producto
    antes = producto.stock_minimo
    producto.stock_minimo = stock_minimo
    db.flush()
    registrar_auditoria(db, accion="stock.minimo", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_anterior={"stock_minimo": antes},
                        estado_nuevo={"stock_minimo": stock_minimo}, ip_origen=ip)
    return producto


def listar_stock(db, *, busqueda: str | None = None, categoria_id: int | None = None,
                 proveedor_id: int | None = None, solo_bajo_minimo: bool = False, incluir_sin_stock: bool = True,
                 pagina: int = 1, tamano: int = 10) -> tuple[list[Producto], int]:
    condiciones = [Producto.activo.is_(True)]
    if busqueda and busqueda.strip():
        condiciones.append(or_(condiciones_codigo(busqueda), filtro_texto(Producto.sku_proveedor, busqueda),
                               filtro_texto(Producto.descripcion, busqueda)))
        # Los infinitos quedan afuera del listado de stock salvo que el código
        # buscado sea justo el suyo (se los puede encontrar puntualmente).
        condiciones.append(or_(Producto.stock_infinito.is_(False), condiciones_codigo(busqueda)))
    else:
        condiciones.append(Producto.stock_infinito.is_(False))
    if categoria_id is not None:
        condiciones.append(Producto.categoria_id.in_(servicio_categorias.rama_de_ids(db, categoria_id)))
    if proveedor_id is not None:
        condiciones.append(Producto.proveedor_id == proveedor_id)
    if solo_bajo_minimo:
        condiciones.append(BAJO_MINIMO_SQL)
    if not incluir_sin_stock:
        condiciones.append(Producto.stock > 0)
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Producto).where(*condiciones))
    productos = db.scalars(
        select(Producto).where(*condiciones).order_by(func.lower(Producto.descripcion), Producto.sku)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(productos), total


def alertas(db, limite: int = 20) -> list[Producto]:
    return list(db.scalars(
        select(Producto).where(Producto.activo.is_(True), Producto.stock_infinito.is_(False), BAJO_MINIMO_SQL)
        .order_by(Producto.stock - Producto.stock_minimo)
        .limit(limite)
    ).unique().all())


def resumen(db) -> dict:
    con_stock = Producto.stock > 0
    fila = db.execute(
        select(
            func.count().filter(con_stock),
            func.coalesce(func.sum(Producto.stock).filter(con_stock), 0),
            func.coalesce(func.sum(Producto.stock * Producto.precio_venta).filter(con_stock), 0),
            func.count().filter(BAJO_MINIMO_SQL),
        ).where(Producto.activo.is_(True), Producto.stock_infinito.is_(False))
    ).one()
    return {
        "productos_con_stock": fila[0],
        "unidades": fila[1],
        "valorizado": redondear(fila[2]),
        "bajo_minimo": fila[3],
    }


def listar_movimientos(db, *, producto_id: int | None = None, tipo: TipoMovimientoStock | None = None,
                       desde: date | None = None, hasta: date | None = None, pagina: int = 1,
                       tamano: int = 10) -> tuple[list[MovimientoStock], int]:
    condiciones = []
    if producto_id is not None:
        condiciones.append(MovimientoStock.producto_id == producto_id)
    if tipo is not None:
        condiciones.append(MovimientoStock.tipo == tipo)
    condiciones.extend(rango_fechas(MovimientoStock.timestamp, desde, hasta))
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(MovimientoStock).where(*condiciones))
    movimientos = db.scalars(
        select(MovimientoStock).where(*condiciones)
        .order_by(MovimientoStock.timestamp.desc(), MovimientoStock.id.desc())
        .offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(movimientos), total


def a_respuesta(db, productos) -> list[StockResponse]:
    rutas = servicio_categorias.caminos(db)
    return [StockResponse.desde(p, rutas[p.categoria_id]) for p in productos]
