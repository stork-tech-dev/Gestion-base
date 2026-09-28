"""Esquemas de stock: ingresos, mínimos y las respuestas de listado/movimientos."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import TipoMovimientoStock


class IngresoCrear(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1, le=1_000_000)
    notas: str | None = Field(default=None, max_length=500)


class MinimoEditar(BaseModel):
    stock_minimo: int = Field(ge=0, le=1_000_000)


class StockResponse(BaseModel):
    producto_id: int
    codigo: str
    descripcion: str
    categoria: str
    proveedor: str
    stock: int
    stock_minimo: int
    bajo_minimo: bool
    stock_infinito: bool
    foto_url: str | None

    @classmethod
    def desde(cls, producto, camino: str) -> "StockResponse":
        return cls(
            producto_id=producto.id, codigo=producto.codigo_con_verificador, descripcion=producto.descripcion,
            categoria=camino, proveedor=producto.proveedor.nombre, stock=producto.stock,
            stock_minimo=producto.stock_minimo, bajo_minimo=producto.bajo_minimo,
            stock_infinito=producto.stock_infinito, foto_url=producto.foto_principal_url,
        )


class ResumenStock(BaseModel):
    productos_con_stock: int
    unidades: int
    valorizado: Decimal
    bajo_minimo: int


class MovimientoResponse(BaseModel):
    id: int
    tipo: TipoMovimientoStock
    producto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    stock_resultante: int
    motivo_baja: str | None
    auditoria_id: int | None
    referencia_venta_id: int | None
    usuario_id: int
    usuario_nombre: str
    timestamp: datetime
    notas: str | None

    @classmethod
    def desde(cls, m) -> "MovimientoResponse":
        return cls(
            id=m.id, tipo=m.tipo, producto_id=m.producto_id, codigo=m.producto.codigo_con_verificador,
            descripcion=m.producto.descripcion, cantidad=m.cantidad, stock_resultante=m.stock_resultante,
            motivo_baja=m.motivo_baja.nombre if m.motivo_baja else None, auditoria_id=m.auditoria_id,
            referencia_venta_id=m.referencia_venta_id, usuario_id=m.usuario_id, usuario_nombre=m.usuario.nombre,
            timestamp=m.timestamp, notas=m.notas,
        )
