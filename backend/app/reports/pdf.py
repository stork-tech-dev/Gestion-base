"""Única vía de WeasyPrint: plantilla Jinja de templates/reports → PDF."""
from weasyprint import HTML

from app.core.templates import APP_DIR, templates


def html(plantilla: str, contexto: dict) -> str:
    return templates.get_template(plantilla).render(**contexto)


def documento(plantilla: str, contexto: dict):
    return HTML(string=html(plantilla, contexto), base_url=str(APP_DIR)).render()


def imprimir(plantilla: str, contexto: dict) -> bytes:
    return documento(plantilla, contexto).write_pdf()
