"""Reportes (sesión 09): solo lectura. Consultar no audita; exportar a Excel
o PDF sí (`reporte.exportar`, en la transacción que confirma el router)."""
from dataclasses import asdict

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria
from app.core.utils import ahora
from app.models import Categoria, EstadoVenta, MedioDePago, Proveedor, Usuario, Venta
from app.reports import motor
from app.reports.definiciones import REPORTES, obtener_reporte
from app.schemas.ventas import Referencia
from app.services.categorias import caminos

# formato → (extensión, exportador)
FORMATOS = {"excel": ("xlsx", motor.exportar_excel), "pdf": ("pdf", motor.exportar_pdf)}


def catalogo() -> list[dict]:
    return [{"clave": d.clave, "nombre": d.nombre, "descripcion": d.descripcion,
             "filtros_admitidos": list(d.filtros_admitidos), "agrupaciones": list(d.agrupaciones)}
            for d in REPORTES.values()]


def consultar(db, clave: str, filtros) -> dict:
    resultado = motor.generar(db, obtener_reporte(clave), filtros)
    grafico = resultado["grafico"]
    return {**resultado, "columnas": [asdict(c) for c in resultado["columnas"]],
            "grafico": asdict(grafico) if grafico else None}


def _sufijo(filtros) -> str:
    if filtros.desde:
        return f"{filtros.desde.isoformat()}_{filtros.hasta.isoformat()}"
    return ahora().date().isoformat()   # stock valorizado: foto de hoy


def exportar(db, autor, clave: str, filtros, formato: str, ip: str | None) -> tuple[bytes, str]:
    """(contenido, nombre de archivo). Genera primero y audita después: si la
    generación falla no queda registro; si falla el registro, no hay archivo."""
    resultado = motor.generar(db, obtener_reporte(clave), filtros)
    extension, exportador = FORMATOS[formato]
    contenido = exportador(db, resultado)
    aplicados = resultado["filtros"]
    registrar_auditoria(
        db, accion="reporte.exportar", entidad="reporte", usuario_id=autor.id, ip_origen=ip,
        estado_nuevo={"clave": clave, "formato": formato,
                      "filtros": aplicados.model_dump(mode="json", exclude_none=True)},
    )
    return contenido, f"reporte-{clave}-{_sufijo(aplicados)}.{extension}"


def opciones(db) -> dict:
    """Catálogos de los filtros. Vendedores: quienes tienen alguna venta
    confirmada o anulada (aunque hoy estén inactivos); medios: todos."""
    rutas = caminos(db)
    categorias = sorted(
        ({"id": id_, "nombre": rutas[id_], "nivel": nivel}
         for id_, nivel in db.execute(select(Categoria.id, Categoria.nivel))),
        key=lambda c: c["nombre"].lower(),
    )
    # EXISTS correlacionado (no un IN sobre todas las ventas): usa ix_ventas_usuario_id.
    vendieron = (select(Venta.id).where(Venta.usuario_id == Usuario.id, Venta.estado != EstadoVenta.EN_CURSO)
                 .exists())
    vendedores = db.scalars(select(Usuario).where(vendieron).order_by(func.lower(Usuario.nombre)))
    return {
        "proveedores": [Referencia.de(p) for p in db.scalars(select(Proveedor).order_by(func.lower(Proveedor.nombre)))],
        "categorias": categorias,
        "vendedores": [Referencia.de(u) for u in vendedores],
        "medios_de_pago": [Referencia.de(m) for m in db.scalars(select(MedioDePago).order_by(func.lower(MedioDePago.nombre)))],
    }
