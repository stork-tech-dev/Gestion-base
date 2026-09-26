"""Consulta de la auditoría (solo lectura)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.models import Usuario
from app.schemas.auditoria import AuditoriaResponse
from app.schemas.comunes import RespuestaPaginada
from app.services.auditoria import TAMANO_MAXIMO_AUDITORIA, listar_auditoria

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("", response_model=RespuestaPaginada[AuditoriaResponse])
def listar(usuario_id: int | None = None, accion: str | None = None, entidad: str | None = None,
           entidad_id: int | None = None, desde: date | None = None, hasta: date | None = None,
           pagina: int = Query(1, ge=1), tamano: int = Query(50, ge=1, le=TAMANO_MAXIMO_AUDITORIA),
           db: Session = Depends(get_db), _: Usuario = Depends(requiere_permiso(Modulo.AUDITORIA, "ver"))):
    registros, total = listar_auditoria(db, usuario_id=usuario_id, accion=accion, entidad=entidad,
                                        entidad_id=entidad_id, desde=desde, hasta=hasta, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[AuditoriaResponse.model_validate(r) for r in registros])
