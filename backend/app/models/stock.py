"""Stock: movimientos y auditorías de inventario (sesión 05)."""
from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Computed, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.motivo_baja import MotivoBaja
from app.models.productos import Producto
from app.models.tipos import enum_db
from app.models.usuarios import Usuario


class TipoMovimientoStock(str, Enum):
    INGRESO_PROVEEDOR = "ingreso_proveedor"
    VENTA = "venta"
    ANULACION_VENTA = "anulacion_venta"
    BAJA = "baja"
    AJUSTE_AUDITORIA = "ajuste_auditoria"


class EstadoAuditoriaInventario(str, Enum):
    EN_CURSO = "en_curso"
    CERRADA = "cerrada"


class MovimientoStock(Base):
    """Historial append-only de cambios de stock (los errores se corrigen
    con otro movimiento, nunca editando uno existente)."""

    __tablename__ = "movimientos_stock"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[TipoMovimientoStock] = mapped_column(enum_db(TipoMovimientoStock, "tipo_movimiento_stock"))
    producto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("productos.id", ondelete="RESTRICT"))
    cantidad: Mapped[int] = mapped_column(Integer)
    stock_resultante: Mapped[int] = mapped_column(Integer)
    motivo_baja_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("motivos_baja.id", ondelete="RESTRICT"))
    auditoria_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auditorias_inventario.id", ondelete="RESTRICT")
    )
    # La FK a ventas se agrega en la sesión 06.
    referencia_venta_id: Mapped[int | None] = mapped_column(BigInteger)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notas: Mapped[str | None] = mapped_column(Text)

    producto: Mapped[Producto] = relationship(lazy="joined")
    usuario: Mapped[Usuario] = relationship(lazy="joined")
    motivo_baja: Mapped[MotivoBaja | None] = relationship(lazy="joined")


class AuditoriaInventario(Base):
    """Auditoría de inventario (arqueo de stock). Solo puede haber una en
    curso a la vez (UNIQUE INDEX condicional en la base)."""

    __tablename__ = "auditorias_inventario"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    estado: Mapped[EstadoAuditoriaInventario] = mapped_column(
        enum_db(EstadoAuditoriaInventario, "estado_auditoria_inventario"), default=EstadoAuditoriaInventario.EN_CURSO
    )
    # Informativo: no restringe qué productos se pueden auditar.
    filtro_categoria_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT")
    )
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime)
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario: Mapped[Usuario] = relationship(lazy="joined")
    items: Mapped[list["AuditoriaItem"]] = relationship(
        order_by="AuditoriaItem.id", lazy="selectin", passive_deletes=True
    )


class AuditoriaItem(Base):
    """Ítem contado de una auditoría de inventario."""

    __tablename__ = "auditoria_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auditorias_inventario.id", ondelete="CASCADE")
    )
    producto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("productos.id", ondelete="RESTRICT"))
    # Foto del stock al registrar el ítem (no se recalcula si el stock cambia después).
    cantidad_sistema: Mapped[int] = mapped_column(Integer)
    cantidad_contada: Mapped[int] = mapped_column(Integer)
    diferencia: Mapped[int] = mapped_column(Integer, Computed("cantidad_contada - cantidad_sistema", persisted=True))

    producto: Mapped[Producto] = relationship(lazy="joined")
