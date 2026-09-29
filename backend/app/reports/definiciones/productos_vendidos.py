"""Productos más vendidos, por producto o por categoría (al nivel pedido).
Importe = Σ precio_final (ya con descuentos y promociones). Los totales son
de TODO el conjunto filtrado, no solo de las `limite` filas mostradas."""
from sqlalchemy import func, select

from app.models import Producto, Venta, VentaItem
from app.reports.definiciones._comunes import (
    condiciones_de_producto, filas_y_totales, grupo_de_producto, porcentaje, ventas_confirmadas,
)
from app.reports.motor import Columna, DefinicionReporte, Grafico
from app.schemas.reportes import Agrupar, Orden
from app.schemas.reportes import TipoColumna as T


def _columnas(filtros) -> list[Columna]:
    if filtros.agrupar is Agrupar.CATEGORIA:
        grupo = [Columna("categoria", "Categoría", T.TEXTO)]
    else:
        grupo = [Columna("codigo", "Código", T.TEXTO), Columna("descripcion", "Descripción", T.TEXTO)]
    return [*grupo, Columna("unidades", "Unidades", T.ENTERO), Columna("importe", "Importe vendido", T.MONEDA),
            Columna("porcentaje", "% del total", T.PORCENTAJE)]


def _consulta(db, filtros):
    condiciones = [*ventas_confirmadas(filtros), *condiciones_de_producto(db, filtros)]
    if filtros.agrupar is Agrupar.CATEGORIA:
        unir, grupo, etiquetas = grupo_de_producto(db, filtros)
        grupos = [grupo]
    else:
        unir, etiquetas = (lambda sentencia: sentencia), None
        grupos = [Producto.id.label("producto_id"), (Producto.sku + Producto.verificador).label("codigo"),
                  Producto.descripcion.label("descripcion")]

    def consulta(*columnas):
        sentencia = (select(*columnas).select_from(VentaItem)
                     .join(Venta, Venta.id == VentaItem.venta_id)
                     .join(Producto, Producto.id == VentaItem.producto_id))
        return unir(sentencia).where(*condiciones)

    unidades = func.count(VentaItem.id).label("unidades")
    importe = func.sum(VentaItem.precio_final).label("importe")
    principal, desempate = (unidades, importe) if filtros.orden is Orden.UNIDADES else (importe, unidades)
    filas, totales = filas_y_totales(db, consulta, grupos, [unidades, importe],
                                     orden=[principal.desc(), desempate.desc(), grupos[0]], limite=filtros.limite)
    for fila in [*filas, totales]:
        fila["porcentaje"] = porcentaje(fila["importe"], totales["importe"])
    if etiquetas is not None:
        for fila in filas:
            fila["categoria"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


def _grafico(filtros) -> Grafico:
    por_categoria = filtros.agrupar is Agrupar.CATEGORIA
    medida = "Unidades vendidas" if filtros.orden is Orden.UNIDADES else "Importe vendido"
    return Grafico("barras", ("categoria",) if por_categoria else ("descripcion",), filtros.orden.value,
                   f"{medida} por {'categoría' if por_categoria else 'producto'}")


DEFINICION = DefinicionReporte(
    clave="productos-vendidos",
    nombre="Productos más vendidos",
    descripcion="Ranking por unidades o importe, por producto o por categoría",
    filtros_admitidos=("desde", "hasta", "agrupar", "nivel", "orden", "limite", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.PRODUCTO, Agrupar.CATEGORIA),
    grafico=_grafico,
)
