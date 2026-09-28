"""Promociones de ventas (sesión 06)."""
from datetime import date, datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.tipos import enum_db


class TipoPromocion(str, Enum):
    DOS_X_UNO = "dos_x_uno"
    TRES_X_DOS = "tres_x_dos"
    PORCENTAJE = "porcentaje"


# Tamaño del grupo y cuántas unidades de ese grupo se pagan, por tipo de promo de grupo.
TAMANO_GRUPO = {TipoPromocion.DOS_X_UNO: 2, TipoPromocion.TRES_X_DOS: 3}
PAGAS_POR_GRUPO = {TipoPromocion.DOS_X_UNO: 1, TipoPromocion.TRES_X_DOS: 2}


class TipoAlcancePromocion(str, Enum):
    PRODUCTO = "producto"
    CATEGORIA = "categoria"
    TODOS_PRODUCTOS = "todos_productos"
    TODOS_CATEGORIAS = "todos_categorias"
    MEDIO_DE_PAGO = "medio_de_pago"


class Promocion(Base):
    __tablename__ = "promociones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    nota: Mapped[str | None] = mapped_column(String(500))
    tipo: Mapped[TipoPromocion] = mapped_column(enum_db(TipoPromocion, "tipo_promocion"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    porcentaje_descuento: Mapped[int | None] = mapped_column(Integer)
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    alcances: Mapped[list["PromocionAlcance"]] = relationship(lazy="selectin", passive_deletes=True)

    def vigente_el(self, dia: date) -> bool:
        return (self.activo and (self.fecha_inicio is None or self.fecha_inicio <= dia)
                and (self.fecha_fin is None or dia <= self.fecha_fin))


class PromocionAlcance(Base):
    __tablename__ = "promocion_alcance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    promocion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("promociones.id", ondelete="CASCADE"))
    tipo_alcance: Mapped[TipoAlcancePromocion] = mapped_column(
        enum_db(TipoAlcancePromocion, "tipo_alcance_promocion")
    )
    # No es FK a propósito: el destino depende de tipo_alcance (producto,
    # categoría o medio de pago). El service valida que exista.
    referencia_id: Mapped[int] = mapped_column(BigInteger)
