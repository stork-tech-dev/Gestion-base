import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from app.models import ResultadoAcceso
from app.schemas.auth import Password


def normalizar_celular(valor):
    """"+54 9 351-210-8190" → "+5493512108190". Vacío → None."""
    if valor is None:
        return None
    limpio = re.sub(r"[\s\-().]", "", str(valor))
    if not limpio:
        return None
    if not re.fullmatch(r"\+?\d{6,19}", limpio):
        raise ValueError("Celular inválido: solo dígitos (de 6 a 19), con + opcional")
    return limpio


Celular = Annotated[str | None, BeforeValidator(normalizar_celular)]


class UsuarioCrear(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=1, max_length=150)
    password: Password
    rol_id: int
    email: EmailStr | None = None
    fecha_nacimiento: date | None = None
    celular: Celular = None


class UsuarioEditar(BaseModel):
    """Todos opcionales. Se distingue "no enviado" de "enviado en null"
    (model_fields_set). El username no se edita (extra prohibido)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    rol_id: int | None = None
    email: EmailStr | None = None
    fecha_nacimiento: date | None = None
    celular: Celular = None
    password: Password | None = None


class UsuarioEstado(BaseModel):
    activo: bool


class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str | None
    nombre: str
    rol_id: int
    rol: str
    activo: bool
    fecha_nacimiento: date | None
    celular: str | None
    created_at: datetime
    updated_at: datetime
    ultimo_acceso: datetime | None

    @classmethod
    def desde(cls, usuario) -> "UsuarioResponse":
        return cls(
            id=usuario.id, username=usuario.username, email=usuario.email, nombre=usuario.nombre,
            rol_id=usuario.rol_id, rol=usuario.rol.nombre, activo=usuario.activo,
            fecha_nacimiento=usuario.fecha_nacimiento, celular=usuario.celular,
            created_at=usuario.created_at, updated_at=usuario.updated_at, ultimo_acceso=usuario.ultimo_acceso,
        )


class RolAsignable(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None


class HistorialAccesoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    ip_origen: str | None
    resultado: ResultadoAcceso
    detalle: str | None
