from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Auditoria(Base):
    """Registro append-only (la base rechaza UPDATE/DELETE/TRUNCATE)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Sin FK a usuarios a propósito: la auditoría debe sobrevivir al usuario.
    usuario_id: Mapped[int | None] = mapped_column(BigInteger)
    accion: Mapped[str] = mapped_column(String(100))
    entidad: Mapped[str] = mapped_column(String(100))
    entidad_id: Mapped[int | None] = mapped_column(BigInteger)
    estado_anterior: Mapped[dict | None] = mapped_column(JSONB)
    estado_nuevo: Mapped[dict | None] = mapped_column(JSONB)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
