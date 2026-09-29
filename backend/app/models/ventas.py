"""Ventas: encabezado, ítems y pagos (sesión 06)."""
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.clientes import Cliente
from app.models.descuentos import MotivoDescuento
from app.models.medios_pago import MedioDePago, PlanCuotas
from app.models.productos import Producto
from app.models.promociones import Promocion
from app.models.tipos import enum_db
from app.models.usuarios import Usuario


class EstadoVenta(str, Enum):
    EN_CURSO = "en_curso"
    CONFIRMADA = "confirmada"
    ANULADA = "anulada"


class Venta(Base):
    """Encabezado de una venta.

    subtotal, descuento_total, recargo_total y total desnormalizados a
    propósito: son la foto del cierre; se recalculan mientras está en_curso
    y se congelan al confirmar.
    """

    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    numero: Mapped[str] = mapped_column(String(12), unique=True)
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("clientes.id", ondelete="RESTRICT"))
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    estado: Mapped[EstadoVenta] = mapped_column(enum_db(EstadoVenta, "estado_venta"), default=EstadoVenta.EN_CURSO)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    descuento_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    recargo_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    codigo_cambio: Mapped[str | None] = mapped_column(String(8), unique=True)
    promocion_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("promociones.id", ondelete="RESTRICT"))
    # La eligió quien vende: dura hasta el próximo cambio del carrito.
    promocion_a_mano: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmada_en: Mapped[datetime | None] = mapped_column(DateTime)
    turno_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("turnos.id", ondelete="RESTRICT"))
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime)
    anulada_por_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(500))
    turno_anulacion_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("turnos.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    cliente: Mapped[Cliente | None] = relationship(lazy="joined")
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")
    anulada_por: Mapped[Usuario | None] = relationship(foreign_keys=[anulada_por_id], lazy="joined")
    promocion: Mapped[Promocion | None] = relationship(lazy="joined")
    items: Mapped[list["VentaItem"]] = relationship(
        order_by="VentaItem.orden", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )
    pagos: Mapped[list["VentaPago"]] = relationship(
        order_by="VentaPago.id", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def cobrable(self) -> Decimal:
        return self.total - self.recargo_total


class VentaItem(Base):
    """Una fila por UNIDAD. precio_lista, precio_unitario y costo_unitario son
    la foto del momento de la venta (precio, costo y dólar cambian)."""

    __tablename__ = "venta_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    venta_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ventas.id", ondelete="CASCADE"))
    producto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("productos.id", ondelete="RESTRICT"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    precio_lista: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    costo_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    descuento_item: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    motivo_descuento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("motivos_descuento.id", ondelete="RESTRICT")
    )
    porcentaje_modificado: Mapped[bool] = mapped_column(Boolean, default=False)
    precio_final: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    en_promocion: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(SmallInteger)

    producto: Mapped[Producto] = relationship(lazy="joined")
    motivo_descuento: Mapped[MotivoDescuento | None] = relationship(lazy="joined")


class VentaPago(Base):
    __tablename__ = "venta_pagos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    venta_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ventas.id", ondelete="CASCADE"))
    medio_de_pago_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("medios_de_pago.id", ondelete="RESTRICT"))
    plan_cuotas_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("planes_cuotas.id", ondelete="RESTRICT")
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2))   # antes del recargo
    recargo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    monto_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    medio_de_pago: Mapped[MedioDePago] = relationship(lazy="joined")
    plan_cuotas: Mapped[PlanCuotas | None] = relationship(lazy="joined")
