from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, and_, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.utils import redondear
from app.models.proveedores import Moneda, Proveedor
from app.models.tipos import enum_db

NIVEL_MAXIMO = 5


class TemporadaProducto(str, Enum):
    ATEMPORAL = "atemporal"
    OTONO_INVIERNO = "otoño_invierno"
    PRIMAVERA_VERANO = "primavera_verano"


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    # Desnormalizado a propósito: se deduce del padre, pero guardarlo permite
    # el CHECK 1..5 y filtrar por nivel sin recorrer el árbol. Mover una
    # categoría actualiza el nivel de toda su rama.
    nivel: Mapped[int] = mapped_column(SmallInteger)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(5))
    # Módulo 11 sobre el SKU; se calcula una sola vez al crear y nunca cambia.
    verificador: Mapped[str] = mapped_column(String(1))
    sku_proveedor: Mapped[str | None] = mapped_column(String(30))
    descripcion: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"))
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedores.id", ondelete="RESTRICT"))
    # En la moneda del proveedor (no cambia: el proveedor del producto no se edita
    # y la moneda de un proveedor con productos tampoco).
    costo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    margen: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    # Desnormalizado (en pesos): CEIL(costo × dólar (o 1) × (1 + margen/100), redondeo).
    # Se guarda para listar/filtrar/vender sin recalcular; se recalcula en cascada
    # al cambiar el dólar del proveedor y al editar costo o margen.
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    descuento_producto: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    peso_gramos: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    temporada: Mapped[TemporadaProducto] = mapped_column(
        enum_db(TemporadaProducto, "temporada_producto"), default=TemporadaProducto.ATEMPORAL
    )
    ubicacion_deposito: Mapped[str | None] = mapped_column(String(100))
    stock_infinito: Mapped[bool] = mapped_column(Boolean, default=False)
    # Desnormalizado a propósito (campo calculable desde movimientos_stock):
    # se guarda para listar/filtrar/vender sin sumar el historial. SOLO lo
    # escribe services.stock.aplicar_movimiento (bloquea la fila).
    stock: Mapped[int] = mapped_column(Integer, default=0)
    stock_minimo: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    categoria: Mapped[Categoria] = relationship(lazy="joined")
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    fotos: Mapped[list["ProductoFoto"]] = relationship(
        order_by="(ProductoFoto.orden, ProductoFoto.id)", lazy="selectin", passive_deletes=True
    )

    @property
    def codigo_con_verificador(self) -> str:
        return f"{self.sku}{self.verificador}"

    @property
    def moneda(self) -> Moneda:
        return self.proveedor.moneda

    @property
    def foto_principal_url(self) -> str | None:
        principal = next((f for f in self.fotos if f.es_principal), None)
        foto = principal or (self.fotos[0] if self.fotos else None)
        return foto.url if foto else None

    @property
    def costo_en_pesos(self) -> Decimal:
        """Sin CEIL: la venta lo congela para la rentabilidad."""
        if self.proveedor.moneda is Moneda.USD:
            return redondear(self.costo * self.proveedor.dolar_actual)
        return redondear(self.costo)

    @property
    def bajo_minimo(self) -> bool:
        return self.stock_minimo > 0 and self.stock <= self.stock_minimo


# Expresión SQLAlchemy equivalente a Producto.bajo_minimo, para usar en filtros
# (WHERE) donde no hay una instancia Python sobre la que evaluar la propiedad.
BAJO_MINIMO_SQL = and_(Producto.stock_minimo > 0, Producto.stock <= Producto.stock_minimo)


class ProductoFoto(Base):
    __tablename__ = "producto_fotos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    producto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("productos.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(255))
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
