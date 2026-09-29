"""Ventas por medio de pago y plan de cuotas. El costo del medio es una
ESTIMACIÓN (total cobrado × costo_medio del plan); un pago sin plan tiene
costo 0 (decisión del módulo: costo_medio solo existe en los planes)."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import MedioDePago, PlanCuotas, Venta, VentaPago
from app.reports.definiciones._comunes import filas_y_totales, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte, Grafico
from app.schemas.reportes import TipoColumna as T


def etiqueta_plan(cuotas: int | None, recargo) -> str:
    """"Un pago" (sin plan) o "N cuotas +X%" (el recargo solo si hay)."""
    if cuotas is None:
        return "Un pago"
    texto = "1 cuota" if cuotas == 1 else f"{cuotas} cuotas"
    if recargo:
        texto += f" +{format(Decimal(recargo).normalize(), 'f').replace('.', ',')}%"
    return texto


def _columnas(_filtros) -> list[Columna]:
    return [
        Columna("medio", "Medio", T.TEXTO),
        Columna("plan", "Plan", T.TEXTO),
        Columna("pagos", "Pagos", T.ENTERO),
        Columna("monto", "Monto", T.MONEDA),
        Columna("recargo", "Recargo", T.MONEDA),
        Columna("total_cobrado", "Total cobrado", T.MONEDA),
        Columna("costo_medio", "Costo del medio (estimado)", T.MONEDA),
        Columna("neto", "Neto", T.MONEDA),
    ]


def _consulta(db, filtros):
    condiciones = ventas_confirmadas(filtros)
    if filtros.medio_de_pago_id:
        condiciones.append(VentaPago.medio_de_pago_id == filtros.medio_de_pago_id)
    if filtros.usuario_id:
        condiciones.append(Venta.usuario_id == filtros.usuario_id)

    def consulta(*columnas):
        return (select(*columnas).select_from(VentaPago)
                .join(Venta, Venta.id == VentaPago.venta_id)
                .join(MedioDePago, MedioDePago.id == VentaPago.medio_de_pago_id)
                .outerjoin(PlanCuotas, PlanCuotas.id == VentaPago.plan_cuotas_id)
                .where(*condiciones))

    costo = func.round(VentaPago.monto_total * func.coalesce(PlanCuotas.costo_medio, 0) / 100, 2)
    filas, totales = filas_y_totales(
        db, consulta,
        [MedioDePago.id.label("medio_id"), MedioDePago.nombre.label("medio"), PlanCuotas.id.label("plan_id"),
         PlanCuotas.cuotas.label("cuotas"), PlanCuotas.recargo_cliente.label("recargo_plan")],
        [func.count(VentaPago.id).label("pagos"), func.sum(VentaPago.monto).label("monto"),
         func.sum(VentaPago.recargo).label("recargo"), func.sum(VentaPago.monto_total).label("total_cobrado"),
         func.sum(costo).label("costo_medio")],
        orden=[func.lower(MedioDePago.nombre), MedioDePago.id, PlanCuotas.cuotas.asc().nulls_first(),
               PlanCuotas.recargo_cliente, PlanCuotas.id],
    )
    for fila in [*filas, totales]:
        fila["neto"] = Decimal(fila["total_cobrado"] or 0) - Decimal(fila["costo_medio"] or 0)
    for fila in filas:
        fila["plan"] = etiqueta_plan(fila["cuotas"], fila["recargo_plan"])
    return filas, totales


def _grafico(_filtros) -> Grafico:
    return Grafico("barras", ("medio", "plan"), "total_cobrado", "Total cobrado por medio de pago")


DEFINICION = DefinicionReporte(
    clave="medios-pago",
    nombre="Ventas por medio de pago",
    descripcion="Cobros por medio y plan de cuotas, con recargos y costo estimado del medio",
    filtros_admitidos=("desde", "hasta", "medio_de_pago_id", "usuario_id"),
    columnas=_columnas,
    consulta=_consulta,
    grafico=_grafico,
)
