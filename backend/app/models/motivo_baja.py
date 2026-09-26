from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MotivoBaja(Base):
    """Catálogo de motivos de baja de stock (lo usa la sesión 05)."""

    __tablename__ = "motivos_baja"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
