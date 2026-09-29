"""Turnos de caja (sesión 07).

ÚNICO lugar que responde "cuál es la caja abierta" (obtener_turno_activo /
turno_para_operar). Para multi-local, estas funciones recibirían el local y
el resto del sistema no cambia.

Concurrencia: quien opera sobre el turno (venta, anulación, retiro, sumarse)
lo toma FOR SHARE; quien lo cierra (services.arqueo) FOR UPDATE. Una
operación que llega durante un cierre espera y ve el turno cerrado → 409.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db, normalizar_texto, paginar, rango_fechas
from app.models import EstadoTurno, RetiroEfectivo, Turno, TurnoUsuario

MENSAJE_SIN_TURNO = "No hay un turno de caja abierto."
MENSAJE_YA_ABIERTO = "Ya hay un turno abierto hoy. Usá 'Unirme al turno' para sumarte."
TAMANO_MAXIMO = 100


def es_de_dia_anterior(turno: Turno) -> bool:
    return turno.fecha_apertura.date() < ahora_db().date()


def _mensaje_dia_anterior(turno: Turno) -> str:
    return (f"Hay un turno del {turno.fecha_apertura:%d/%m/%Y} sin cerrar. "
            "Cerrá el turno anterior antes de continuar.")


def obtener_turno_activo(db) -> Turno | None:
    """El turno abierto (de hoy o de un día anterior), o None."""
    return db.scalar(select(Turno).where(Turno.estado == EstadoTurno.ABIERTO))


def hay_turno_para_operar(db) -> bool:
    """Mismo criterio que `turno_para_operar` (True solo con un turno abierto
    de HOY) pero sin bloquear la fila ni sumar al usuario: lo usa `api/pages.py`
    para decidir qué mostrar en /ventas/nueva, donde tomar el lock solo por
    armar la pantalla sería un efecto secundario indebido."""
    turno = obtener_turno_activo(db)
    return turno is not None and not es_de_dia_anterior(turno)


def obtener_turno(db, turno_id: int) -> Turno:
    turno = db.get(Turno, turno_id)
    if turno is None:
        raise NoEncontrado("Turno no encontrado")
    return turno


def bloquear_turno(db, turno_id: int, *, compartido: bool = False) -> Turno:
    """SELECT … FOR SHARE (compartido) o FOR UPDATE de la fila por id (sin
    joins: Postgres no bloquea el lado nullable de un LEFT JOIN) y relectura
    con populate_existing."""
    db.execute(select(Turno.id).where(Turno.id == turno_id).with_for_update(read=compartido))
    turno = db.get(Turno, turno_id, populate_existing=True)
    if turno is None:
        raise NoEncontrado("Turno no encontrado")
    return turno


def _sumar_usuario(db, turno: Turno, usuario, ip) -> None:
    """Agrega al usuario al turno si no estaba (ON CONFLICT: dos pestañas a la vez)."""
    nuevo = db.scalar(
        pg_insert(TurnoUsuario)
        .values(turno_id=turno.id, usuario_id=usuario.id, ingreso=ahora_db())
        .on_conflict_do_nothing(index_elements=["turno_id", "usuario_id"])
        .returning(TurnoUsuario.id)
    )
    if nuevo is None:
        return
    db.expire(turno, ["participantes"])
    registrar_auditoria(db, accion="turno.unirse", entidad="turno", entidad_id=turno.id, usuario_id=usuario.id,
                        estado_nuevo={"usuario_id": usuario.id}, ip_origen=ip)


def turno_para_operar(db, usuario, ip) -> Turno:
    """El turno abierto de HOY, bloqueado FOR SHARE hasta el fin de la
    transacción, con el usuario sumado (decisión 3). 409 si no hay turno o si
    quedó abierto uno de un día anterior (bloqueo duro)."""
    turno_id = db.scalar(select(Turno.id).where(Turno.estado == EstadoTurno.ABIERTO))
    if turno_id is None:
        raise ReglaDeNegocio(MENSAJE_SIN_TURNO)
    turno = bloquear_turno(db, turno_id, compartido=True)
    if turno.estado is not EstadoTurno.ABIERTO:  # se cerró mientras esperábamos el lock
        raise ReglaDeNegocio(MENSAJE_SIN_TURNO)
    if es_de_dia_anterior(turno):
        raise ReglaDeNegocio(_mensaje_dia_anterior(turno))
    _sumar_usuario(db, turno, usuario, ip)
    return turno


def abrir_turno(db, usuario, efectivo_apertura: Decimal, notas: str | None, ip) -> Turno:
    if efectivo_apertura is None or efectivo_apertura < 0:
        raise DatoInvalido("El efectivo inicial no puede ser negativo")
    activo = obtener_turno_activo(db)
    if activo is not None:
        raise ReglaDeNegocio(_mensaje_dia_anterior(activo) if es_de_dia_anterior(activo) else MENSAJE_YA_ABIERTO)
    ahora = ahora_db()
    turno = Turno(estado=EstadoTurno.ABIERTO, efectivo_apertura=efectivo_apertura, usuario_apertura_id=usuario.id,
                  fecha_apertura=ahora, notas=normalizar_texto(notas))
    try:
        # Savepoint propio: si otro abrió en paralelo, el índice
        # uq_turnos_un_abierto corta acá y la sesión sigue usable.
        with db.begin_nested():
            db.add(turno)
            db.flush()
    except IntegrityError as exc:
        raise ReglaDeNegocio(MENSAJE_YA_ABIERTO) from exc
    db.add(TurnoUsuario(turno_id=turno.id, usuario_id=usuario.id, ingreso=ahora))
    db.flush()
    db.refresh(turno)
    registrar_auditoria(db, accion="turno.abierto", entidad="turno", entidad_id=turno.id, usuario_id=usuario.id,
                        estado_nuevo=snapshot(turno), ip_origen=ip)
    return turno


def unirse_a_turno(db, usuario, ip) -> Turno:
    """Decisión 6: solo al turno de hoy. Si ya estaba sumado no hace nada."""
    return turno_para_operar(db, usuario, ip)


def registrar_retiro(db, usuario, monto: Decimal, motivo: str, ip) -> RetiroEfectivo:
    """El permiso (caja.retiro) lo exige el endpoint."""
    motivo = normalizar_texto(motivo)
    if not motivo or len(motivo) > 255:
        raise DatoInvalido("El motivo del retiro es obligatorio (hasta 255 caracteres)")
    if monto is None or monto <= 0:
        raise DatoInvalido("El monto del retiro tiene que ser mayor a cero")
    turno = turno_para_operar(db, usuario, ip)
    retiro = RetiroEfectivo(turno_id=turno.id, monto=monto, motivo=motivo, usuario_id=usuario.id,
                            timestamp=ahora_db())
    db.add(retiro)
    db.flush()
    registrar_auditoria(db, accion="caja.retiro_efectivo", entidad="retiro_efectivo", entidad_id=retiro.id,
                        usuario_id=usuario.id, estado_nuevo=snapshot(retiro), ip_origen=ip)
    return retiro


def listar_retiros(db, turno_id: int) -> list[RetiroEfectivo]:
    return list(db.scalars(select(RetiroEfectivo).where(RetiroEfectivo.turno_id == turno_id)
                           .order_by(RetiroEfectivo.timestamp, RetiroEfectivo.id)).all())


def listar_turnos(db, *, estado: EstadoTurno | None = None, desde: date | None = None, hasta: date | None = None,
                  pagina: int = 1, tamano: int = 20) -> tuple[list[Turno], int]:
    condiciones = rango_fechas(Turno.fecha_apertura, desde, hasta)
    if estado is not None:
        condiciones.append(Turno.estado == estado)
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Turno).where(*condiciones))
    turnos = db.scalars(select(Turno).where(*condiciones).order_by(Turno.fecha_apertura.desc(), Turno.id.desc())
                        .offset((pagina - 1) * tamano).limit(tamano)).unique().all()
    return list(turnos), total
