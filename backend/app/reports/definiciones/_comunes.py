"""Piezas SQL compartidas por las definiciones de reportes (una sola
definición de "venta que cuenta", período, rama de categoría, categoría de
nivel N, costo en pesos y agregado filas + totales)."""
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import aliased

from app.core.utils import rango_fechas, redondear
from app.models import Categoria, EstadoVenta, Moneda, Producto, Proveedor, Venta, VentaItem
from app.schemas.reportes import Agrupar
from app.services.categorias import caminos, rama_de_ids


def ventas_confirmadas(filtros) -> list:
    """Condiciones de "venta que cuenta": confirmada, con confirmada_en en el
    rango (día completo). Las anuladas y en curso nunca suman."""
    return [Venta.estado == EstadoVenta.CONFIRMADA, *rango_fechas(Venta.confirmada_en, filtros.desde, filtros.hasta)]


def unidades_por_venta(filtros):
    """Subconsulta (venta_id, unidades) de las ventas que cuentan: se une a
    `ventas` sin multiplicar sus importes (venta_items tiene una fila por unidad)."""
    return (select(VentaItem.venta_id, func.count(VentaItem.id).label("unidades"))
            .join(Venta, Venta.id == VentaItem.venta_id)
            .where(*ventas_confirmadas(filtros))
            .group_by(VentaItem.venta_id)
            .subquery("unidades_por_venta"))


def periodo(columna, agrupar: Agrupar):
    """Día, o primer día del mes, de un TIMESTAMP (hora del negocio) como DATE."""
    return cast(func.date_trunc("month" if agrupar is Agrupar.MES else "day", columna), Date)


def condiciones_de_producto(db, filtros) -> list:
    """Filtros opcionales por proveedor y por rama de categoría del producto."""
    condiciones = []
    if filtros.proveedor_id:
        condiciones.append(Producto.proveedor_id == filtros.proveedor_id)
    if filtros.categoria_id:
        condiciones.append(Producto.categoria_id.in_(rama_de_ids(db, filtros.categoria_id)))
    return condiciones


def _categoria_de_nivel(nivel: int):
    """Subconsulta (categoria_id, grupo_id): cada categoría → su ancestro de
    nivel `nivel`, o ella misma si su rama es más corta. CTE recursiva que
    sube por los padres; `padre.nivel < nivel_ancestro` garantiza que termine
    aunque el árbol tuviera un ciclo."""
    ancestros = select(
        Categoria.id.label("categoria_id"), Categoria.id.label("ancestro_id"),
        Categoria.nivel.label("nivel_categoria"), Categoria.nivel.label("nivel_ancestro"),
    ).cte("ancestros", recursive=True)
    actual, padre = aliased(Categoria), aliased(Categoria)
    ancestros = ancestros.union_all(
        select(ancestros.c.categoria_id, padre.id, ancestros.c.nivel_categoria, padre.nivel)
        .select_from(ancestros)
        .join(actual, actual.id == ancestros.c.ancestro_id)
        .join(padre, (padre.id == actual.parent_id) & (padre.nivel < ancestros.c.nivel_ancestro))
    )
    return (select(ancestros.c.categoria_id, ancestros.c.ancestro_id.label("grupo_id"))
            .where(ancestros.c.nivel_ancestro == func.least(ancestros.c.nivel_categoria, nivel))
            .subquery("categoria_de_nivel"))


def grupo_de_producto(db, filtros):
    """Agrupación de productos por categoría (al nivel pedido) o por proveedor.
    Devuelve (unir, grupo, etiquetas): `unir(sentencia)` suma el JOIN que
    haga falta, `grupo` es la columna "grupo_id" y `etiquetas[grupo_id]` el
    texto del grupo (camino de la categoría o nombre del proveedor)."""
    if filtros.agrupar is Agrupar.CATEGORIA:
        mapa = _categoria_de_nivel(filtros.nivel)
        return (lambda sentencia: sentencia.join(mapa, mapa.c.categoria_id == Producto.categoria_id),
                mapa.c.grupo_id.label("grupo_id"), caminos(db))
    return (lambda sentencia: sentencia, Producto.proveedor_id.label("grupo_id"),
            dict(db.execute(select(Proveedor.id, Proveedor.nombre)).all()))


def costo_en_pesos():
    """Mismo cálculo que Producto.costo_en_pesos (dólar ACTUAL del proveedor),
    en SQL. Necesita el JOIN con proveedores."""
    return case((Proveedor.moneda == Moneda.USD, func.round(Producto.costo * Proveedor.dolar_actual, 2)),
                else_=Producto.costo)


def filas_y_totales(db, consulta, grupos: list, medidas: list, *, orden=None, limite=None):
    """Agrega en SQL. `consulta(*columnas)` devuelve el SELECT con sus JOIN y
    WHERE; se ejecuta agrupado por `grupos` (filas) y sin agrupar (totales,
    sobre el mismo conjunto filtrado y sin `limite`)."""
    sentencia = consulta(*grupos, *medidas).group_by(*grupos).order_by(*(orden if orden is not None else grupos))
    if limite:
        sentencia = sentencia.limit(limite)
    filas = [dict(fila) for fila in db.execute(sentencia).mappings()]
    totales = dict(db.execute(consulta(*medidas)).mappings().one())
    return filas, totales


def dividir(dividendo, divisor) -> Decimal:
    """Cociente con 2 decimales; 0 si el divisor es 0 (ticket promedio sin ventas)."""
    return redondear(Decimal(dividendo or 0) / Decimal(divisor)) if divisor else Decimal("0.00")


def porcentaje(parte, total) -> Decimal:
    """parte / total × 100 con 2 decimales; 0 si el total es 0."""
    return dividir(Decimal(parte or 0) * 100, total)
