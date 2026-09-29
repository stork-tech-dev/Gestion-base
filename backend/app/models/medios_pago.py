"""Medios de pago y sus planes de cuotas (sesión 06)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MedioDePago(Base):
    __tablename__ = "medios_de_pago"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    soporta_cuotas: Mapped[bool] = mapped_column(Boolean, default=False)
    # El arqueo lo busca por esta marca, nunca por nombre.
    es_efectivo: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    planes: Mapped[list["PlanCuotas"]] = relationship(
        order_by="(PlanCuotas.cuotas, PlanCuotas.recargo_cliente)", lazy="selectin"
    )


class PlanCuotas(Base):
    __tablename__ = "planes_cuotas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medio_de_pago_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("medios_de_pago.id", ondelete="RESTRICT"))
    cuotas: Mapped[int] = mapped_column(SmallInteger)
    # % que paga el cliente (0 = sin interés).
    recargo_cliente: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # % que cobra la terminal: SOLO reportes, no afecta lo que paga el cliente.
    costo_medio: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    monto_minimo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def disponible_para(self, monto: Decimal) -> bool:
        return self.activo and self.monto_minimo <= monto

    @property
    def sin_interes(self) -> bool:
        return self.recargo_cliente == 0
