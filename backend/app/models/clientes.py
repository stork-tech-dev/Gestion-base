"""Clientes de ventas (sesión 06)."""
from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tipos import enum_db


class CondicionIva(str, Enum):
    CONSUMIDOR_FINAL = "consumidor_final"
    RESPONSABLE_INSCRIPTO = "responsable_inscripto"
    MONOTRIBUTISTA = "monotributista"
    EXENTO = "exento"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))   # nombre o razón social
    dni: Mapped[str | None] = mapped_column(String(15), unique=True)   # solo dígitos
    # cuit y condicion_iva no se usan hoy en ningún cálculo: quedan cargados
    # para la futura facturación electrónica. Solo dígitos, verificador
    # válido (lo valida el service).
    cuit: Mapped[str | None] = mapped_column(String(11), unique=True)
    condicion_iva: Mapped[CondicionIva] = mapped_column(
        enum_db(CondicionIva, "condicion_iva"), default=CondicionIva.CONSUMIDOR_FINAL
    )
    domicilio: Mapped[str | None] = mapped_column(String(200))
    codigo_postal: Mapped[str | None] = mapped_column(String(10))
    localidad: Mapped[str | None] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(150))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ClientePromocion(Base):
    """Promociones exclusivas de ciertos clientes."""

    __tablename__ = "cliente_promociones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clientes.id", ondelete="RESTRICT"))
    promocion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("promociones.id", ondelete="CASCADE"))
