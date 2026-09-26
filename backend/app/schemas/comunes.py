"""Esquemas compartidos por todos los módulos."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class RespuestaPaginada(BaseModel, Generic[T]):
    """Envoltorio estándar de todos los listados paginados."""

    total: int
    pagina: int
    tamano: int
    resultados: list[T]


class MensajeResponse(BaseModel):
    mensaje: str
