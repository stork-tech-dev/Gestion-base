from pydantic import BaseModel, Field


class PermisoEntrada(BaseModel):
    modulo: str = Field(min_length=1, max_length=50)
    recurso: str | None = Field(default=None, max_length=100)
    puede_ver: bool = False
    puede_crear: bool = False
    puede_editar: bool = False
    puede_eliminar: bool = False


class ActualizarPermisos(BaseModel):
    permisos: list[PermisoEntrada]


class NodoPermiso(BaseModel):
    modulo: str
    recurso: str | None
    label: str
    acciones_aplicables: list[str]
    puede_ver: bool | None = None
    puede_crear: bool | None = None
    puede_editar: bool | None = None
    puede_eliminar: bool | None = None
    # Solo en el árbol de un usuario: de dónde sale cada permiso.
    heredado_ver: bool | None = None
    heredado_crear: bool | None = None
    heredado_editar: bool | None = None
    heredado_eliminar: bool | None = None
    override_ver: bool | None = None
    override_crear: bool | None = None
    override_editar: bool | None = None
    override_eliminar: bool | None = None
    # Solo en el árbol de un usuario pedido por un autor: si puede concederlo.
    otorgable_ver: bool | None = None
    otorgable_crear: bool | None = None
    otorgable_editar: bool | None = None
    otorgable_eliminar: bool | None = None
    recursos: list["NodoPermiso"] = []


class ArbolPermisos(BaseModel):
    modulos: list[NodoPermiso]


class AccesoResponse(BaseModel):
    clave: str
    label: str
    heredado: bool
    override: bool
    permitido: bool
    otorgable: bool = True


class ActualizarAccesos(BaseModel):
    accesos: list[str]
