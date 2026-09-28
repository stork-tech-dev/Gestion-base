"""Esquemas de promociones de ventas (sesión 06): 2x1, 3x2 y descuento por
porcentaje, con su alcance (productos, categorías y medios de pago)."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models import TipoAlcancePromocion, TipoPromocion


class PromocionAlcanceDatos(BaseModel):
    tipo_alcance: TipoAlcancePromocion
    # Para TODOS_PRODUCTOS/TODOS_CATEGORIAS el service fuerza este valor a 0;
    # 0 también vale para MEDIO_DE_PAGO ("cualquier medio"). El service valida
    # que la referencia exista para PRODUCTO/CATEGORIA y para MEDIO_DE_PAGO != 0.
    referencia_id: int = Field(default=0, ge=0)


class PromocionDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    nota: str | None = Field(default=None, max_length=500)
    tipo: TipoPromocion
    # Obligatorio si tipo == PORCENTAJE; debe venir None si no (lo valida el
    # service, porque es una regla cruzada entre dos campos).
    porcentaje_descuento: int | None = Field(default=None, ge=1, le=75)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    alcances: list[PromocionAlcanceDatos] = Field(default_factory=list)


class PromocionCrear(PromocionDatos):
    pass


class PromocionEditar(PromocionDatos):
    pass


class PromocionEstado(BaseModel):
    activo: bool


class PromocionAlcanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo_alcance: TipoAlcancePromocion
    referencia_id: int


class PromocionResponse(BaseModel):
    id: int
    nombre: str
    nota: str | None
    tipo: TipoPromocion
    activo: bool
    porcentaje_descuento: int | None
    fecha_inicio: date | None
    fecha_fin: date | None
    alcances: list[PromocionAlcanceResponse]

    @classmethod
    def desde(cls, promocion) -> "PromocionResponse":
        return cls(
            id=promocion.id, nombre=promocion.nombre, nota=promocion.nota, tipo=promocion.tipo,
            activo=promocion.activo, porcentaje_descuento=promocion.porcentaje_descuento,
            fecha_inicio=promocion.fecha_inicio, fecha_fin=promocion.fecha_fin,
            alcances=[PromocionAlcanceResponse.model_validate(a) for a in promocion.alcances],
        )
