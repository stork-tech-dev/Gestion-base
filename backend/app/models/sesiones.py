from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResultadoAcceso(str, Enum):
    EXITOSO = "exitoso"
    FALLIDO = "fallido"


class HistorialAcceso(Base):
    """Intentos de ingreso (append-only en la base). Distinto de la auditoría."""

    __tablename__ = "historial_accesos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    resultado: Mapped[ResultadoAcceso] = mapped_column(
        SAEnum(ResultadoAcceso, name="resultado_acceso", values_callable=lambda e: [i.value for i in e])
    )
    detalle: Mapped[str | None] = mapped_column(String(255))


class Sesion(Base):
    """Refresh token emitido (se guarda solo el jti) con su ventana de inactividad."""

    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
    jti: Mapped[str] = mapped_column(String(64), unique=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime)
    expira_en: Mapped[datetime] = mapped_column(DateTime)  # ventana deslizante de inactividad
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
