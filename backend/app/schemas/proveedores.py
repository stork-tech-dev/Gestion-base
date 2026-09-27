from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import EstadoProveedor, Moneda

Dolar = Decimal  # alias documental: valor del dólar en pesos, 2 decimales


class ProveedorDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    pais: str | None = Field(default=None, max_length=200)
    provincia: str | None = Field(default=None, max_length=255)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    notas: str | None = Field(default=None, max_length=2000)


class ProveedorCrear(ProveedorDatos):
    moneda: Moneda = Moneda.ARS
    dolar_actual: Dolar | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)


class ProveedorEditar(ProveedorDatos):
    moneda: Moneda
    # Solo se usa al pasar de pesos a dólares: la edición no cambia el dólar.
    dolar_actual: Dolar | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)


class ProveedorEstado(BaseModel):
    estado: EstadoProveedor
    confirmar_con_productos: bool = False


class ProveedorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    pais: str | None
    provincia: str | None
    telefono: str | None
    email: str | None
    notas: str | None
    estado: EstadoProveedor
    moneda: Moneda
    dolar_actual: Decimal | None
    activo: bool
    en_dolares: bool
    created_at: datetime
    updated_at: datetime
