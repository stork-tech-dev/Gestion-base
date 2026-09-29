"""Importación inicial desde Excel (sesión 08). Todas las rutas piden
IMPORTACION crear (decisión de producto: alcanza con ese permiso)."""
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TAMANO_MAXIMO_BYTES, TIPO_XLSX
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ahora, ip_de_request
from app.models import Usuario
from app.schemas.importacion import ResultadoImportacion, TipoImportacion
from app.services import importacion as servicio

router = APIRouter(prefix="/importacion", tags=["importacion"])

puede_importar = requiere_permiso(Modulo.IMPORTACION, "crear")


def _leer(archivo: UploadFile) -> bytes:
    return archivo.file.read(TAMANO_MAXIMO_BYTES + 1)   # leer_tabla rechaza lo que pase de 5 MB


def _nombre(archivo: UploadFile) -> str | None:
    """Nombre del archivo para la auditoría, acotado (lo manda el cliente)."""
    return archivo.filename[:255] if archivo.filename else None


@router.get(
    "/{tipo}/plantilla",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}},
                     "description": "Plantilla .xlsx con la hoja de datos y la hoja Instrucciones"}},
)
def plantilla(tipo: TipoImportacion, _: Usuario = Depends(puede_importar)):
    nombre = f"importar-{tipo.value}-{ahora().date().isoformat()}.xlsx"
    return Response(content=servicio.generar_plantilla(tipo), media_type=TIPO_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/{tipo}/validar", response_model=ResultadoImportacion)
def validar(tipo: TipoImportacion, archivo: UploadFile = File(...), db: Session = Depends(get_db),
            autor: Usuario = Depends(puede_importar)):
    resultado = servicio.validar(db, autor, tipo, _leer(archivo), _nombre(archivo))
    db.rollback()       # el service ya revirtió su savepoint; esto libera los locks tomados
    return resultado


@router.post("/{tipo}/importar", response_model=ResultadoImportacion)
def importar(tipo: TipoImportacion, request: Request, archivo: UploadFile = File(...),
             db: Session = Depends(get_db), autor: Usuario = Depends(puede_importar)):
    resultado = servicio.importar(db, autor, tipo, _leer(archivo), _nombre(archivo), ip_de_request(request))
    if resultado["aplicado"]:
        db.commit()
    else:
        db.rollback()
    return resultado
