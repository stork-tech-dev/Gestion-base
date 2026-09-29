"""Registro único de reportes: clave → definición, en el orden del hub.
Agregar un reporte = escribir su módulo en esta carpeta y sumarlo acá (vive
acá y no en el motor porque las definiciones importan el motor)."""
from app.core.errores import NoEncontrado
from app.reports.definiciones import stock_valorizado

REPORTES = {d.clave: d for d in (
    stock_valorizado.DEFINICION,
)}


def obtener_reporte(clave: str):
    definicion = REPORTES.get(clave)
    if definicion is None:
        raise NoEncontrado("Reporte no encontrado")
    return definicion
