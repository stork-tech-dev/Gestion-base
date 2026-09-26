from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.permisos import ROL_ADMIN


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(150))
    rol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id", ondelete="RESTRICT"))
    rol: Mapped[Rol] = relationship(lazy="joined")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    celular: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime)  # NULL = debe cambiar la contraseña

    @property
    def debe_cambiar_password(self) -> bool:
        return self.ultimo_acceso is None

    @property
    def es_admin(self) -> bool:
        return self.rol is not None and self.rol.nombre == ROL_ADMIN
