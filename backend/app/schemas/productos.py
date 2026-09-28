from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Moneda, TemporadaProducto

# Topes = columnas NUMERIC: un valor enorme es 422, nunca un 500 de la base.
Costo = Field(gt=0, lt=Decimal("100000000"), decimal_places=2)


class ProductoDatos(BaseModel):
    categoria_id: int
    descripcion: str = Field(min_length=1, max_length=500)
    costo: Decimal = Costo
    sku_proveedor: str | None = Field(default=None, max_length=30)
    descuento_producto: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    peso_gramos: Decimal | None = Field(default=None, gt=0, lt=Decimal("1000000"), decimal_places=2)
    temporada: TemporadaProducto = TemporadaProducto.ATEMPORAL
    ubicacion_deposito: str | None = Field(default=None, max_length=100)
    stock_infinito: bool = False


class ProductoCrear(ProductoDatos):
    proveedor_id: int
    margen: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=2)   # None → margen_default


class ProductoEditar(ProductoDatos):
    # SKU, verificador y proveedor no se editan.
    margen: Decimal = Field(ge=0, le=1000, decimal_places=2)
    # None = no cambia (un cliente que omite el campo no apaga el stock infinito).
    stock_infinito: bool | None = None


class ProductoEstado(BaseModel):
    activo: bool


class CategoriaResumen(BaseModel):
    id: int
    nombre: str
    camino: str


class ProveedorResumen(BaseModel):
    id: int
    nombre: str
    moneda: Moneda


class FotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    es_principal: bool
    orden: int


class ProductoResponse(BaseModel):
    id: int
    sku: str
    verificador: str
    codigo_con_verificador: str
    sku_proveedor: str | None
    descripcion: str
    categoria: CategoriaResumen
    proveedor: ProveedorResumen
    moneda: Moneda
    costo: Decimal
    margen: Decimal
    precio_venta: Decimal
    descuento_producto: Decimal
    peso_gramos: Decimal | None
    temporada: TemporadaProducto
    ubicacion_deposito: str | None
    stock_infinito: bool
    activo: bool
    foto_url: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def _campos(cls, producto, camino: str) -> dict:
        return dict(
            id=producto.id, sku=producto.sku, verificador=producto.verificador,
            codigo_con_verificador=producto.codigo_con_verificador, sku_proveedor=producto.sku_proveedor,
            descripcion=producto.descripcion,
            categoria=CategoriaResumen(id=producto.categoria.id, nombre=producto.categoria.nombre, camino=camino),
            proveedor=ProveedorResumen(id=producto.proveedor.id, nombre=producto.proveedor.nombre,
                                       moneda=producto.proveedor.moneda),
            moneda=producto.moneda, costo=producto.costo, margen=producto.margen,
            precio_venta=producto.precio_venta, descuento_producto=producto.descuento_producto,
            peso_gramos=producto.peso_gramos, temporada=producto.temporada,
            ubicacion_deposito=producto.ubicacion_deposito, stock_infinito=producto.stock_infinito,
            activo=producto.activo, foto_url=producto.foto_principal_url,
            created_at=producto.created_at, updated_at=producto.updated_at,
        )

    @classmethod
    def desde(cls, producto, camino: str) -> "ProductoResponse":
        return cls(**cls._campos(producto, camino))


class ProductoDetalle(ProductoResponse):
    fotos: list[FotoResponse]

    @classmethod
    def desde(cls, producto, camino: str) -> "ProductoDetalle":
        return cls(**cls._campos(producto, camino), fotos=[FotoResponse.model_validate(f) for f in producto.fotos])


class PrecioPreview(BaseModel):
    moneda: Moneda
    dolar_proveedor: Decimal | None
    precio_venta: Decimal


class Similar(BaseModel):
    id: int
    sku: str
    descripcion: str
    activo: bool


class ItemEtiqueta(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1, le=1000)


class PedidoEtiquetas(BaseModel):
    items: list[ItemEtiqueta] = Field(min_length=1, max_length=200)
    tipo: Literal["rectangular", "colita"]
