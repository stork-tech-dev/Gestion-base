"""Arqueo y cierre del turno (sesión 07).

Se arquea POR TURNO, no por franja horaria: suma lo cobrado en ventas con
turno_id = el turno (confirmadas o anuladas después: el dinero entró acá) y
resta lo de ventas con turno_anulacion_id = el turno (el dinero salió acá).
El efectivo además suma el fondo inicial y resta los retiros.
"""
from collections import defaultdict
from dataclasses import dataclass

from decimal import Decimal

from sqlalchemy import func, or_, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.permisos import ROL_ADMIN
from app.core.utils import ahora_db, pesos_texto, sin_tildes
from app.models import (
    Arqueo, ArqueoItem, EstadoTurno, EstadoVenta, MedioDePago, MedioPagoArqueoConfig, Notificacion, RetiroEfectivo,
    Rol, TipoNotificacion, Turno, Usuario, Venta, VentaPago,
)
from app.services.turnos import bloquear_turno, obtener_turno

CERO = Decimal("0")
MENSAJE_CERRADO = "El turno ya está cerrado"


def clave_de(medio_de_pago_id: int | None, grupo_terminal: str | None) -> tuple:
    return ("grupo", grupo_terminal) if grupo_terminal else ("medio", medio_de_pago_id)


@dataclass
class LineaArqueo:
    medio_de_pago_id: int | None
    grupo_terminal: str | None
    medio_nombre: str
    es_efectivo: bool
    es_informativo: bool
    monto_esperado: Decimal

    @property
    def clave(self) -> tuple:
        return clave_de(self.medio_de_pago_id, self.grupo_terminal)


def _sumas_por_medio(db, *condiciones) -> dict[int, Decimal]:
    filas = db.execute(
        select(VentaPago.medio_de_pago_id, func.sum(VentaPago.monto_total))
        .join(Venta, Venta.id == VentaPago.venta_id).where(*condiciones).group_by(VentaPago.medio_de_pago_id)
    ).all()
    return {medio_id: monto for medio_id, monto in filas}


def _movimientos_por_medio(db, turno_id: int) -> dict[int, Decimal]:
    neto: dict[int, Decimal] = defaultdict(lambda: CERO)
    cobros = _sumas_por_medio(db, Venta.turno_id == turno_id,
                              Venta.estado.in_([EstadoVenta.CONFIRMADA, EstadoVenta.ANULADA]))
    anulaciones = _sumas_por_medio(db, Venta.turno_anulacion_id == turno_id, Venta.estado == EstadoVenta.ANULADA)
    for medio_id, monto in cobros.items():
        neto[medio_id] += monto
    for medio_id, monto in anulaciones.items():
        neto[medio_id] -= monto
    return dict(neto)


def _total_retiros(db, turno_id: int) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(RetiroEfectivo.monto), CERO))
                     .where(RetiroEfectivo.turno_id == turno_id))


def calcular_esperado(db, turno: Turno) -> tuple[list[LineaArqueo], Decimal]:
    """Una línea por medio activo (o con movimientos en el turno, decisión 9),
    o por grupo de terminal. total = suma de las líneas no informativas."""
    movimientos = _movimientos_por_medio(db, turno.id)
    medios = db.scalars(select(MedioDePago).where(
        or_(MedioDePago.activo.is_(True), MedioDePago.id.in_(list(movimientos))))).all()
    configs = {c.medio_de_pago_id: c for c in db.scalars(select(MedioPagoArqueoConfig))}
    lineas: dict[tuple, LineaArqueo] = {}
    for medio in medios:
        config = configs.get(medio.id)
        monto = movimientos.get(medio.id, CERO)
        if medio.es_efectivo:
            # El cajón físico incluye el fondo inicial.
            monto += turno.efectivo_apertura - _total_retiros(db, turno.id)
        informativo = bool(config and config.es_informativo)
        if config and config.agrupa_en_terminal and not medio.es_efectivo:
            nueva = LineaArqueo(None, config.grupo_terminal, config.grupo_terminal, False, informativo, CERO)
        else:
            nueva = LineaArqueo(medio.id, None, medio.nombre, medio.es_efectivo, informativo, CERO)
        linea = lineas.setdefault(nueva.clave, nueva)
        linea.monto_esperado += monto
    ordenadas = sorted(lineas.values(), key=lambda l: (not l.es_efectivo, sin_tildes(l.medio_nombre).lower()))
    total = sum((l.monto_esperado for l in ordenadas if not l.es_informativo), CERO)
    return ordenadas, total


def esperado_de_turno(db, turno_id: int) -> tuple[Turno, list[LineaArqueo], Decimal]:
    turno = obtener_turno(db, turno_id)
    if turno.estado is not EstadoTurno.ABIERTO:
        raise ReglaDeNegocio(MENSAJE_CERRADO)
    lineas, total = calcular_esperado(db, turno)
    return turno, lineas, total


def _declarados_por_clave(items_declarados) -> dict[tuple, Decimal]:
    declarados: dict[tuple, Decimal] = {}
    for item in items_declarados:
        clave = clave_de(item.medio_de_pago_id, item.grupo_terminal)
        if clave in declarados:
            raise DatoInvalido("Hay un medio de pago declarado dos veces")
        declarados[clave] = item.monto_declarado
    return declarados


def _notificar_admins(db, turno: Turno, arqueo: Arqueo, lineas: list[LineaArqueo],
                      declarados: dict[tuple, Decimal]) -> None:
    diferencia = arqueo.total_declarado - arqueo.total_esperado
    fecha = f"{turno.fecha_apertura:%d/%m/%Y}"
    participantes = [p.usuario for p in turno.participantes]
    detalle = [
        f"- {l.medio_nombre}: esperado {pesos_texto(l.monto_esperado)}, declarado {pesos_texto(declarados[l.clave])}, "
        f"diferencia {pesos_texto(declarados[l.clave] - l.monto_esperado)}"
        for l in lineas if not l.es_informativo
    ]
    cuerpo = "\n".join([
        f"Turno del {fecha}.",
        f"Diferencia total: {pesos_texto(diferencia)}.",
        f"Usuarios del turno: {', '.join(u.nombre for u in participantes)}.",
        "Detalle por medio:",
        *detalle,
    ])
    metadata = {"turno_id": turno.id, "arqueo_id": arqueo.id, "diferencia": str(diferencia),
                "usuarios": [u.id for u in participantes]}
    admins = db.scalars(select(Usuario).join(Rol, Rol.id == Usuario.rol_id)
                        .where(Rol.nombre == ROL_ADMIN, Usuario.activo.is_(True))).all()
    for admin in admins:
        db.add(Notificacion(usuario_id=admin.id, tipo=TipoNotificacion.DIFERENCIA_ARQUEO,
                            titulo=f"Diferencia en arqueo — {fecha}", cuerpo=cuerpo, metadata_=metadata))
    arqueo.notificacion_enviada = True


def registrar_arqueo(db, usuario, turno_id: int, items_declarados, total_declarado: Decimal, ip) -> Arqueo:
    """Arqueo + cierre del turno + notificaciones, todo en la transacción del
    caller. El turno va FOR UPDATE: las operaciones en curso (FOR SHARE)
    terminan antes y las que lleguen después ven el turno cerrado."""
    turno = bloquear_turno(db, turno_id)
    if turno.estado is not EstadoTurno.ABIERTO:
        raise ReglaDeNegocio(MENSAJE_CERRADO)
    lineas, total_esperado = calcular_esperado(db, turno)
    declarados = _declarados_por_clave(items_declarados)
    por_clave = {l.clave: l for l in lineas}
    if set(declarados) - set(por_clave):
        raise ReglaDeNegocio("Los medios de pago del arqueo cambiaron: volvé a cargar la pantalla.")
    for linea in lineas:
        if linea.es_informativo:
            declarados[linea.clave] = linea.monto_esperado  # decisión 10: no suma ni difiere
    faltan = [l.medio_nombre for l in lineas if l.clave not in declarados]
    if faltan:
        raise DatoInvalido(f"Falta declarar: {', '.join(faltan)}")
    suma = sum((declarados[l.clave] for l in lineas if not l.es_informativo), CERO)
    if suma != total_declarado:
        raise DatoInvalido("El total declarado no coincide con la suma de los medios")

    antes = snapshot(turno)
    arqueo = Arqueo(turno_id=turno.id, usuario_id=usuario.id, total_esperado=total_esperado,
                    total_declarado=total_declarado, created_at=ahora_db())
    arqueo.items = [ArqueoItem(medio_de_pago_id=l.medio_de_pago_id, grupo_terminal=l.grupo_terminal,
                               monto_esperado=l.monto_esperado, monto_declarado=declarados[l.clave],
                               es_informativo=l.es_informativo) for l in lineas]
    db.add(arqueo)
    # Mantiene la relación en memoria consistente (mismo motivo que
    # `_sumar_usuario` con `participantes`): sin esto, una lectura posterior
    # del turno en la MISMA sesión (otro request reusando la sesión, como en
    # los tests) seguiría viendo `turno.arqueo` como lo cacheó el primer
    # selectin, antes de que este arqueo existiera.
    turno.arqueo = arqueo
    turno.estado = EstadoTurno.CERRADO
    turno.fecha_cierre = ahora_db()
    turno.usuario_cierre_id = usuario.id
    db.flush()
    if total_declarado != total_esperado:
        _notificar_admins(db, turno, arqueo, lineas, declarados)
    db.flush()
    db.refresh(arqueo)  # trae las columnas generadas (diferencia)
    registrar_auditoria(db, accion="caja.arqueo_cerrado", entidad="turno", entidad_id=turno.id,
                        usuario_id=usuario.id, estado_anterior=antes,
                        estado_nuevo={**snapshot(turno), "arqueo_id": arqueo.id,
                                      "total_esperado": arqueo.total_esperado,
                                      "total_declarado": arqueo.total_declarado,
                                      "diferencia": arqueo.diferencia,
                                      "items": [{"medio_de_pago_id": i.medio_de_pago_id,
                                                 "grupo_terminal": i.grupo_terminal,
                                                 "monto_esperado": i.monto_esperado,
                                                 "monto_declarado": i.monto_declarado,
                                                 "es_informativo": i.es_informativo,
                                                 "diferencia": i.diferencia} for i in arqueo.items]},
                        ip_origen=ip)
    return arqueo


def obtener_arqueo(db, turno_id: int) -> Arqueo:
    obtener_turno(db, turno_id)
    arqueo = db.scalar(select(Arqueo).where(Arqueo.turno_id == turno_id))
    if arqueo is None:
        raise NoEncontrado("El turno no tiene arqueo")
    return arqueo
