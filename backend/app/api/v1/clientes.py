"""Clientes de ventas: alta, edición, baja, listado, búsqueda rápida (combobox
del punto de venta) y ficha (compras confirmadas + promociones exclusivas)."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ahora_db, ip_de_request
from app.models import CondicionIva, Usuario
from app.schemas.clientes import (
    ClienteCrear,
    ClienteEditar,
    ClienteEstado,
    ClienteFicha,
    ClientePromocionAsignar,
    ClienteResponse,
)
from app.schemas.comunes import RespuestaPaginada
from app.services import clientes as servicio
from app.services import promociones as servicio_promociones
from app.services.clientes import LIMITE_BUSQUEDA_MAXIMO, TAMANO_MAXIMO

router = APIRouter(prefix="/clientes", tags=["clientes"])

puede_ver = requiere_permiso(Modulo.CLIENTES, "ver")
puede_crear = requiere_permiso(Modulo.CLIENTES, "crear")
puede_editar = requiere_permiso(Modulo.CLIENTES, "editar")

# Rutas fijas (/buscar) ANTES de /{cliente_id}: mismo motivo que stock.py y
# productos.py (si no, "/buscar" se probaría primero como cliente_id=int y
# fallaría la conversión con 422 en vez de resolver la ruta fija).
PAGINA_MAXIMA = 100_000


@router.get("", response_model=RespuestaPaginada[ClienteResponse])
def listar(busqueda: str | None = None, localidad: str | None = None, condicion_iva: CondicionIva | None = None,
          activo: bool | None = None, pagina: int = Query(1, ge=1, le=PAGINA_MAXIMA),
          tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO), db: Session = Depends(get_db),
          _: Usuario = Depends(puede_ver)):
    items, total = servicio.listar_clientes(db, busqueda=busqueda, localidad=localidad, condicion_iva=condicion_iva,
                                            activo=activo, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[ClienteResponse.model_validate(c) for c in items])


@router.get("/buscar", response_model=list[ClienteResponse])
def buscar(q: str = "", limite: int = Query(10, ge=1, le=LIMITE_BUSQUEDA_MAXIMO), db: Session = Depends(get_db),
          _: Usuario = Depends(puede_ver)):
    return [ClienteResponse.model_validate(c) for c in servicio.buscar(db, q, limite)]


@router.get("/{cliente_id}", response_model=ClienteFicha)
def ficha(cliente_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return ClienteFicha.desde(servicio.ficha(db, cliente_id), ahora_db().date())


@router.post("", response_model=ClienteResponse, status_code=201)
def crear(datos: ClienteCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    cliente = servicio.crear_cliente(db, autor, datos, ip_de_request(request))
    db.commit()
    return ClienteResponse.model_validate(cliente)


@router.put("/{cliente_id}", response_model=ClienteResponse)
def editar(cliente_id: int, datos: ClienteEditar, request: Request, db: Session = Depends(get_db),
          autor: Usuario = Depends(puede_editar)):
    cliente = servicio.editar_cliente(db, autor, servicio.obtener_cliente(db, cliente_id), datos,
                                      ip_de_request(request))
    db.commit()
    return ClienteResponse.model_validate(cliente)


@router.patch("/{cliente_id}/estado", response_model=ClienteResponse)
def cambiar_estado(cliente_id: int, datos: ClienteEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    cliente = servicio.cambiar_estado(db, autor, servicio.obtener_cliente(db, cliente_id), datos.activo,
                                      ip_de_request(request))
    db.commit()
    return ClienteResponse.model_validate(cliente)


@router.post("/{cliente_id}/promociones", response_model=ClienteFicha, status_code=201)
def asignar_promocion(cliente_id: int, datos: ClientePromocionAsignar, request: Request,
                      db: Session = Depends(get_db), autor: Usuario = Depends(puede_editar)):
    cliente = servicio.obtener_cliente(db, cliente_id)
    servicio_promociones.asignar_a_cliente(db, autor, cliente, datos.promocion_id, ip_de_request(request))
    db.commit()
    return ClienteFicha.desde(servicio.ficha(db, cliente_id), ahora_db().date())


@router.delete("/{cliente_id}/promociones/{promocion_id}", status_code=204)
def quitar_promocion(cliente_id: int, promocion_id: int, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(puede_editar)):
    cliente = servicio.obtener_cliente(db, cliente_id)
    servicio_promociones.quitar_de_cliente(db, autor, cliente, promocion_id, ip_de_request(request))
    db.commit()
