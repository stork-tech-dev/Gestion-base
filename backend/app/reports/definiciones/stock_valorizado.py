"""Stock valorizado: foto ACTUAL (sin fechas) del stock de los productos
activos, con stock y sin stock infinito, a costo (en pesos, con el dólar
actual del proveedor) y a precio de venta."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Producto, Proveedor
from app.reports.definiciones._comunes import (
    condiciones_de_producto, costo_en_pesos, filas_y_totales, grupo_de_producto, porcentaje,
)
from app.reports.motor import Columna, DefinicionReporte, Grafico, titulo_de_agrupacion
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T
from app.services.stock import STOCK_SQL


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("grupo", titulo_de_agrupacion(filtros.agrupar), T.TEXTO),
        Columna("productos", "Productos", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("valorizado_costo", "Valorizado a costo", T.MONEDA),
        Columna("valorizado_venta", "Valorizado a venta", T.MONEDA),
        Columna("ganancia_potencial", "Ganancia potencial", T.MONEDA),
        Columna("margen_potencial", "Margen potencial %", T.PORCENTAJE),
    ]


def _consulta(db, filtros):
    unir, grupo, etiquetas = grupo_de_producto(db, filtros)
    condiciones = [Producto.activo.is_(True), Producto.stock_infinito.is_(False), STOCK_SQL > 0,
                   *condiciones_de_producto(db, filtros)]

    def consulta(*columnas):
        sentencia = select(*columnas).select_from(Producto).join(Proveedor, Proveedor.id == Producto.proveedor_id)
        return unir(sentencia).where(*condiciones)

    valorizado_costo = func.sum(costo_en_pesos() * STOCK_SQL).label("valorizado_costo")
    filas, totales = filas_y_totales(db, consulta, [grupo], [
        func.count(Producto.id).label("productos"),
        func.sum(STOCK_SQL).label("unidades"),
        valorizado_costo,
        func.sum(Producto.precio_venta * STOCK_SQL).label("valorizado_venta"),
    ], orden=[valorizado_costo.desc(), grupo])
    for fila in [*filas, totales]:
        fila["ganancia_potencial"] = Decimal(fila["valorizado_venta"] or 0) - Decimal(fila["valorizado_costo"] or 0)
        fila["margen_potencial"] = porcentaje(fila["ganancia_potencial"], fila["valorizado_venta"])
    for fila in filas:
        fila["grupo"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


def _grafico(filtros) -> Grafico:
    return Grafico("barras", ("grupo",), "valorizado_costo",
                   f"Valorizado a costo por {titulo_de_agrupacion(filtros.agrupar).lower()}")


DEFINICION = DefinicionReporte(
    clave="stock-valorizado",
    nombre="Stock valorizado",
    descripcion="Stock actual valorizado a costo y a precio de venta",
    filtros_admitidos=("agrupar", "nivel", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.CATEGORIA, Agrupar.PROVEEDOR),
    grafico=_grafico,
)
