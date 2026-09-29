"""Caja: turnos, quiénes trabajan en cada uno, retiros de efectivo y arqueos (sesión 07)."""
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Boolean, Computed, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.medios_pago import MedioDePago
from app.models.tipos import enum_db
from app.models.usuarios import Usuario


class EstadoTurno(str, Enum):
    ABIERTO = "abierto"
    CERRADO = "cerrado"


class Turno(Base):
    """Período de trabajo de la caja. Nunca hay dos abiertos (índice
    uq_turnos_un_abierto). Quién es "el turno abierto" lo responde SOLO
    services.turnos."""

    __tablename__ = "turnos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estado: Mapped[EstadoTurno] = mapped_column(enum_db(EstadoTurno, "estado_turno"), default=EstadoTurno.ABIERTO)
    efectivo_apertura: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    usuario_apertura_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    usuario_cierre_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario_apertura: Mapped[Usuario] = relationship(foreign_keys=[usuario_apertura_id], lazy="joined")
    usuario_cierre: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_cierre_id], lazy="joined")
    participantes: Mapped[list["TurnoUsuario"]] = relationship(
        order_by="(TurnoUsuario.ingreso, TurnoUsuario.id)", lazy="selectin"
    )
    arqueo: Mapped["Arqueo | None"] = relationship(lazy="selectin", uselist=False)


class TurnoUsuario(Base):
    __tablename__ = "turno_usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turno_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("turnos.id", ondelete="RESTRICT"))
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    ingreso: Mapped[datetime] = mapped_column(DateTime)

    usuario: Mapped[Usuario] = relationship(lazy="joined")


class RetiroEfectivo(Base):
    __tablename__ = "retiros_efectivo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turno_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("turnos.id", ondelete="RESTRICT"))
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    motivo: Mapped[str] = mapped_column(String(255))
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)

    usuario: Mapped[Usuario] = relationship(lazy="joined")


class MedioPagoArqueoConfig(Base):
    """Cómo se arquea un medio (fila opcional; sin fila = línea propia, suma)."""

    __tablename__ = "medios_pago_arqueo_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medio_de_pago_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("medios_de_pago.id", ondelete="RESTRICT"), unique=True)
    agrupa_en_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    grupo_terminal: Mapped[str | None] = mapped_column(String(60))
    es_informativo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Arqueo(Base):
    """Cierre de un turno. total_esperado/total_declarado son la foto del
    cierre (las ventas del turno ya no cambian, pero el cálculo sí podría)."""

    __tablename__ = "arqueos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turno_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("turnos.id", ondelete="RESTRICT"), unique=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    total_esperado: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_declarado: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Columna generada por Postgres: nunca se escribe desde Python.
    diferencia: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), Computed("total_declarado - total_esperado", persisted=True))
    notificacion_enviada: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    usuario: Mapped[Usuario] = relationship(lazy="joined")
    items: Mapped[list["ArqueoItem"]] = relationship(order_by="ArqueoItem.id", lazy="selectin")


class ArqueoItem(Base):
    __tablename__ = "arqueo_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    arqueo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("arqueos.id", ondelete="RESTRICT"))
    medio_de_pago_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("medios_de_pago.id", ondelete="RESTRICT"))
    grupo_terminal: Mapped[str | None] = mapped_column(String(60))
    monto_esperado: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    monto_declarado: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    diferencia: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), Computed("monto_declarado - monto_esperado", persisted=True))
    es_informativo: Mapped[bool] = mapped_column(Boolean, default=False)

    medio: Mapped[MedioDePago | None] = relationship(lazy="joined")

    @property
    def nombre(self) -> str:
        return self.grupo_terminal or self.medio.nombre
