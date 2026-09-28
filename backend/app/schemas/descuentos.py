"""Esquemas de motivos de descuento en ventas (sesión 06)."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class MotivoDescuentoDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    nota: str | None = Field(default=None, max_length=500)
    # NULL = quien vende elige el porcentaje al confirmar (services.descuentos.resolver_porcentaje).
    porcentaje_sugerido: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    habilita_cuotas_sin_interes: bool = False
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    # Vacío = todos los medios (services.descuentos._sincronizar_medios).
    medio_de_pago_ids: list[int] = Field(default_factory=list)

    @field_validator("medio_de_pago_ids")
    @classmethod
    def _sin_repetidos(cls, valor: list[int]) -> list[int]:
        if len(valor) != len(set(valor)):
            raise ValueError("Los medios de pago no pueden repetirse")
        return valor


class MotivoDescuentoCrear(MotivoDescuentoDatos):
    pass


class MotivoDescuentoEditar(MotivoDescuentoDatos):
    pass


class MotivoDescuentoEstado(BaseModel):
    activo: bool


class MotivoDescuentoResponse(BaseModel):
    id: int
    nombre: str
    nota: str | None
    porcentaje_sugerido: Decimal | None
    habilita_cuotas_sin_interes: bool
    activo: bool
    fecha_inicio: date | None
    fecha_fin: date | None
    medio_de_pago_ids: list[int]

    @classmethod
    def desde(cls, motivo) -> "MotivoDescuentoResponse":
        return cls(
            id=motivo.id, nombre=motivo.nombre, nota=motivo.nota,
            porcentaje_sugerido=motivo.porcentaje_sugerido,
            habilita_cuotas_sin_interes=motivo.habilita_cuotas_sin_interes, activo=motivo.activo,
            fecha_inicio=motivo.fecha_inicio, fecha_fin=motivo.fecha_fin,
            medio_de_pago_ids=[m.id for m in motivo.medios],
        )
