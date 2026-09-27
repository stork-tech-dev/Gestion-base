from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tipos import enum_db


class EstadoProveedor(str, Enum):
    # Tres estados en lugar de un booleano: "desactivado" se reactiva
    # libremente; "inhabilitado" solo con Admin.
    ACTIVO = "activo"
    DESACTIVADO = "desactivado"
    INHABILITADO = "inhabilitado"


class Moneda(str, Enum):
    ARS = "ars"
    USD = "usd"


class OrigenCambioDolar(str, Enum):
    MANUAL = "manual"
    MASIVO_VALOR = "masivo_valor"
    MASIVO_PORCENTAJE = "masivo_porcentaje"
    IMPORTACION_EXCEL = "importacion_excel"


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    pais: Mapped[str | None] = mapped_column(String(200))
    provincia: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoProveedor] = mapped_column(enum_db(EstadoProveedor, "estado_proveedor"), default=EstadoProveedor.ACTIVO)
    moneda: Mapped[Moneda] = mapped_column(enum_db(Moneda, "moneda"), default=Moneda.ARS)
    # Solo proveedores en dólares (CHECK en la base).
    dolar_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def activo(self) -> bool:
        return self.estado is EstadoProveedor.ACTIVO

    @property
    def en_dolares(self) -> bool:
        return self.moneda is Moneda.USD


class ProveedorDolarHistorial(Base):
    """Cada cambio real del dólar de un proveedor (append-only en la base)."""

    __tablename__ = "proveedor_dolar_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedores.id", ondelete="CASCADE"))
    valor_anterior: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    valor_nuevo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    origen: Mapped[OrigenCambioDolar] = mapped_column(enum_db(OrigenCambioDolar, "origen_cambio_dolar"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
