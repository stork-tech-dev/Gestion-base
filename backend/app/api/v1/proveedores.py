"""Proveedores y valor del dólar. Las rutas /dolar/... van antes de /{proveedor_id}."""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TAMANO_MAXIMO_BYTES, TIPO_XLSX
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ahora, ip_de_request
from app.models import EstadoProveedor, Moneda, Usuario
from app.schemas.proveedores import (
    CambioDolar,
    CambioMasivo,
    DolarEnUso,
    HistorialDolarResponse,
    PreviewDolar,
    ProveedorCrear,
    ProveedorDolarResumen,
    ProveedorEditar,
    ProveedorEstado,
    ProveedorResponse,
    ResultadoImportacionDolar,
)
from app.services import proveedores as servicio

router = APIRouter(prefix="/proveedores", tags=["proveedores"])

puede_ver = requiere_permiso(Modulo.PROVEEDORES, "ver")
puede_crear = requiere_permiso(Modulo.PROVEEDORES, "crear")
puede_editar = requiere_permiso(Modulo.PROVEEDORES, "editar")
puede_masivo = requiere_permiso(Modulo.PROVEEDORES, "editar", Recurso.DOLAR_CAMBIO_MASIVO)


@router.get("/dolar/en-uso", response_model=DolarEnUso)
def dolar_en_uso(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return DolarEnUso(hay_proveedores_en_dolares=servicio.hay_proveedores_en_dolares(db))


@router.post("/dolar/masivo/preview", response_model=list[PreviewDolar])
def preview_masivo(datos: CambioMasivo, db: Session = Depends(get_db), _: Usuario = Depends(puede_masivo)):
    return servicio.preview_masivo(db, datos.proveedor_ids, datos.modalidad, datos.valor)


@router.post("/dolar/masivo", response_model=list[PreviewDolar])
def aplicar_masivo(datos: CambioMasivo, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_masivo)):
    aplicados = servicio.aplicar_masivo(db, autor, datos.proveedor_ids, datos.modalidad, datos.valor, ip_de_request(request))
    db.commit()
    return aplicados


@router.get(
    "/dolar/plantilla",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}},
                     "description": "Planilla .xlsx con los proveedores activos en dólares"}},
)
def plantilla(db: Session = Depends(get_db), _: Usuario = Depends(puede_masivo)):
    nombre = f"dolar-proveedores-{ahora().date().isoformat()}.xlsx"
    return Response(
        content=servicio.generar_plantilla_dolar(db), media_type=TIPO_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/dolar/importar", response_model=ResultadoImportacionDolar)
def importar(request: Request, archivo: UploadFile = File(...), db: Session = Depends(get_db),
             autor: Usuario = Depends(puede_masivo)):
    contenido = archivo.file.read(TAMANO_MAXIMO_BYTES + 1)  # el service rechaza lo que pase de 5 MB
    resultado = servicio.importar_dolar(db, autor, contenido, ip_de_request(request))
    if resultado["errores"]:
        db.rollback()
    else:
        db.commit()
    return resultado


@router.get("/dolar/activos", response_model=list[ProveedorDolarResumen])
def activos_en_dolares(db: Session = Depends(get_db), _: Usuario = Depends(puede_masivo)):
    """Proveedores activos en dólares. Quien solo tiene el permiso puntual del
    cambio masivo (sin "ver" proveedores) necesita esta ruta: GET /proveedores
    le daría 403. Devuelve solo id/nombre/dolar_actual (ProveedorDolarResumen):
    sin datos de contacto, que ese permiso no habilita a ver."""
    return servicio.listar_activos_en_dolares(db)


@router.get("", response_model=list[ProveedorResponse])
def listar(nombre: str | None = None, email: str | None = None, telefono: str | None = None,
           provincia: str | None = None, pais: str | None = None, estado: EstadoProveedor | None = None,
           moneda: Moneda | None = None, dolar_desde: Decimal | None = None, dolar_hasta: Decimal | None = None,
           db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.listar_proveedores(db, nombre=nombre, email=email, telefono=telefono, provincia=provincia,
                                       pais=pais, estado=estado, moneda=moneda, dolar_desde=dolar_desde,
                                       dolar_hasta=dolar_hasta)


@router.get("/{proveedor_id}", response_model=ProveedorResponse)
def ficha(proveedor_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.obtener_proveedor(db, proveedor_id)


@router.post("", response_model=ProveedorResponse, status_code=201)
def crear(datos: ProveedorCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    proveedor = servicio.crear_proveedor(db, autor, datos, ip_de_request(request))
    db.commit()
    return proveedor


@router.put("/{proveedor_id}", response_model=ProveedorResponse)
def editar(proveedor_id: int, datos: ProveedorEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.editar_proveedor(db, autor, servicio.obtener_proveedor(db, proveedor_id, bloquear=True), datos, ip_de_request(request))
    db.commit()
    return proveedor


@router.patch("/{proveedor_id}/estado", response_model=ProveedorResponse)
def cambiar_estado(proveedor_id: int, datos: ProveedorEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.cambiar_estado(db, autor, servicio.obtener_proveedor(db, proveedor_id), datos.estado,
                                        datos.confirmar_con_productos, ip_de_request(request))
    db.commit()
    return proveedor


@router.patch("/{proveedor_id}/dolar", response_model=ProveedorResponse)
def cambiar_dolar(proveedor_id: int, datos: CambioDolar, request: Request, db: Session = Depends(get_db),
                  autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.cambiar_dolar(db, autor, servicio.obtener_proveedor(db, proveedor_id, bloquear=True),
                                       datos.valor_nuevo, ip_de_request(request))
    db.commit()
    return proveedor


@router.get("/{proveedor_id}/dolar/historial", response_model=list[HistorialDolarResponse])
def historial(proveedor_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    servicio.obtener_proveedor(db, proveedor_id)
    return servicio.historial_dolar(db, proveedor_id)
