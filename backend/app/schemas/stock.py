"""Esquemas de stock: ingresos, mínimos, motivos y bajas, auditorías de
inventario (conteos), y las respuestas de listado/movimientos."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import EstadoAuditoriaInventario, TipoMovimientoStock


class IngresoCrear(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1, le=1_000_000)
    notas: str | None = Field(default=None, max_length=500)


class MinimoEditar(BaseModel):
    stock_minimo: int = Field(ge=0, le=1_000_000)


class MotivoBajaCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class MotivoBajaEditar(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    activo: bool


class MotivoBajaResponse(BaseModel):
    id: int
    nombre: str
    activo: bool

    @classmethod
    def desde(cls, motivo) -> "MotivoBajaResponse":
        return cls(id=motivo.id, nombre=motivo.nombre, activo=motivo.activo)


class BajaCrear(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1, le=1_000_000)
    motivo_baja_id: int
    notas: str | None = Field(default=None, max_length=500)


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


class AuditoriaIniciar(BaseModel):
    filtro_categoria_id: int | None = None
    notas: str | None = Field(default=None, max_length=500)


class ItemContado(BaseModel):
    producto_id: int
    cantidad_contada: int = Field(ge=0, le=1_000_000)


class ItemsRegistrar(BaseModel):
    items: list[ItemContado] = Field(min_length=1, max_length=500)


class ItemEditar(BaseModel):
    cantidad_contada: int = Field(ge=0, le=1_000_000)


class ItemPorCodigo(BaseModel):
    """Registrar un ítem contado escaneando o tipeando el código (SKU o
    etiqueta con verificador) en vez de mandar el `producto_id`."""
    codigo: str = Field(min_length=1, max_length=20)
    cantidad_contada: int = Field(ge=0, le=1_000_000)


class AuditoriaItemResponse(BaseModel):
    id: int
    producto_id: int
    codigo: str
    descripcion: str
    cantidad_sistema: int
    cantidad_contada: int
    diferencia: int

    @classmethod
    def desde(cls, item) -> "AuditoriaItemResponse":
        return cls(
            id=item.id, producto_id=item.producto_id, codigo=item.producto.codigo_con_verificador,
            descripcion=item.producto.descripcion, cantidad_sistema=item.cantidad_sistema,
            cantidad_contada=item.cantidad_contada, diferencia=item.diferencia,
        )


class AuditoriaResponse(BaseModel):
    id: int
    estado: EstadoAuditoriaInventario
    usuario_id: int
    usuario_nombre: str
    filtro_categoria_id: int | None
    fecha_inicio: datetime
    fecha_fin: datetime | None
    notas: str | None
    cantidad_items: int

    @classmethod
    def desde(cls, auditoria) -> "AuditoriaResponse":
        return cls(
            id=auditoria.id, estado=auditoria.estado, usuario_id=auditoria.usuario_id,
            usuario_nombre=auditoria.usuario.nombre, filtro_categoria_id=auditoria.filtro_categoria_id,
            fecha_inicio=auditoria.fecha_inicio, fecha_fin=auditoria.fecha_fin, notas=auditoria.notas,
            cantidad_items=len(auditoria.items),
        )


class AuditoriaDetalle(AuditoriaResponse):
    items: list[AuditoriaItemResponse]

    @classmethod
    def desde(cls, auditoria) -> "AuditoriaDetalle":
        base = AuditoriaResponse.desde(auditoria)
        return cls(**base.model_dump(), items=[AuditoriaItemResponse.desde(i) for i in auditoria.items])
