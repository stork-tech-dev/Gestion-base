"""Ventas: el carrito de la pantalla de venta y el listado/detalle de ventas
confirmadas o anuladas.

Rutas fijas (`/en-curso`, `/opciones-descuento`, `/producto`, `/productos`,
`/vendedores`) declaradas ANTES de `/{venta_id}` (mismo motivo que stock.py y
productos.py: si no, esos segmentos se probarían primero contra el converter
int de `/{venta_id}` y devolverían 422 en vez de resolver la ruta fija)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import ReglaDeNegocio
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import EstadoVenta, Usuario
from app.schemas.comunes import RespuestaPaginada
from app.schemas.ventas import (
    AnularVenta,
    CantidadLinea,
    ClienteAsociar,
    ConfirmarVenta,
    DescuentoAplicar,
    DescuentoGeneral,
    ItemAgregar,
    MedioParaVenta,
    MONTO_MAXIMO,
    OpcionesDescuento,
    PagosRegistrar,
    PromocionElegir,
    PromocionParaVenta,
    ProductoVenta,
    Referencia,
    VentaResponse,
    VentaResumen,
)
from app.services import descuentos as servicio_descuentos
from app.services import productos as servicio_productos
from app.services import ventas as servicio
from app.services.productos import buscar_por_codigo
from app.services.ventas import TAMANO_MAXIMO

router = APIRouter(prefix="/ventas", tags=["ventas"])

puede_ver = requiere_permiso(Modulo.VENTAS, "ver")
puede_vender = requiere_permiso(Modulo.VENTAS, "crear")
puede_descontar = requiere_permiso(Modulo.VENTAS, "crear", Recurso.VENTA_DESCUENTO)
puede_anular = requiere_permiso(Modulo.VENTAS, "eliminar", Recurso.VENTA_ANULAR)

PAGINA_MAXIMA = 100_000
LIMITE_BUSQUEDA_MAXIMO = 20


# --- Rutas fijas (GET) ----------------------------------------------------------

@router.get("", response_model=RespuestaPaginada[VentaResumen])
def listar(cliente_id: int | None = None, usuario_id: int | None = None, estado: EstadoVenta | None = None,
          numero: str | None = None, codigo_cambio: str | None = None,
          total_desde: Decimal | None = Query(None, ge=0, le=MONTO_MAXIMO),
          total_hasta: Decimal | None = Query(None, ge=0, le=MONTO_MAXIMO),
          fecha_desde: date | None = None, fecha_hasta: date | None = None,
          pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO),
          db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    ventas, total = servicio.listar_ventas(db, cliente_id=cliente_id, usuario_id=usuario_id, estado=estado,
                                           numero=numero, codigo_cambio=codigo_cambio, total_desde=total_desde,
                                           total_hasta=total_hasta, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                                           pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[VentaResumen.desde(v) for v in ventas])


@router.get("/en-curso", response_model=VentaResponse | None)
def en_curso(db: Session = Depends(get_db), autor: Usuario = Depends(puede_ver)):
    venta = servicio.venta_en_curso(db, autor)
    return servicio.a_respuesta(db, venta) if venta is not None else None


@router.get("/opciones-descuento", response_model=OpcionesDescuento)
def opciones_descuento(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    motivos = servicio_descuentos.listar_motivos(db, activo=True)
    return OpcionesDescuento.desde(motivos, servicio_descuentos.porcentajes_validos(db), servicio_descuentos.tope(db))


@router.get("/producto", response_model=ProductoVenta)
def producto_por_codigo(codigo: str = Query(min_length=1), db: Session = Depends(get_db),
                        _: Usuario = Depends(puede_ver)):
    producto = buscar_por_codigo(db, codigo)   # 404 si no existe
    if not producto.activo:
        raise ReglaDeNegocio(f"'{producto.descripcion}' está inactivo")
    return servicio.a_productos_venta(db, [producto])[0]


@router.get("/productos", response_model=list[ProductoVenta])
def productos_para_buscador(busqueda: str = "", limite: int = Query(8, ge=1, le=LIMITE_BUSQUEDA_MAXIMO),
                            db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items, _total = servicio_productos.listar_productos(db, busqueda=busqueda, activo=True, tamano=limite)
    return servicio.a_productos_venta(db, items)


@router.get("/vendedores", response_model=list[Referencia])
def vendedores(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return [Referencia.de(u) for u in servicio.vendedores(db)]


# --- Detalle y consultas de una venta puntual ------------------------------------

@router.get("/{venta_id}", response_model=VentaResponse)
def detalle(venta_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.a_respuesta(db, servicio.obtener_venta(db, venta_id))


@router.get("/{venta_id}/medios-de-pago", response_model=list[MedioParaVenta])
def medios_de_pago(venta_id: int, monto: Decimal | None = Query(None, gt=0, le=MONTO_MAXIMO),
                   db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    venta = servicio.obtener_venta(db, venta_id)
    return [MedioParaVenta.desde(m["medio"], m["planes"]) for m in servicio.medios_para_venta(db, venta, monto)]


@router.get("/{venta_id}/promociones", response_model=list[PromocionParaVenta])
def promociones_de_venta(venta_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    venta = servicio.obtener_venta(db, venta_id)
    return [PromocionParaVenta.desde(p["promocion"], p["ahorro"]) for p in servicio.promociones_para_venta(db, venta)]


# --- Carrito: iniciar y armar la venta --------------------------------------------

@router.post("", response_model=VentaResponse)
def iniciar(request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    """200 siempre (haya iniciado una venta nueva o devuelto la que ya estaba
    en curso): más simple que decidir 200/201 según el caso."""
    venta = servicio.iniciar_venta(db, autor, ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/items", response_model=VentaResponse)
def agregar_item(venta_id: int, datos: ItemAgregar, request: Request, db: Session = Depends(get_db),
                 autor: Usuario = Depends(puede_vender)):
    venta = servicio.agregar_item(db, autor, venta_id, codigo=datos.codigo, producto_id=datos.producto_id,
                                  cantidad=datos.cantidad, ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.delete("/{venta_id}/items/{item_id}", response_model=VentaResponse)
def quitar_item(venta_id: int, item_id: int, db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    venta = servicio.quitar_item(db, autor, venta_id, item_id)
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.put("/{venta_id}/items/{item_id}/cantidad", response_model=VentaResponse)
def cambiar_cantidad(venta_id: int, item_id: int, datos: CantidadLinea, request: Request,
                     db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    venta = servicio.cambiar_cantidad(db, autor, venta_id, item_id, datos.cantidad, ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/cliente", response_model=VentaResponse)
def asociar_cliente(venta_id: int, datos: ClienteAsociar, db: Session = Depends(get_db),
                    autor: Usuario = Depends(puede_vender)):
    venta = servicio.asociar_cliente(db, autor, venta_id, datos.cliente_id)
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/descuento", response_model=VentaResponse)
def aplicar_descuento(venta_id: int, datos: DescuentoAplicar, request: Request, db: Session = Depends(get_db),
                      autor: Usuario = Depends(puede_vender), _descuento: Usuario = Depends(puede_descontar)):
    venta = servicio.aplicar_descuento_item(db, autor, venta_id, datos.item_id, datos.motivo_id, datos.porcentaje,
                                            ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/descuento-general", response_model=VentaResponse)
def aplicar_descuento_general(venta_id: int, datos: DescuentoGeneral, request: Request,
                              db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender),
                              _descuento: Usuario = Depends(puede_descontar)):
    venta = servicio.aplicar_descuento_general(db, autor, venta_id, porcentaje=datos.porcentaje, total=datos.total,
                                               ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/promocion", response_model=VentaResponse)
def elegir_promocion(venta_id: int, datos: PromocionElegir, db: Session = Depends(get_db),
                     autor: Usuario = Depends(puede_vender)):
    venta = servicio.elegir_promocion(db, autor, venta_id, datos.promocion_id)
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/pagos", response_model=VentaResponse)
def registrar_pagos(venta_id: int, datos: PagosRegistrar, db: Session = Depends(get_db),
                    autor: Usuario = Depends(puede_vender)):
    venta = servicio.registrar_pagos(db, autor, venta_id, datos.pagos)
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/confirmar", response_model=VentaResponse)
def confirmar(venta_id: int, datos: ConfirmarVenta, request: Request, db: Session = Depends(get_db),
             autor: Usuario = Depends(puede_vender)):
    venta = servicio.confirmar_venta(db, autor, venta_id, datos.total_esperado, ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/recalcular", response_model=VentaResponse)
def recalcular(venta_id: int, db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    """Relee precios vivos (decisión 3): lo llama la pantalla tras un 409 de
    `/confirmar` ("los precios cambiaron")."""
    venta = servicio.recalcular(db, autor, venta_id)
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.post("/{venta_id}/anular", response_model=VentaResponse)
def anular(venta_id: int, datos: AnularVenta, request: Request, db: Session = Depends(get_db),
          autor: Usuario = Depends(puede_ver), _anular: Usuario = Depends(puede_anular)):
    """VENTAS ver + venta.anular (decisión 6): el spec pedía VENTAS eliminar,
    pero el supervisor sembrado no lo tiene y no podría anular con eso."""
    venta = servicio.anular_venta(db, autor, venta_id, datos.motivo, ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.delete("/{venta_id}", status_code=204)
def descartar(venta_id: int, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    servicio.descartar_venta(db, autor, venta_id, ip_de_request(request))
    db.commit()
