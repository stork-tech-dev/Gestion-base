"""Registro único de reportes: clave → definición, en el orden del hub.
Agregar un reporte = escribir su módulo en esta carpeta y sumarlo acá (vive
acá y no en el motor porque las definiciones importan el motor)."""
from app.core.errores import NoEncontrado
from app.reports.definiciones import (
    medios_pago, productos_vendidos, rentabilidad, stock_valorizado, vendedores, ventas_periodo,
)

REPORTES = {d.clave: d for d in (
    ventas_periodo.DEFINICION,
    medios_pago.DEFINICION,
    vendedores.DEFINICION,
    productos_vendidos.DEFINICION,
    rentabilidad.DEFINICION,
    stock_valorizado.DEFINICION,
)}


def obtener_reporte(clave: str):
    definicion = REPORTES.get(clave)
    if definicion is None:
        raise NoEncontrado("Reporte no encontrado")
    return definicion
