"""Motivos de descuento en ventas (sesión 06)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.medios_pago import MedioDePago

# Asociación motivo <-> medios de pago habilitados (vacío = todos los medios).
motivo_medios_pago = Table(
    "motivo_medios_pago",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("motivo_id", BigInteger, ForeignKey("motivos_descuento.id", ondelete="CASCADE"), nullable=False),
    Column("medio_de_pago_id", BigInteger, ForeignKey("medios_de_pago.id", ondelete="RESTRICT"), nullable=False),
)


class MotivoDescuento(Base):
    __tablename__ = "motivos_descuento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    nota: Mapped[str | None] = mapped_column(String(500))
    porcentaje_sugerido: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))   # NULL = quien vende elige
    habilita_cuotas_sin_interes: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    medios: Mapped[list[MedioDePago]] = relationship(secondary=motivo_medios_pago, lazy="selectin")
