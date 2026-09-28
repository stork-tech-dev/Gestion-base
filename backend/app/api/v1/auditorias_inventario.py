"""Auditorías de inventario (conteos de stock). Distinto del endpoint de solo
lectura `GET /api/v1/auditoria` (Principio 3): acá se gestionan los conteos
físicos, no el log de auditoría del sistema."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TIPO_XLSX
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import EstadoAuditoriaInventario, Usuario
from app.reports.auditoria_pdf import generar_pdf_auditoria, generar_xls_auditoria
from app.schemas.comunes import RespuestaPaginada
from app.schemas.stock import (
    AuditoriaDetalle,
    AuditoriaIniciar,
    AuditoriaItemResponse,
    AuditoriaResponse,
    ItemContado,
    ItemEditar,
    ItemPorCodigo,
    ItemsRegistrar,
)
from app.services import auditoria_inventario as servicio
from app.services import productos as servicio_productos
from app.services.auditoria_inventario import TAMANO_MAXIMO

router = APIRouter(prefix="/auditorias-inventario", tags=["auditorias-inventario"])

puede_ver = requiere_permiso(Modulo.STOCK, "ver")
puede_auditar = requiere_permiso(Modulo.STOCK, "crear", Recurso.STOCK_AUDITORIA)

PAGINA_MAXIMA = 100_000


@router.get("", response_model=RespuestaPaginada[AuditoriaResponse])
def listar(estado: EstadoAuditoriaInventario | None = None, desde: date | None = None, hasta: date | None = None,
          pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO),
          db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items, total = servicio.listar(db, estado=estado, desde=desde, hasta=hasta, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[AuditoriaResponse.desde(a) for a in items])


@router.post("", response_model=AuditoriaResponse, status_code=201)
def iniciar(datos: AuditoriaIniciar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_auditar)):
    auditoria = servicio.iniciar(db, autor, datos, ip_de_request(request))
    db.commit()
    return AuditoriaResponse.desde(auditoria)


@router.get("/{auditoria_id}", response_model=AuditoriaDetalle)
def detalle(auditoria_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return AuditoriaDetalle.desde(servicio.obtener_auditoria(db, auditoria_id))


@router.get(
    "/{auditoria_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def pdf(auditoria_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    contenido = generar_pdf_auditoria(db, auditoria)
    return Response(content=contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="conteo-{auditoria.id}.pdf"'})


@router.get(
    "/{auditoria_id}/xls",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}}}},
)
def xls(auditoria_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    contenido = generar_xls_auditoria(db, auditoria)
    return Response(content=contenido, media_type=TIPO_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="conteo-{auditoria.id}.xlsx"'})


@router.post("/{auditoria_id}/items", response_model=list[AuditoriaItemResponse], status_code=201)
def registrar_items(auditoria_id: int, datos: ItemsRegistrar, request: Request, db: Session = Depends(get_db),
                    autor: Usuario = Depends(puede_auditar)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    items = servicio.registrar_items(db, autor, auditoria, datos.items, ip_de_request(request))
    db.commit()
    return [AuditoriaItemResponse.desde(i) for i in items]


@router.post("/{auditoria_id}/items/por-codigo", response_model=AuditoriaItemResponse, status_code=201)
def registrar_item_por_codigo(auditoria_id: int, datos: ItemPorCodigo, request: Request, db: Session = Depends(get_db),
                              autor: Usuario = Depends(puede_auditar)):
    """Mismo alta que `/items`, pero resolviendo el producto por código
    (escáner de la pantalla de conteo) en vez de pedir el `producto_id`."""
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    producto = servicio_productos.buscar_por_codigo(db, datos.codigo)
    item = servicio.registrar_items(
        db, autor, auditoria, [ItemContado(producto_id=producto.id, cantidad_contada=datos.cantidad_contada)],
        ip_de_request(request),
    )[0]
    db.commit()
    return AuditoriaItemResponse.desde(item)


@router.patch("/{auditoria_id}/items/{item_id}", response_model=AuditoriaItemResponse)
def editar_item(auditoria_id: int, item_id: int, datos: ItemEditar, request: Request, db: Session = Depends(get_db),
                autor: Usuario = Depends(puede_auditar)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    item = servicio.editar_item(db, autor, auditoria, item_id, datos.cantidad_contada, ip_de_request(request))
    db.commit()
    return AuditoriaItemResponse.desde(item)


@router.delete("/{auditoria_id}/items/{item_id}", status_code=204)
def eliminar_item(auditoria_id: int, item_id: int, request: Request, db: Session = Depends(get_db),
                  autor: Usuario = Depends(puede_auditar)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    servicio.eliminar_item(db, autor, auditoria, item_id, ip_de_request(request))
    db.commit()
    return Response(status_code=204)


@router.patch("/{auditoria_id}/finalizar", response_model=AuditoriaResponse)
def finalizar(auditoria_id: int, request: Request, db: Session = Depends(get_db),
             autor: Usuario = Depends(puede_auditar)):
    auditoria = servicio.obtener_auditoria(db, auditoria_id)
    cerrada = servicio.finalizar(db, autor, auditoria, ip_de_request(request))
    db.commit()
    return AuditoriaResponse.desde(cerrada)
