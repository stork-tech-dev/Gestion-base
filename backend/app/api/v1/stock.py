"""Stock: listado, alertas, resumen, movimientos, motivos de baja, ingresos,
bajas y mínimos. Rutas todas fijas (sin `/{id}` genérico): el listado usa
`producto_id`, no un id propio de este router."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import TipoMovimientoStock, Usuario
from app.schemas.comunes import RespuestaPaginada
from app.schemas.stock import (
    BajaCrear,
    IngresoCrear,
    MinimoEditar,
    MotivoBajaCrear,
    MotivoBajaEditar,
    MotivoBajaResponse,
    MovimientoResponse,
    ResumenStock,
    StockResponse,
)
from app.services import bajas_stock as servicio_bajas
from app.services import stock as servicio
from app.services.stock import TAMANO_MAXIMO

router = APIRouter(prefix="/stock", tags=["stock"])

puede_ver = requiere_permiso(Modulo.STOCK, "ver")
puede_ingresar = requiere_permiso(Modulo.STOCK, "crear")
puede_minimos = requiere_permiso(Modulo.STOCK, "editar")
puede_baja = requiere_permiso(Modulo.STOCK, "crear", Recurso.STOCK_BAJA)
puede_motivos = requiere_permiso(Modulo.STOCK, "editar", Recurso.STOCK_MOTIVOS_BAJA)

PAGINA_MAXIMA = 100_000


@router.get("", response_model=RespuestaPaginada[StockResponse])
def listar(busqueda: str | None = None, categoria_id: int | None = None, proveedor_id: int | None = None,
           solo_bajo_minimo: bool = False, incluir_sin_stock: bool = True,
           pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO),
           db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items, total = servicio.listar_stock(db, busqueda=busqueda, categoria_id=categoria_id, proveedor_id=proveedor_id,
                                         solo_bajo_minimo=solo_bajo_minimo, incluir_sin_stock=incluir_sin_stock,
                                         pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano, resultados=servicio.a_respuesta(db, items))


@router.get("/alertas", response_model=list[StockResponse])
def alertas(limite: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.a_respuesta(db, servicio.alertas(db, limite))


@router.get("/resumen", response_model=ResumenStock)
def resumen(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.resumen(db)


@router.get("/movimientos", response_model=RespuestaPaginada[MovimientoResponse])
def movimientos(producto_id: int | None = None, tipo: TipoMovimientoStock | None = None,
                desde: date | None = None, hasta: date | None = None,
                pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO),
                db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    items, total = servicio.listar_movimientos(db, producto_id=producto_id, tipo=tipo, desde=desde, hasta=hasta,
                                                pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[MovimientoResponse.desde(m) for m in items])


@router.get("/motivos-baja", response_model=list[MotivoBajaResponse])
def motivos_baja(activo: bool | None = None, nombre: str | None = None, db: Session = Depends(get_db),
                 _: Usuario = Depends(puede_ver)):
    return [MotivoBajaResponse.desde(m) for m in servicio_bajas.listar_motivos(db, nombre=nombre, activo=activo)]


@router.post("/motivos-baja", response_model=MotivoBajaResponse, status_code=201)
def crear_motivo_baja(datos: MotivoBajaCrear, request: Request, db: Session = Depends(get_db),
                      autor: Usuario = Depends(puede_motivos)):
    motivo = servicio_bajas.crear_motivo(db, autor, datos, ip_de_request(request))
    db.commit()
    return MotivoBajaResponse.desde(motivo)


@router.put("/motivos-baja/{motivo_id}", response_model=MotivoBajaResponse)
def editar_motivo_baja(motivo_id: int, datos: MotivoBajaEditar, request: Request, db: Session = Depends(get_db),
                       autor: Usuario = Depends(puede_motivos)):
    motivo = servicio_bajas.editar_motivo(db, autor, servicio_bajas.obtener_motivo(db, motivo_id), datos,
                                          ip_de_request(request))
    db.commit()
    return MotivoBajaResponse.desde(motivo)


@router.post("/ingresos", response_model=MovimientoResponse, status_code=201)
def ingresos(datos: IngresoCrear, request: Request, db: Session = Depends(get_db),
            autor: Usuario = Depends(puede_ingresar)):
    movimiento = servicio.registrar_ingreso(db, autor, datos.producto_id, datos.cantidad, datos.notas,
                                            ip_de_request(request))
    db.commit()
    return MovimientoResponse.desde(movimiento)


@router.post("/bajas", response_model=MovimientoResponse, status_code=201)
def bajas(datos: BajaCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_baja)):
    movimiento = servicio_bajas.registrar_baja(db, autor, datos.producto_id, datos.cantidad, datos.motivo_baja_id,
                                               datos.notas, ip_de_request(request))
    db.commit()
    return MovimientoResponse.desde(movimiento)


@router.put("/minimos/{producto_id}", response_model=StockResponse)
def minimos(producto_id: int, datos: MinimoEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_minimos)):
    producto = servicio.definir_minimo(db, autor, producto_id, datos.stock_minimo, ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, [producto])[0]
