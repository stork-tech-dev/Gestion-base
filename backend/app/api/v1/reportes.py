"""Reportes (sesión 09): catálogo, opciones de filtros y cada reporte en
JSON, Excel y PDF con los mismos query params. Todo pide REPORTES ver.
Rutas fijas ("" y /opciones) declaradas ANTES de /{clave}."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TIPO_XLSX
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.reportes import FiltrosReporte, OpcionesReportes, ReporteCatalogo, ReporteResponse
from app.services import reportes as servicio

router = APIRouter(prefix="/reportes", tags=["reportes"])

puede_ver = requiere_permiso(Modulo.REPORTES, "ver")
Filtros = Annotated[FiltrosReporte, Query()]


@router.get("", response_model=list[ReporteCatalogo])
def catalogo(_: Usuario = Depends(puede_ver)):
    return servicio.catalogo()


@router.get("/opciones", response_model=OpcionesReportes)
def opciones(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.opciones(db)


@router.get("/{clave}", response_model=ReporteResponse)
def reporte(clave: str, filtros: Filtros, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.consultar(db, clave, filtros)


def _exportar(db, autor, request, clave, filtros, formato, media_type, disposicion) -> Response:
    contenido, nombre = servicio.exportar(db, autor, clave, filtros, formato, ip_de_request(request))
    db.commit()
    return Response(content=contenido, media_type=media_type,
                    headers={"Content-Disposition": f'{disposicion}; filename="{nombre}"'})


@router.get(
    "/{clave}/excel",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}}}},
)
def excel(clave: str, filtros: Filtros, request: Request, db: Session = Depends(get_db),
          autor: Usuario = Depends(puede_ver)):
    return _exportar(db, autor, request, clave, filtros, "excel", TIPO_XLSX, "attachment")


@router.get(
    "/{clave}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def pdf(clave: str, filtros: Filtros, request: Request, db: Session = Depends(get_db),
        autor: Usuario = Depends(puede_ver)):
    return _exportar(db, autor, request, clave, filtros, "pdf", "application/pdf", "inline")
