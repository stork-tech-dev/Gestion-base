"""Ventas por período: ventas confirmadas por día o mes de `confirmada_en`
y, aparte, las anuladas por el período en que se ANULARON (decisión del
módulo: coincide con el arqueo del turno que las descontó)."""
from sqlalchemy import func, select

from app.core.utils import rango_fechas
from app.models import EstadoVenta, Venta
from app.reports.definiciones._comunes import dividir, filas_y_totales, periodo, unidades_por_venta, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("periodo", "Período", T.MES if filtros.agrupar is Agrupar.MES else T.FECHA),
        Columna("ventas", "Ventas", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("subtotal", "Subtotal", T.MONEDA),
        Columna("descuentos", "Descuentos", T.MONEDA),
        Columna("recargos", "Recargos", T.MONEDA),
        Columna("total", "Total", T.MONEDA),
        Columna("ticket_promedio", "Ticket promedio", T.MONEDA),
        Columna("anuladas", "Anuladas (cant.)", T.ENTERO),
        Columna("anuladas_monto", "Anuladas ($)", T.MONEDA),
    ]


def _consulta(db, filtros):
    unidades = unidades_por_venta(filtros)

    def confirmadas(*columnas):
        return (select(*columnas).select_from(Venta)
                .outerjoin(unidades, unidades.c.venta_id == Venta.id)
                .where(*ventas_confirmadas(filtros)))

    filas, totales = filas_y_totales(db, confirmadas, [periodo(Venta.confirmada_en, filtros.agrupar).label("periodo")], [
        func.count(Venta.id).label("ventas"),
        func.sum(unidades.c.unidades).label("unidades"),
        func.sum(Venta.subtotal).label("subtotal"),
        func.sum(Venta.descuento_total).label("descuentos"),
        func.sum(Venta.recargo_total).label("recargos"),
        func.sum(Venta.total).label("total"),
    ])

    def anuladas(*columnas):
        return (select(*columnas).select_from(Venta)
                .where(Venta.estado == EstadoVenta.ANULADA,
                       *rango_fechas(Venta.anulada_en, filtros.desde, filtros.hasta)))

    filas_anuladas, totales_anuladas = filas_y_totales(
        db, anuladas, [periodo(Venta.anulada_en, filtros.agrupar).label("periodo")],
        [func.count(Venta.id).label("anuladas"), func.sum(Venta.total).label("anuladas_monto")])

    # Unión de los dos conjuntos YA agregados: un período puede tener solo ventas, solo anuladas o ambas.
    por_periodo = {fila["periodo"]: fila for fila in filas}
    for fila in filas_anuladas:
        por_periodo.setdefault(fila["periodo"], {"periodo": fila["periodo"]}).update(fila)
    filas = [por_periodo[p] for p in sorted(por_periodo)]
    totales.update(totales_anuladas)
    for fila in [*filas, totales]:
        fila["ticket_promedio"] = dividir(fila.get("total"), fila.get("ventas"))
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="ventas-periodo",
    nombre="Ventas por período",
    descripcion="Ventas, unidades, descuentos, recargos y anuladas por día o por mes",
    filtros_admitidos=("desde", "hasta", "agrupar"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.DIA, Agrupar.MES),
)
