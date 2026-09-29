"""Esquemas de medios de pago y sus planes de cuotas (sesión 06)."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MedioDePagoDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    soporta_cuotas: bool = False
    es_efectivo: bool = False


class MedioDePagoCrear(MedioDePagoDatos):
    pass


class MedioDePagoEditar(MedioDePagoDatos):
    pass


class MedioDePagoEstado(BaseModel):
    activo: bool


class PlanCuotasDatos(BaseModel):
    cuotas: int = Field(ge=1, le=60)
    recargo_cliente: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    # SOLO para reportes: nunca se usa para calcular lo que paga el cliente
    # (ver services.medios_pago.calcular_recargo).
    costo_medio: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    monto_minimo: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999.99"), decimal_places=2)


class PlanCuotasCrear(PlanCuotasDatos):
    pass


class PlanCuotasEditar(PlanCuotasDatos):
    pass


class PlanCuotasEstado(BaseModel):
    activo: bool


class PlanCuotasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medio_de_pago_id: int
    cuotas: int
    recargo_cliente: Decimal
    costo_medio: Decimal
    monto_minimo: Decimal
    activo: bool


class MedioDePagoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    soporta_cuotas: bool
    es_efectivo: bool
    activo: bool
    planes: list[PlanCuotasResponse]
