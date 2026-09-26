from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConfiguracionSistema(Base):
    """Fila única con los parámetros comerciales del sistema."""

    __tablename__ = "configuracion_sistema"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    redondeo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    margen_default: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    descuento_maximo: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    tope_descuento_venta: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
