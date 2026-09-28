"""Esquemas de clientes (sesión 06). El email es opcional: se valida con
EmailStr si `email-validator` está instalado (está en requirements.txt); si
por algún motivo no lo está, se usa un patrón simple para no romper el alta."""
import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import CondicionIva, TipoPromocion

try:
    from pydantic import EmailStr as _Email
except ImportError:  # pragma: no cover - depende de si está instalado email-validator
    _PATRON_EMAIL_SIMPLE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _validar_email_simple(valor: str) -> str:
        if not _PATRON_EMAIL_SIMPLE.match(valor):
            raise ValueError("Email inválido")
        return valor

    _Email = Annotated[str, AfterValidator(_validar_email_simple)]


class ClienteDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    # Se limpian a solo dígitos en el service (clientes.solo_digitos): acá se
    # acepta cualquier formato ("20-39059158-1") y se valida largo/verificador allá.
    dni: str | None = Field(default=None, max_length=15)
    cuit: str | None = Field(default=None, max_length=15)
    condicion_iva: CondicionIva = CondicionIva.CONSUMIDOR_FINAL
    domicilio: str | None = Field(default=None, max_length=200)
    codigo_postal: str | None = Field(default=None, max_length=10)
    localidad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    email: _Email | None = Field(default=None, max_length=150)


class ClienteCrear(ClienteDatos):
    pass


class ClienteEditar(ClienteDatos):
    pass


class ClienteEstado(BaseModel):
    activo: bool


class ClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    dni: str | None
    cuit: str | None
    condicion_iva: CondicionIva
    domicilio: str | None
    codigo_postal: str | None
    localidad: str | None
    telefono: str | None
    email: str | None
    activo: bool


class ClientePromocionAsignar(BaseModel):
    promocion_id: int


class PromocionDeCliente(BaseModel):
    id: int
    nombre: str
    tipo: TipoPromocion
    vigente: bool


class ClienteFicha(BaseModel):
    """`services.clientes.ficha` + vigencia de cada promoción exclusiva
    (calculada acá para no depender de que el llamador la calcule bien)."""

    cliente: ClienteResponse
    promociones: list[PromocionDeCliente]
    compras_cantidad: int
    compras_total: Decimal

    @classmethod
    def desde(cls, datos: dict, hoy: date) -> "ClienteFicha":
        return cls(
            cliente=ClienteResponse.model_validate(datos["cliente"]),
            promociones=[PromocionDeCliente(id=p.id, nombre=p.nombre, tipo=p.tipo, vigente=p.vigente_el(hoy))
                        for p in datos["promociones"]],
            compras_cantidad=datos["compras_cantidad"],
            compras_total=datos["compras_total"],
        )
