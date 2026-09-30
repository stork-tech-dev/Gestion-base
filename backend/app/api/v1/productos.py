"""Productos y sus fotos. Las rutas fijas, `/fotos/{foto_id}/...` y `/etiquetas`
van antes de `/{producto_id}` (mismo motivo que en proveedores: si no, el
converter `int` de `/{producto_id}` se probaría primero contra esos segmentos)."""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import NoProcesable
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import TemporadaProducto, Usuario
from app.reports.etiquetas_pdf import generar_etiquetas
from app.schemas.comunes import RespuestaPaginada
from app.schemas.productos import (
    FotoResponse,
    PedidoEtiquetas,
    PrecioPreview,
    ProductoCrear,
    ProductoDetalle,
    ProductoEditar,
    ProductoEstado,
    ProductoResponse,
    ProveedorParaProducto,
    Similar,
)
from app.services import producto_fotos
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores
from app.services.producto_fotos import TAMANO_MAXIMO_FOTO
from app.services.productos import TAMANO_MAXIMO

router = APIRouter(prefix="/productos", tags=["productos"])

puede_ver = requiere_permiso(Modulo.PRODUCTOS, "ver")
puede_crear = requiere_permiso(Modulo.PRODUCTOS, "crear")
puede_editar = requiere_permiso(Modulo.PRODUCTOS, "editar")

# Topes de los filtros: `pagina` sin tope desborda el OFFSET (BIGINT) de
# Postgres y daba 500. Los ids enormes no hacen falta acotarlos: Postgres los
# compara como numeric y la respuesta es vacía o 404 (probado).
PRECIO_MAXIMO = 100_000_000   # NUMERIC(10, 2), igual que el costo
PAGINA_MAXIMA = 100_000


@router.get("", response_model=RespuestaPaginada[ProductoResponse])
def listar(busqueda: str | None = None, categoria_id: int | None = None, proveedor_id: int | None = None,
           temporada: TemporadaProducto | None = None, activo: bool | None = None,
           precio_desde: Decimal | None = Query(None, ge=0, lt=PRECIO_MAXIMO),
           precio_hasta: Decimal | None = Query(None, ge=0, lt=PRECIO_MAXIMO), stock_cero: bool = False,
           pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO),
           db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items, total = servicio.listar_productos(db, busqueda=busqueda, categoria_id=categoria_id,
                                              proveedor_id=proveedor_id, temporada=temporada, activo=activo,
                                              precio_desde=precio_desde, precio_hasta=precio_hasta,
                                              stock_cero=stock_cero, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano, resultados=servicio.a_respuesta(db, items))


@router.get("/proveedores", response_model=list[ProveedorParaProducto])
def proveedores(solo_activos: bool = False, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    """Proveedores para el formulario (`solo_activos=true`) y el filtro del
    listado (todos). Pide PRODUCTOS ver, no PROVEEDORES ver: el Vendedor no
    tiene este último y la pantalla de productos igual los necesita."""
    return servicio_proveedores.listar_para_productos(db, solo_activos)


@router.get("/precio-preview", response_model=PrecioPreview)
def precio_preview(proveedor_id: int, costo: Decimal = Query(gt=0, lt=PRECIO_MAXIMO),
                   margen: Decimal | None = Query(None, ge=0, le=1000),
                   precio_venta: Decimal | None = Query(None, gt=0, lt=PRECIO_MAXIMO),
                   db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    if (margen is None) == (precio_venta is None):
        raise NoProcesable("Mandá margen o precio de venta (uno de los dos).")
    return servicio.precio_preview(db, proveedor_id, costo, margen, precio_venta)


@router.get("/similares", response_model=list[Similar])
def similares(descripcion: str = Query(max_length=500), categoria_id: int | None = None,
             proveedor_id: int | None = None, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.buscar_similares(db, descripcion, categoria_id, proveedor_id)


@router.get("/por-codigo", response_model=ProductoDetalle)
def por_codigo(codigo: str = Query(min_length=1, max_length=20), db: Session = Depends(get_db),
               _: Usuario = Depends(puede_ver)):
    return servicio.a_detalle(db, servicio.buscar_por_codigo(db, codigo))


@router.post(
    "/etiquetas",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def etiquetas(datos: PedidoEtiquetas, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items = [(item.producto_id, item.cantidad) for item in datos.items]
    pdf = generar_etiquetas(db, items, datos.tipo)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="etiquetas.pdf"'})


@router.patch("/fotos/{foto_id}/principal", response_model=FotoResponse)
def marcar_foto_principal(foto_id: int, request: Request, db: Session = Depends(get_db),
                          autor: Usuario = Depends(puede_editar)):
    foto = producto_fotos.marcar_principal(db, autor, producto_fotos.obtener_foto(db, foto_id), ip_de_request(request))
    db.commit()
    return foto


@router.delete("/fotos/{foto_id}", status_code=204)
def eliminar_foto(foto_id: int, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_editar)):
    producto_fotos.eliminar_foto(db, autor, producto_fotos.obtener_foto(db, foto_id), ip_de_request(request))
    db.commit()
    return Response(status_code=204)


@router.get("/{producto_id}", response_model=ProductoDetalle)
def ficha(producto_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.a_detalle(db, servicio.obtener_producto(db, producto_id))


@router.post("", response_model=ProductoResponse, status_code=201)
def crear(datos: ProductoCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    producto = servicio.crear_producto(db, autor, datos, ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, [producto])[0]


@router.put("/{producto_id}", response_model=ProductoResponse)
def editar(producto_id: int, datos: ProductoEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    producto = servicio.editar_producto(db, autor, servicio.obtener_producto(db, producto_id), datos,
                                        ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, [producto])[0]


@router.patch("/{producto_id}/estado", response_model=ProductoResponse)
def cambiar_estado(producto_id: int, datos: ProductoEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    producto = servicio.cambiar_estado_producto(db, autor, servicio.obtener_producto(db, producto_id), datos.activo,
                                                ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, [producto])[0]


@router.get(
    "/{producto_id}/barcode",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {"schema": {"type": "string", "format": "binary"}}}}},
)
def barcode(producto_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return Response(content=servicio.barcode_svg(db, producto_id), media_type="image/svg+xml")


@router.post("/{producto_id}/fotos", response_model=FotoResponse, status_code=201)
def subir_foto(producto_id: int, request: Request, archivo: UploadFile = File(...), db: Session = Depends(get_db),
               autor: Usuario = Depends(puede_editar)):
    contenido = archivo.file.read(TAMANO_MAXIMO_FOTO + 1)  # el service rechaza lo que pase de 5 MB
    foto = producto_fotos.subir_foto(db, autor, servicio.obtener_producto(db, producto_id), contenido,
                                     ip_de_request(request))
    db.commit()
    return foto
