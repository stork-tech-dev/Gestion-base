"""Notificaciones para usuarios (sesión 07: diferencia de arqueo)."""
from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tipos import enum_db


class TipoNotificacion(str, Enum):
    DIFERENCIA_ARQUEO = "diferencia_arqueo"


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    tipo: Mapped[TipoNotificacion] = mapped_column(enum_db(TipoNotificacion, "tipo_notificacion"))
    titulo: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    # `metadata` está reservado por SQLAlchemy en los modelos declarativos.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
