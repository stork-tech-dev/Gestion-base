"""Configuración de ventas: medios de pago y sus planes de cuotas, motivos de
descuento y promociones. El módulo CONFIGURACION es exclusivo del Admin (ni
vendedor ni supervisor lo tienen sembrado), salvo el recurso `configuracion.promociones`
que sí tiene el supervisor (dependencies `promos_*`, separadas de `puede_*`)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import TipoPromocion, Usuario
from app.schemas.descuentos import (
    MotivoDescuentoCrear,
    MotivoDescuentoEditar,
    MotivoDescuentoEstado,
    MotivoDescuentoResponse,
)
from app.schemas.medios_pago import (
    MedioDePagoCrear,
    MedioDePagoEditar,
    MedioDePagoEstado,
    MedioDePagoResponse,
    PlanCuotasCrear,
    PlanCuotasEditar,
    PlanCuotasEstado,
    PlanCuotasResponse,
)
from app.schemas.promociones import PromocionCrear, PromocionEditar, PromocionEstado, PromocionResponse
from app.services import descuentos as servicio_descuentos
from app.services import medios_pago as servicio_medios
from app.services import promociones as servicio_promos

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

puede_ver = requiere_permiso(Modulo.CONFIGURACION, "ver")
puede_editar = requiere_permiso(Modulo.CONFIGURACION, "editar")
promos_ver = requiere_permiso(Modulo.CONFIGURACION, "ver", Recurso.PROMOCIONES)
promos_crear = requiere_permiso(Modulo.CONFIGURACION, "crear", Recurso.PROMOCIONES)
promos_editar = requiere_permiso(Modulo.CONFIGURACION, "editar", Recurso.PROMOCIONES)


# --- Medios de pago -----------------------------------------------------------

@router.get("/medios-de-pago", response_model=list[MedioDePagoResponse])
def listar_medios(nombre: str | None = None, soporta_cuotas: bool | None = None, activo: bool | None = None,
                  db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    medios = servicio_medios.listar_medios(db, nombre=nombre, soporta_cuotas=soporta_cuotas, activo=activo)
    return [MedioDePagoResponse.model_validate(m) for m in medios]


@router.post("/medios-de-pago", response_model=MedioDePagoResponse, status_code=201)
def crear_medio(datos: MedioDePagoCrear, request: Request, db: Session = Depends(get_db),
                autor: Usuario = Depends(puede_editar)):
    medio = servicio_medios.crear_medio(db, autor, datos, ip_de_request(request))
    db.commit()
    return MedioDePagoResponse.model_validate(medio)


@router.put("/medios-de-pago/{medio_id}", response_model=MedioDePagoResponse)
def editar_medio(medio_id: int, datos: MedioDePagoEditar, request: Request, db: Session = Depends(get_db),
                 autor: Usuario = Depends(puede_editar)):
    medio = servicio_medios.editar_medio(db, autor, servicio_medios.obtener_medio(db, medio_id), datos,
                                         ip_de_request(request))
    db.commit()
    return MedioDePagoResponse.model_validate(medio)


@router.patch("/medios-de-pago/{medio_id}/estado", response_model=MedioDePagoResponse)
def cambiar_estado_medio(medio_id: int, datos: MedioDePagoEstado, request: Request, db: Session = Depends(get_db),
                         autor: Usuario = Depends(puede_editar)):
    medio = servicio_medios.cambiar_estado_medio(db, autor, servicio_medios.obtener_medio(db, medio_id),
                                                 datos.activo, ip_de_request(request))
    db.commit()
    return MedioDePagoResponse.model_validate(medio)


@router.get("/medios-de-pago/{medio_id}/planes", response_model=list[PlanCuotasResponse])
def listar_planes(medio_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    servicio_medios.obtener_medio(db, medio_id)   # 404 si no existe el medio
    return [PlanCuotasResponse.model_validate(p) for p in servicio_medios.listar_planes(db, medio_id)]


@router.post("/medios-de-pago/{medio_id}/planes", response_model=PlanCuotasResponse, status_code=201)
def crear_plan(medio_id: int, datos: PlanCuotasCrear, request: Request, db: Session = Depends(get_db),
              autor: Usuario = Depends(puede_editar)):
    medio = servicio_medios.obtener_medio(db, medio_id)
    plan = servicio_medios.crear_plan(db, autor, medio, datos, ip_de_request(request))
    db.commit()
    return PlanCuotasResponse.model_validate(plan)


@router.put("/planes-cuotas/{plan_id}", response_model=PlanCuotasResponse)
def editar_plan(plan_id: int, datos: PlanCuotasEditar, request: Request, db: Session = Depends(get_db),
               autor: Usuario = Depends(puede_editar)):
    plan = servicio_medios.editar_plan(db, autor, servicio_medios.obtener_plan(db, plan_id), datos,
                                       ip_de_request(request))
    db.commit()
    return PlanCuotasResponse.model_validate(plan)


@router.patch("/planes-cuotas/{plan_id}/estado", response_model=PlanCuotasResponse)
def cambiar_estado_plan(plan_id: int, datos: PlanCuotasEstado, request: Request, db: Session = Depends(get_db),
                        autor: Usuario = Depends(puede_editar)):
    plan = servicio_medios.cambiar_estado_plan(db, autor, servicio_medios.obtener_plan(db, plan_id), datos.activo,
                                               ip_de_request(request))
    db.commit()
    return PlanCuotasResponse.model_validate(plan)


# --- Motivos de descuento ------------------------------------------------------

@router.get("/motivos-descuento", response_model=list[MotivoDescuentoResponse])
def listar_motivos(nombre: str | None = None, habilita_cuotas_sin_interes: bool | None = None,
                   activo: bool | None = None, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    motivos = servicio_descuentos.listar_motivos(db, nombre=nombre,
                                                 habilita_cuotas_sin_interes=habilita_cuotas_sin_interes,
                                                 activo=activo)
    return [MotivoDescuentoResponse.desde(m) for m in motivos]


@router.post("/motivos-descuento", response_model=MotivoDescuentoResponse, status_code=201)
def crear_motivo(datos: MotivoDescuentoCrear, request: Request, db: Session = Depends(get_db),
                 autor: Usuario = Depends(puede_editar)):
    motivo = servicio_descuentos.crear_motivo(db, autor, datos, ip_de_request(request))
    db.commit()
    return MotivoDescuentoResponse.desde(motivo)


@router.put("/motivos-descuento/{motivo_id}", response_model=MotivoDescuentoResponse)
def editar_motivo(motivo_id: int, datos: MotivoDescuentoEditar, request: Request, db: Session = Depends(get_db),
                  autor: Usuario = Depends(puede_editar)):
    motivo = servicio_descuentos.editar_motivo(db, autor, servicio_descuentos.obtener_motivo(db, motivo_id), datos,
                                               ip_de_request(request))
    db.commit()
    return MotivoDescuentoResponse.desde(motivo)


@router.patch("/motivos-descuento/{motivo_id}/estado", response_model=MotivoDescuentoResponse)
def cambiar_estado_motivo(motivo_id: int, datos: MotivoDescuentoEstado, request: Request,
                          db: Session = Depends(get_db), autor: Usuario = Depends(puede_editar)):
    motivo = servicio_descuentos.cambiar_estado_motivo(db, autor, servicio_descuentos.obtener_motivo(db, motivo_id),
                                                        datos.activo, ip_de_request(request))
    db.commit()
    return MotivoDescuentoResponse.desde(motivo)


# --- Promociones ---------------------------------------------------------------

@router.get("/promociones/catalogos")
def catalogos_promociones(db: Session = Depends(get_db), _: Usuario = Depends(promos_ver)):
    """Productos, categorías (camino completo) y medios activos, para armar el
    formulario de alcances de una promoción. Estructura ad-hoc (ver
    services.promociones.catalogos): no hace falta un schema Pydantic."""
    return servicio_promos.catalogos(db)


@router.get("/promociones", response_model=list[PromocionResponse])
def listar_promociones(nombre: str | None = None, tipo: TipoPromocion | None = None, rige_hoy: bool | None = None,
                       activo: bool | None = None, db: Session = Depends(get_db), _: Usuario = Depends(promos_ver)):
    promos = servicio_promos.listar_promociones(db, nombre=nombre, tipo=tipo, rige_hoy=rige_hoy, activo=activo)
    return [PromocionResponse.desde(p) for p in promos]


@router.post("/promociones", response_model=PromocionResponse, status_code=201)
def crear_promocion(datos: PromocionCrear, request: Request, db: Session = Depends(get_db),
                    autor: Usuario = Depends(promos_crear)):
    promo = servicio_promos.crear_promocion(db, autor, datos, ip_de_request(request))
    db.commit()
    return PromocionResponse.desde(promo)


@router.put("/promociones/{promocion_id}", response_model=PromocionResponse)
def editar_promocion(promocion_id: int, datos: PromocionEditar, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(promos_editar)):
    promo = servicio_promos.editar_promocion(db, autor, servicio_promos.obtener_promocion(db, promocion_id), datos,
                                             ip_de_request(request))
    db.commit()
    return PromocionResponse.desde(promo)


@router.patch("/promociones/{promocion_id}/estado", response_model=PromocionResponse)
def cambiar_estado_promocion(promocion_id: int, datos: PromocionEstado, request: Request,
                             db: Session = Depends(get_db), autor: Usuario = Depends(promos_editar)):
    promo = servicio_promos.cambiar_estado_promocion(db, autor, servicio_promos.obtener_promocion(db, promocion_id),
                                                      datos.activo, ip_de_request(request))
    db.commit()
    return PromocionResponse.desde(promo)
