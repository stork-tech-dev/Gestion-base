"""Notificaciones del usuario logueado (sesión 07)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import TipoNotificacion


class NotificacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    tipo: TipoNotificacion
    titulo: str
    cuerpo: str
    leida: bool
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime


class NotificacionesResponse(BaseModel):
    no_leidas: int
    resultados: list[NotificacionResponse]
