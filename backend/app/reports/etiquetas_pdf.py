"""Etiquetas para la Zebra GC420t (se abren en el navegador y se imprimen desde
el diálogo del sistema). No se guardan en disco."""
import base64

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.reports import pdf
from app.services.productos import obtener_producto, svg_code128

TIPOS = ("rectangular", "colita")
MAXIMO_ETIQUETAS = 1000
POR_RENGLON = 3
PLANTILLA = "reports/etiquetas.html"


def _contexto(db, items, tipo) -> dict:
    if tipo not in TIPOS:
        raise DatoInvalido("El tipo de etiqueta tiene que ser 'rectangular' o 'colita'.")
    if not items or any(cantidad < 1 for _, cantidad in items):
        raise DatoInvalido("Cada producto tiene que llevar al menos una etiqueta.")
    if sum(cantidad for _, cantidad in items) > MAXIMO_ETIQUETAS:
        raise ReglaDeNegocio(f"Se pueden imprimir hasta {MAXIMO_ETIQUETAS} etiquetas por vez.")
    etiquetas = []
    for producto_id, cantidad in items:
        producto = obtener_producto(db, producto_id)
        svg = svg_code128(producto.codigo_con_verificador, ancho_mm=16, alto_mm=4.5)
        dato = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        etiquetas += [{"codigo": producto.codigo_con_verificador, "barcode": dato}] * cantidad
    paginas = ([etiquetas[i:i + POR_RENGLON] for i in range(0, len(etiquetas), POR_RENGLON)]
               if tipo == "rectangular" else [[e] for e in etiquetas])
    return {"tipo": tipo, "paginas": paginas}


def html_etiquetas(db, items, tipo) -> str:
    return pdf.html(PLANTILLA, _contexto(db, items, tipo))


def etiquetas_documento(db, items, tipo):
    return pdf.documento(PLANTILLA, _contexto(db, items, tipo))


def generar_etiquetas(db, items, tipo) -> bytes:
    return pdf.imprimir(PLANTILLA, _contexto(db, items, tipo))
