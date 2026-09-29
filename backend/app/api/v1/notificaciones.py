"""Notificaciones del usuario logueado (sesión 07). Solo piden sesión
(decisión 4): cada uno ve y marca únicamente las suyas."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import requiere_login
from app.models import Usuario
from app.schemas.notificaciones import NotificacionesResponse, NotificacionResponse
from app.services import notificaciones as servicio

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("", response_model=NotificacionesResponse)
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_login)):
    notificaciones, no_leidas = servicio.listar(db, usuario)
    return NotificacionesResponse(no_leidas=no_leidas,
                                  resultados=[NotificacionResponse.model_validate(n) for n in notificaciones])


# Antes de /{notificacion_id}/leer (ruta fija primero).
@router.patch("/leer-todas", status_code=204)
def leer_todas(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_login)):
    servicio.marcar_todas(db, usuario)
    db.commit()
    return Response(status_code=204)


@router.patch("/{notificacion_id}/leer", response_model=NotificacionResponse)
def leer(notificacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_login)):
    notificacion = servicio.marcar_leida(db, usuario, notificacion_id)
    db.commit()
    return NotificacionResponse.model_validate(notificacion)
