from datetime import datetime

from pydantic import BaseModel, Field


class RolCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=255)


class RolEditar(RolCrear):
    pass


class RolEstado(BaseModel):
    activo: bool


class RolResponse(BaseModel):
    id: int
    nombre: str
    descripcion: str | None
    es_sistema: bool
    activo: bool
    cantidad_usuarios: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def desde(cls, rol, cantidad_usuarios: int) -> "RolResponse":
        return cls(
            id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, es_sistema=rol.es_sistema,
            activo=rol.activo, cantidad_usuarios=cantidad_usuarios, created_at=rol.created_at,
            updated_at=rol.updated_at,
        )
