"""PDF y Excel de una auditoría de inventario (conteo): mismos datos, dos formatos."""
from app.core.excel import generar_tabla
from app.reports import pdf

PLANTILLA = "reports/auditoria_inventario.html"
COLUMNAS = ["Código", "Descripción", "Sistema", "Contado", "Diferencia"]


def _filas(auditoria) -> list[list]:
    return [
        [item.producto.codigo_con_verificador, item.producto.descripcion, item.cantidad_sistema,
         item.cantidad_contada, item.diferencia]
        for item in auditoria.items
    ]


def generar_pdf_auditoria(db, auditoria) -> bytes:
    # `db` no se usa hoy (todo lo que necesita la plantilla ya viene cargado
    # en `auditoria`); se mantiene en la firma por si el reporte necesita
    # resolver algo más adelante (ej. el camino de `filtro_categoria_id`).
    return pdf.imprimir(PLANTILLA, {"auditoria": auditoria})


def generar_xls_auditoria(db, auditoria) -> bytes:
    return generar_tabla("Conteo", COLUMNAS, _filas(auditoria))
