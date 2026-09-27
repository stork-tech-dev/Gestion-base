from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import EstadoProveedor, Moneda, OrigenCambioDolar

Dolar = Decimal  # alias documental: valor del dólar en pesos, 2 decimales
# Los campos de dólar no llevan `max_digits`: el tope (NUMERIC(10, 2)) lo
# aplica `services.proveedores.validar_dolar` sobre el valor redondeado, con
# un 400 y un mensaje claro, igual que para el masivo y el Excel.


class ProveedorDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    pais: str | None = Field(default=None, max_length=200)
    provincia: str | None = Field(default=None, max_length=255)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    notas: str | None = Field(default=None, max_length=2000)


class ProveedorCrear(ProveedorDatos):
    moneda: Moneda = Moneda.ARS
    dolar_actual: Dolar | None = Field(default=None, gt=0, decimal_places=3)


class ProveedorEditar(ProveedorDatos):
    moneda: Moneda
    # Solo se usa al pasar de pesos a dólares: la edición no cambia el dólar.
    dolar_actual: Dolar | None = Field(default=None, gt=0, decimal_places=3)


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


class ProveedorDolarResumen(BaseModel):
    """Versión mínima de ProveedorResponse para GET /dolar/activos: quien solo
    tiene el permiso puntual del cambio masivo (sin "ver" proveedores) no debe
    recibir datos de contacto (email, teléfono, notas, país, provincia)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    dolar_actual: Decimal


class CambioDolar(BaseModel):
    valor_nuevo: Dolar = Field(gt=0, decimal_places=3)


class ModalidadMasiva(str, Enum):
    VALOR = "valor"          # el mismo valor para todos
    PORCENTAJE = "porcentaje"  # sobre el dólar de cada uno


class CambioMasivo(BaseModel):
    proveedor_ids: list[int] | None = None  # None = todos los activos en dólares
    modalidad: ModalidadMasiva
    valor: Decimal = Field(max_digits=10, decimal_places=3)


class PreviewDolar(BaseModel):
    proveedor_id: int
    nombre: str
    valor_actual: Decimal
    valor_nuevo: Decimal
    aplicado: bool = False  # siempre False en la vista previa; al aplicar, True si el dólar cambió


class HistorialDolarResponse(BaseModel):
    id: int
    valor_anterior: Decimal
    valor_nuevo: Decimal
    origen: OrigenCambioDolar
    timestamp: datetime
    usuario_id: int
    usuario_nombre: str


class ErrorFila(BaseModel):
    fila: int
    error: str


class ResultadoImportacionDolar(BaseModel):
    aplicados: int
    sin_cambios: int
    errores: list[ErrorFila]


class DolarEnUso(BaseModel):
    hay_proveedores_en_dolares: bool
