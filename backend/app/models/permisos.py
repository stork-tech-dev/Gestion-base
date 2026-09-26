from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ColumnasPermiso:
    """Columnas comunes a rol_permisos y usuario_permisos (una sola definición)."""

    modulo: Mapped[str] = mapped_column(String(50))
    recurso: Mapped[str | None] = mapped_column(String(100))  # NULL = módulo completo
    puede_ver: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_crear: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_editar: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_eliminar: Mapped[bool] = mapped_column(Boolean, default=False)

    def puede(self, accion: str) -> bool:
        return bool(getattr(self, f"puede_{accion}"))


class RolPermiso(ColumnasPermiso, Base):
    __tablename__ = "rol_permisos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id", ondelete="CASCADE"))


class UsuarioPermiso(ColumnasPermiso, Base):
    """Overrides individuales: siempre aditivos (OR con los del rol)."""

    __tablename__ = "usuario_permisos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
