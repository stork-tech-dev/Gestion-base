"""Ventas por vendedor (quien cargó y confirmó la venta)."""
from sqlalchemy import func, select

from app.models import Usuario, Venta
from app.reports.definiciones._comunes import dividir, filas_y_totales, unidades_por_venta, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte, Grafico
from app.schemas.reportes import TipoColumna as T


def _columnas(_filtros) -> list[Columna]:
    return [
        Columna("vendedor", "Vendedor", T.TEXTO),
        Columna("ventas", "Ventas", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("total", "Total", T.MONEDA),
        Columna("ticket_promedio", "Ticket promedio", T.MONEDA),
        Columna("descuentos", "Descuentos otorgados", T.MONEDA),
    ]


def _consulta(db, filtros):
    unidades = unidades_por_venta(filtros)
    condiciones = ventas_confirmadas(filtros)
    if filtros.usuario_id:
        condiciones.append(Venta.usuario_id == filtros.usuario_id)

    def consulta(*columnas):
        return (select(*columnas).select_from(Venta)
                .join(Usuario, Usuario.id == Venta.usuario_id)
                .outerjoin(unidades, unidades.c.venta_id == Venta.id)
                .where(*condiciones))

    total = func.sum(Venta.total).label("total")
    filas, totales = filas_y_totales(
        db, consulta, [Usuario.id.label("usuario_id"), Usuario.nombre.label("vendedor")],
        [func.count(Venta.id).label("ventas"), func.sum(unidades.c.unidades).label("unidades"), total,
         func.sum(Venta.descuento_total).label("descuentos")],
        orden=[total.desc(), func.lower(Usuario.nombre), Usuario.id],
    )
    for fila in [*filas, totales]:
        fila["ticket_promedio"] = dividir(fila["total"], fila["ventas"])
    return filas, totales


def _grafico(_filtros) -> Grafico:
    return Grafico("barras", ("vendedor",), "total", "Total vendido por vendedor")


DEFINICION = DefinicionReporte(
    clave="vendedores",
    nombre="Ventas por vendedor",
    descripcion="Ventas, unidades, ticket promedio y descuentos de cada vendedor",
    filtros_admitidos=("desde", "hasta", "usuario_id"),
    columnas=_columnas,
    consulta=_consulta,
    grafico=_grafico,
)
