"""Turnos de caja, retiros de efectivo y arqueo (sesión 07).

Rutas fijas (`/activo`, `/abrir`, `/unirse`, `/retiros`) declaradas ANTES de
`/{turno_id}` (mismo motivo que ventas.py)."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import EstadoTurno, Usuario
from app.schemas.caja import (
    ArqueoEsperadoResponse, ArqueoLinea, ArqueoRegistrar, ArqueoResponse, RetiroCrear, RetiroResponse, TurnoAbrir,
    TurnoResponse,
)
from app.schemas.comunes import RespuestaPaginada
from app.services import arqueo as servicio_arqueo
from app.services import turnos as servicio

router = APIRouter(prefix="/turnos", tags=["caja"])

puede_ver = requiere_permiso(Modulo.CAJA, "ver")
puede_arquear = requiere_permiso(Modulo.CAJA, "crear", Recurso.CAJA_ARQUEO)
puede_retirar = requiere_permiso(Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)

PAGINA_MAXIMA = 100_000


def _respuesta(turno) -> TurnoResponse:
    return TurnoResponse.desde(turno, servicio.es_de_dia_anterior(turno))


@router.get("/activo", response_model=TurnoResponse | None)
def activo(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    turno = servicio.obtener_turno_activo(db)
    return _respuesta(turno) if turno else None


@router.post("/abrir", response_model=TurnoResponse, status_code=201)
def abrir(datos: TurnoAbrir, request: Request, db: Session = Depends(get_db),
          usuario: Usuario = Depends(puede_ver)):
    turno = servicio.abrir_turno(db, usuario, datos.efectivo_apertura, datos.notas, ip_de_request(request))
    db.commit()
    return _respuesta(turno)


@router.post("/unirse", response_model=TurnoResponse)
def unirse(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(puede_ver)):
    turno = servicio.unirse_a_turno(db, usuario, ip_de_request(request))
    db.commit()
    db.refresh(turno)
    return _respuesta(turno)


@router.post("/retiros", response_model=RetiroResponse, status_code=201)
def retirar(datos: RetiroCrear, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(puede_retirar)):
    retiro = servicio.registrar_retiro(db, usuario, datos.monto, datos.motivo, ip_de_request(request))
    db.commit()
    return RetiroResponse.desde(retiro)


@router.get("", response_model=RespuestaPaginada[TurnoResponse])
def listar(estado: EstadoTurno | None = None, desde: date | None = None, hasta: date | None = None,
           pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA), tamano: int = Query(20, ge=1, le=servicio.TAMANO_MAXIMO),
           db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    turnos, total = servicio.listar_turnos(db, estado=estado, desde=desde, hasta=hasta, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano, resultados=[_respuesta(t) for t in turnos])


@router.get("/{turno_id}", response_model=TurnoResponse)
def detalle(turno_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return _respuesta(servicio.obtener_turno(db, turno_id))


@router.get("/{turno_id}/retiros", response_model=list[RetiroResponse])
def retiros(turno_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    servicio.obtener_turno(db, turno_id)
    return [RetiroResponse.desde(r) for r in servicio.listar_retiros(db, turno_id)]


@router.get("/{turno_id}/arqueo/esperado", response_model=ArqueoEsperadoResponse)
def esperado(turno_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_arquear)):
    turno, lineas, total = servicio_arqueo.esperado_de_turno(db, turno_id)
    return ArqueoEsperadoResponse(
        turno_id=turno.id, efectivo_apertura=turno.efectivo_apertura, total_esperado=total,
        items=[ArqueoLinea(medio_de_pago_id=l.medio_de_pago_id, medio_nombre=l.medio_nombre,
                           grupo_terminal=l.grupo_terminal, monto_esperado=l.monto_esperado,
                           es_informativo=l.es_informativo, es_efectivo=l.es_efectivo) for l in lineas])


@router.post("/{turno_id}/arqueo", response_model=ArqueoResponse, status_code=201)
def cerrar(turno_id: int, datos: ArqueoRegistrar, request: Request, db: Session = Depends(get_db),
           usuario: Usuario = Depends(puede_arquear)):
    arqueo = servicio_arqueo.registrar_arqueo(db, usuario, turno_id, datos.items_declarados, datos.total_declarado,
                                              ip_de_request(request))
    db.commit()
    return ArqueoResponse.desde(arqueo)


@router.get("/{turno_id}/arqueo", response_model=ArqueoResponse)
def ver_arqueo(turno_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return ArqueoResponse.desde(servicio_arqueo.obtener_arqueo(db, turno_id))
