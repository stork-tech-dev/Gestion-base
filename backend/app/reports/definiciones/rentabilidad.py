"""Rentabilidad: importe vendido (Σ precio_final) menos costo CONGELADO de
cada unidad (venta_items.costo_unitario). Los recargos por cuotas son
financieros y no entran; cambiar después el costo o el dólar no la altera."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Producto, Venta, VentaItem
from app.reports.definiciones._comunes import (
    condiciones_de_producto, filas_y_totales, grupo_de_producto, periodo, porcentaje, ventas_confirmadas,
)
from app.reports.motor import Columna, DefinicionReporte, Grafico, titulo_de_agrupacion
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T

TIPO_DEL_GRUPO = {Agrupar.DIA: T.FECHA, Agrupar.MES: T.MES}


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("grupo", titulo_de_agrupacion(filtros.agrupar), TIPO_DEL_GRUPO.get(filtros.agrupar, T.TEXTO)),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("importe", "Importe vendido", T.MONEDA),
        Columna("costo", "Costo", T.MONEDA),
        Columna("ganancia", "Ganancia bruta", T.MONEDA),
        Columna("margen", "Margen %", T.PORCENTAJE),
    ]


def _consulta(db, filtros):
    condiciones = [*ventas_confirmadas(filtros), *condiciones_de_producto(db, filtros)]
    importe = func.sum(VentaItem.precio_final).label("importe")
    if filtros.agrupar in TIPO_DEL_GRUPO:
        unir, etiquetas = (lambda sentencia: sentencia), None
        grupo = periodo(Venta.confirmada_en, filtros.agrupar).label("grupo")
        orden = [grupo]
    else:
        unir, grupo, etiquetas = grupo_de_producto(db, filtros)
        orden = [importe.desc(), grupo]

    def consulta(*columnas):
        sentencia = (select(*columnas).select_from(VentaItem)
                     .join(Venta, Venta.id == VentaItem.venta_id)
                     .join(Producto, Producto.id == VentaItem.producto_id))
        return unir(sentencia).where(*condiciones)

    filas, totales = filas_y_totales(db, consulta, [grupo], [
        func.count(VentaItem.id).label("unidades"), importe, func.sum(VentaItem.costo_unitario).label("costo"),
    ], orden=orden)
    for fila in [*filas, totales]:
        fila["ganancia"] = Decimal(fila["importe"] or 0) - Decimal(fila["costo"] or 0)
        fila["margen"] = porcentaje(fila["ganancia"], fila["importe"])
    if etiquetas is not None:
        for fila in filas:
            fila["grupo"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


def _grafico(filtros) -> Grafico:
    return Grafico("linea" if filtros.agrupar in TIPO_DEL_GRUPO else "barras", ("grupo",), "ganancia",
                   f"Ganancia bruta por {titulo_de_agrupacion(filtros.agrupar).lower()}")


DEFINICION = DefinicionReporte(
    clave="rentabilidad",
    nombre="Rentabilidad",
    descripcion="Importe vendido, costo, ganancia bruta y margen",
    filtros_admitidos=("desde", "hasta", "agrupar", "nivel", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.DIA, Agrupar.MES, Agrupar.CATEGORIA, Agrupar.PROVEEDOR),
    grafico=_grafico,
)
