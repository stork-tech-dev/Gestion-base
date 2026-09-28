from pydantic import BaseModel, ConfigDict, Field


class CategoriaEditar(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    orden: int = Field(default=0, ge=0, le=32767)


class CategoriaCrear(CategoriaEditar):
    parent_id: int | None = None


class CategoriaMover(BaseModel):
    parent_id: int | None = None


class CategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    nivel: int
    parent_id: int | None
    orden: int


class CategoriaNodo(CategoriaResponse):
    hijos: list["CategoriaNodo"] = []
