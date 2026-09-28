"""Esquemas de ventas (sesión 06): requests del carrito y respuestas.

`costo_unitario` NUNCA aparece en ninguna respuesta de /api/v1/ventas: es la
foto del costo para Reportes, no para la pantalla de venta."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import CondicionIva, EstadoVenta, TipoPromocion
from app.services.descuentos import aplicar_descuentos, calcular_descuento_total

# Tope de las columnas NUMERIC(10,2): un monto enorme es 422, nunca un 500.
MONTO_MAXIMO = Decimal("99999999.99")


# --- Requests -----------------------------------------------------------------

class ItemAgregar(BaseModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    producto_id: int | None = None


class ClienteAsociar(BaseModel):
    cliente_id: int | None = None


class DescuentoAplicar(BaseModel):
    item_id: int
    motivo_id: int | None = None
    # Entero con límites: un valor raro es 422 acá, nunca un 500 en
    # descuentos.validar_porcentaje (que hace Decimal(str(p)) / int(...)).
    porcentaje: int | None = Field(default=None, ge=1, le=100)


class PromocionElegir(BaseModel):
    promocion_id: int | None = None


class PagoDatos(BaseModel):
    medio_de_pago_id: int
    # Solo cuenta el del primero de dos pagos: el del único pago y el del
    # segundo los fija el backend (lo cobrable / el resto).
    monto: Decimal = Field(gt=0, le=MONTO_MAXIMO, decimal_places=2)
    plan_cuotas_id: int | None = None


class PagosRegistrar(BaseModel):
    pagos: list[PagoDatos] = Field(default_factory=list, max_length=2)


class ConfirmarVenta(BaseModel):
    total_esperado: Decimal = Field(ge=0, le=MONTO_MAXIMO, decimal_places=2)


class AnularVenta(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


# --- Respuestas ------------------------------------------------------------------

class Referencia(BaseModel):
    id: int
    nombre: str

    @classmethod
    def de(cls, obj) -> "Referencia | None":
        return cls(id=obj.id, nombre=obj.nombre) if obj is not None else None


class ClienteDeVenta(BaseModel):
    id: int
    nombre: str
    condicion_iva: CondicionIva


class PlanDePago(BaseModel):
    id: int
    cuotas: int
    recargo_cliente: Decimal


class VentaItemResponse(BaseModel):
    id: int
    producto_id: int
    codigo: str
    descripcion: str
    categoria: str
    foto_url: str | None
    precio_lista: Decimal
    precio_unitario: Decimal
    descuento_item: Decimal
    descuento_efectivo: Decimal
    motivo: Referencia | None
    porcentaje_modificado: bool
    precio_final: Decimal
    en_promocion: bool
    orden: int

    @classmethod
    def desde(cls, item, camino: str) -> "VentaItemResponse":
        producto = item.producto
        return cls(
            id=item.id, producto_id=item.producto_id, codigo=producto.codigo_con_verificador,
            descripcion=producto.descripcion, categoria=camino, foto_url=producto.foto_principal_url,
            precio_lista=item.precio_lista, precio_unitario=item.precio_unitario,
            descuento_item=item.descuento_item,
            descuento_efectivo=calcular_descuento_total(producto.descuento_producto, item.descuento_item),
            motivo=Referencia.de(item.motivo_descuento), porcentaje_modificado=item.porcentaje_modificado,
            precio_final=item.precio_final, en_promocion=item.en_promocion, orden=item.orden,
        )


class VentaPagoResponse(BaseModel):
    id: int
    medio: Referencia
    plan: PlanDePago | None
    monto: Decimal
    recargo: Decimal
    monto_total: Decimal

    @classmethod
    def desde(cls, pago) -> "VentaPagoResponse":
        plan = pago.plan_cuotas
        return cls(
            id=pago.id, medio=Referencia.de(pago.medio_de_pago),
            plan=PlanDePago(id=plan.id, cuotas=plan.cuotas, recargo_cliente=plan.recargo_cliente) if plan else None,
            monto=pago.monto, recargo=pago.recargo, monto_total=pago.monto_total,
        )


class VentaResponse(BaseModel):
    id: int
    numero: str
    estado: EstadoVenta
    cliente: ClienteDeVenta | None
    usuario: Referencia
    items: list[VentaItemResponse]
    pagos: list[VentaPagoResponse]
    subtotal: Decimal
    descuento_total: Decimal
    recargo_total: Decimal
    total: Decimal
    cobrable: Decimal
    promocion: Referencia | None
    promocion_a_mano: bool
    codigo_cambio: str | None
    confirmada_en: datetime | None
    created_at: datetime
    anulada_en: datetime | None
    anulada_por: Referencia | None
    motivo_anulacion: str | None

    @classmethod
    def desde(cls, venta, caminos: dict[int, str]) -> "VentaResponse":
        """`caminos` = services.categorias.caminos(db) (una sola lectura por respuesta)."""
        cliente = venta.cliente
        return cls(
            id=venta.id, numero=venta.numero, estado=venta.estado,
            cliente=(ClienteDeVenta(id=cliente.id, nombre=cliente.nombre, condicion_iva=cliente.condicion_iva)
                     if cliente else None),
            usuario=Referencia.de(venta.usuario),
            items=[VentaItemResponse.desde(i, caminos.get(i.producto.categoria_id, "")) for i in venta.items],
            pagos=[VentaPagoResponse.desde(p) for p in venta.pagos],
            subtotal=venta.subtotal, descuento_total=venta.descuento_total, recargo_total=venta.recargo_total,
            total=venta.total, cobrable=venta.cobrable, promocion=Referencia.de(venta.promocion),
            promocion_a_mano=venta.promocion_a_mano, codigo_cambio=venta.codigo_cambio,
            confirmada_en=venta.confirmada_en, created_at=venta.created_at, anulada_en=venta.anulada_en,
            anulada_por=Referencia.de(venta.anulada_por), motivo_anulacion=venta.motivo_anulacion,
        )


class VentaResumen(BaseModel):
    id: int
    numero: str
    fecha: datetime
    usuario: Referencia
    cliente: Referencia | None
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal
    codigo_cambio: str | None
    estado: EstadoVenta
    medios: list[str]
    anulada_en: datetime | None
    anulada_por: Referencia | None
    motivo_anulacion: str | None

    @classmethod
    def desde(cls, venta) -> "VentaResumen":
        return cls(
            id=venta.id, numero=venta.numero, fecha=venta.confirmada_en or venta.created_at,
            usuario=Referencia.de(venta.usuario), cliente=Referencia.de(venta.cliente),
            subtotal=venta.subtotal, descuento_total=venta.descuento_total, total=venta.total,
            codigo_cambio=venta.codigo_cambio, estado=venta.estado,
            medios=[p.medio_de_pago.nombre for p in venta.pagos],
            anulada_en=venta.anulada_en, anulada_por=Referencia.de(venta.anulada_por),
            motivo_anulacion=venta.motivo_anulacion,
        )


class AgregarItemResponse(BaseModel):
    venta: VentaResponse
    aviso: str | None


class ProductoVenta(BaseModel):
    id: int
    codigo: str
    descripcion: str
    categoria: str
    precio: Decimal          # con el descuento propio del producto
    precio_lista: Decimal
    stock: int
    stock_infinito: bool
    foto_url: str | None

    @classmethod
    def desde(cls, producto, camino: str, redondeo: Decimal) -> "ProductoVenta":
        return cls(
            id=producto.id, codigo=producto.codigo_con_verificador, descripcion=producto.descripcion,
            categoria=camino,
            precio=aplicar_descuentos(producto.precio_venta, producto.descuento_producto, Decimal("0"), redondeo),
            precio_lista=producto.precio_venta, stock=producto.stock, stock_infinito=producto.stock_infinito,
            foto_url=producto.foto_principal_url,
        )


class MotivoParaVenta(BaseModel):
    id: int
    nombre: str
    nota: str | None
    porcentaje_sugerido: Decimal | None
    habilita_cuotas_sin_interes: bool


class OpcionesDescuento(BaseModel):
    motivos: list[MotivoParaVenta]
    porcentajes: list[int]
    tope: Decimal

    @classmethod
    def desde(cls, motivos, porcentajes: list[int], tope: Decimal) -> "OpcionesDescuento":
        return cls(
            motivos=[MotivoParaVenta(id=m.id, nombre=m.nombre, nota=m.nota, porcentaje_sugerido=m.porcentaje_sugerido,
                                     habilita_cuotas_sin_interes=m.habilita_cuotas_sin_interes) for m in motivos],
            porcentajes=porcentajes, tope=tope,
        )


class PlanParaVenta(BaseModel):
    id: int
    cuotas: int
    recargo_cliente: Decimal
    monto_minimo: Decimal


class MedioParaVenta(BaseModel):
    """Sin `costo_medio` (solo Reportes)."""
    id: int
    nombre: str
    es_efectivo: bool
    soporta_cuotas: bool
    planes: list[PlanParaVenta]

    @classmethod
    def desde(cls, medio, planes) -> "MedioParaVenta":
        return cls(
            id=medio.id, nombre=medio.nombre, es_efectivo=medio.es_efectivo, soporta_cuotas=medio.soporta_cuotas,
            planes=[PlanParaVenta(id=p.id, cuotas=p.cuotas, recargo_cliente=p.recargo_cliente,
                                  monto_minimo=p.monto_minimo) for p in planes],
        )


class PromocionParaVenta(BaseModel):
    id: int
    nombre: str
    nota: str | None
    tipo: TipoPromocion
    ahorro: Decimal

    @classmethod
    def desde(cls, promo, ahorro: Decimal) -> "PromocionParaVenta":
        return cls(id=promo.id, nombre=promo.nombre, nota=promo.nota, tipo=promo.tipo, ahorro=ahorro)
