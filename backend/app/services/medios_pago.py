"""Medios de pago y sus planes de cuotas (sesión 06). `costo_medio` es SOLO
para reportes (lo que cobra la terminal): calcular_recargo nunca lo usa, lo
que paga el cliente sale únicamente de `recargo_cliente`."""
from decimal import Decimal

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, nombre_libre, redondear
from app.models import MedioDePago, PlanCuotas


def obtener_medio(db, medio_id: int) -> MedioDePago:
    medio = db.get(MedioDePago, medio_id)
    if medio is None:
        raise NoEncontrado("Medio de pago no encontrado")
    return medio


def listar_medios(db, *, nombre: str | None = None, soporta_cuotas: bool | None = None,
                  activo: bool | None = None) -> list[MedioDePago]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(MedioDePago.nombre, nombre))
    if soporta_cuotas is not None:
        condiciones.append(MedioDePago.soporta_cuotas.is_(soporta_cuotas))
    if activo is not None:
        condiciones.append(MedioDePago.activo.is_(activo))
    return list(db.scalars(
        select(MedioDePago).where(*condiciones).order_by(func.lower(MedioDePago.nombre))
    ).all())


def medio_efectivo(db) -> MedioDePago:
    """El arqueo (módulo 07) lo busca por esta marca, nunca por nombre."""
    medio = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    if medio is None:
        raise NoEncontrado("No hay ningún medio de pago marcado como efectivo")
    return medio


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    return nombre_libre(db, MedioDePago, nombre, excepto_id=excepto_id,
                        mensaje_duplicado=lambda m: f"Ya existe un medio de pago llamado '{m.nombre}'")


def _validar_efectivo_sin_cuotas(es_efectivo: bool, soporta_cuotas: bool) -> None:
    if es_efectivo and soporta_cuotas:
        raise DatoInvalido("El efectivo no se cobra en cuotas")


def _validar_un_solo_efectivo(db, es_efectivo: bool, excepto_id: int | None = None) -> None:
    if not es_efectivo:
        return
    condiciones = [MedioDePago.es_efectivo.is_(True)]
    if excepto_id is not None:
        condiciones.append(MedioDePago.id != excepto_id)
    existente = db.scalar(select(MedioDePago).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya hay un medio marcado como efectivo: '{existente.nombre}'")


def _planes_activos(db, medio_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(PlanCuotas)
        .where(PlanCuotas.medio_de_pago_id == medio_id, PlanCuotas.activo.is_(True))
    )


def crear_medio(db, autor, datos, ip) -> MedioDePago:
    _validar_efectivo_sin_cuotas(datos.es_efectivo, datos.soporta_cuotas)
    nombre = _nombre_libre(db, datos.nombre)
    _validar_un_solo_efectivo(db, datos.es_efectivo)
    medio = MedioDePago(nombre=nombre, soporta_cuotas=datos.soporta_cuotas, es_efectivo=datos.es_efectivo, activo=True)
    db.add(medio)
    db.flush()
    db.refresh(medio)
    registrar_auditoria(db, accion="medio_de_pago.crear", entidad="medio_de_pago", entidad_id=medio.id,
                        usuario_id=autor.id, estado_nuevo=medio, ip_origen=ip)
    return medio


def editar_medio(db, autor, medio: MedioDePago, datos, ip) -> MedioDePago:
    _validar_efectivo_sin_cuotas(datos.es_efectivo, datos.soporta_cuotas)
    nombre = _nombre_libre(db, datos.nombre, excepto_id=medio.id)
    _validar_un_solo_efectivo(db, datos.es_efectivo, excepto_id=medio.id)
    # Si se pudiera desmarcar, después cambiar_estado_medio ya no vería este
    # medio como "el efectivo" y lo dejaría desactivar: el arqueo (módulo 07)
    # se queda sin medio_efectivo(). Por eso se corta acá, no solo al desactivar.
    if medio.es_efectivo and not datos.es_efectivo:
        raise ReglaDeNegocio("El efectivo no se puede desmarcar: lo usa la caja")
    if medio.soporta_cuotas and not datos.soporta_cuotas and _planes_activos(db, medio.id):
        raise ReglaDeNegocio("Desactivá primero sus planes de cuotas")
    antes = snapshot(medio)
    medio.nombre = nombre
    medio.soporta_cuotas = datos.soporta_cuotas
    medio.es_efectivo = datos.es_efectivo
    db.flush()
    registrar_auditoria(db, accion="medio_de_pago.editar", entidad="medio_de_pago", entidad_id=medio.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=medio, ip_origen=ip)
    return medio


def cambiar_estado_medio(db, autor, medio: MedioDePago, activo: bool, ip) -> MedioDePago:
    if medio.activo is activo:
        return medio
    if not activo and medio.es_efectivo:
        raise ReglaDeNegocio("El efectivo no se puede desactivar: lo usa la caja")
    antes = snapshot(medio)
    medio.activo = activo
    db.flush()
    registrar_auditoria(db, accion="medio_de_pago.activar" if activo else "medio_de_pago.desactivar",
                        entidad="medio_de_pago", entidad_id=medio.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=medio, ip_origen=ip)
    return medio


# --- Planes de cuotas --------------------------------------------------------

def obtener_plan(db, plan_id: int) -> PlanCuotas:
    plan = db.get(PlanCuotas, plan_id)
    if plan is None:
        raise NoEncontrado("Plan de cuotas no encontrado")
    return plan


def listar_planes(db, medio_id: int) -> list[PlanCuotas]:
    return list(db.scalars(
        select(PlanCuotas).where(PlanCuotas.medio_de_pago_id == medio_id)
        .order_by(PlanCuotas.cuotas, PlanCuotas.recargo_cliente)
    ).all())


def _validar_duplicado_plan(db, medio_id: int, cuotas: int, recargo: Decimal, excepto_id: int | None = None) -> None:
    condiciones = [PlanCuotas.medio_de_pago_id == medio_id, PlanCuotas.cuotas == cuotas,
                  PlanCuotas.recargo_cliente == recargo]
    if excepto_id is not None:
        condiciones.append(PlanCuotas.id != excepto_id)
    if db.scalar(select(PlanCuotas).where(*condiciones)) is not None:
        raise ReglaDeNegocio(f"Ya existe un plan de {cuotas} cuotas con {recargo}% de recargo")


def crear_plan(db, autor, medio: MedioDePago, datos, ip) -> PlanCuotas:
    if not medio.soporta_cuotas:
        raise ReglaDeNegocio("Este medio no se cobra en cuotas")
    _validar_duplicado_plan(db, medio.id, datos.cuotas, datos.recargo_cliente)
    plan = PlanCuotas(cuotas=datos.cuotas, recargo_cliente=datos.recargo_cliente,
                      costo_medio=datos.costo_medio, monto_minimo=datos.monto_minimo, activo=True)
    # Se cuelga del lado de la relación (no seteando medio_de_pago_id a mano):
    # así, si `medio.planes` ya estaba cargado en memoria (ej. lo acaba de
    # devolver crear_medio), el plan nuevo aparece ahí también. Si no, esto
    # dispara su carga perezosa y listo.
    medio.planes.append(plan)
    db.add(plan)
    db.flush()
    db.refresh(plan)
    registrar_auditoria(db, accion="plan_cuotas.crear", entidad="plan_cuotas", entidad_id=plan.id,
                        usuario_id=autor.id, estado_nuevo=plan, ip_origen=ip)
    return plan


def editar_plan(db, autor, plan: PlanCuotas, datos, ip) -> PlanCuotas:
    _validar_duplicado_plan(db, plan.medio_de_pago_id, datos.cuotas, datos.recargo_cliente, excepto_id=plan.id)
    antes = snapshot(plan)
    plan.cuotas = datos.cuotas
    plan.recargo_cliente = datos.recargo_cliente
    plan.costo_medio = datos.costo_medio
    plan.monto_minimo = datos.monto_minimo
    db.flush()
    registrar_auditoria(db, accion="plan_cuotas.editar", entidad="plan_cuotas", entidad_id=plan.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=plan, ip_origen=ip)
    return plan


def cambiar_estado_plan(db, autor, plan: PlanCuotas, activo: bool, ip) -> PlanCuotas:
    if plan.activo is activo:
        return plan
    antes = snapshot(plan)
    plan.activo = activo
    db.flush()
    registrar_auditoria(db, accion="plan_cuotas.activar" if activo else "plan_cuotas.desactivar",
                        entidad="plan_cuotas", entidad_id=plan.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=plan, ip_origen=ip)
    return plan


def planes_disponibles(medio: MedioDePago, monto: Decimal, habilita_sin_interes: bool) -> list[PlanCuotas]:
    if not medio.soporta_cuotas:
        return []
    return [p for p in medio.planes if p.activo and (p.disponible_para(monto) or (habilita_sin_interes and p.sin_interes))]


def calcular_recargo(monto: Decimal, plan: PlanCuotas | None) -> Decimal:
    """Recargo que paga el cliente. `costo_medio` NUNCA se usa acá: es SOLO
    para reportes (lo que cobra la terminal), no afecta lo que paga el cliente."""
    if plan is None:
        return Decimal("0")
    return redondear(monto * plan.recargo_cliente / 100)
