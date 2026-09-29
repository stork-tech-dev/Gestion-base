"""Tests de services/turnos.py (sesión 07)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.core.utils import ahora_db
from app.models import Auditoria, EstadoTurno, Turno, TurnoUsuario
from app.services import turnos as servicio

D = Decimal


def _turno_de_ayer(db, usuario):
    turno = Turno(efectivo_apertura=D("0"), usuario_apertura_id=usuario.id,
                  fecha_apertura=ahora_db() - timedelta(days=1))
    db.add(turno)
    db.flush()
    return turno


def _acciones(db, turno_id):
    return db.scalars(select(Auditoria.accion).where(Auditoria.entidad == "turno",
                                                     Auditoria.entidad_id == turno_id)).all()


def test_abrir_turno_crea_turno_y_suma_al_que_abre(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    turno = servicio.abrir_turno(db, vendedor, D("5000"), "  Fondo del día  ", "10.0.0.1")
    assert turno.estado is EstadoTurno.ABIERTO
    assert turno.efectivo_apertura == D("5000")
    assert turno.notas == "Fondo del día"
    assert [p.usuario_id for p in turno.participantes] == [vendedor.id]
    assert "turno.abierto" in _acciones(db, turno.id)


def test_abrir_con_uno_abierto_hoy_409_hay_que_sumarse(db, crear_usuario):
    servicio.abrir_turno(db, crear_usuario("vendedor"), D("0"), None, None)
    with pytest.raises(ReglaDeNegocio, match="Unirme al turno"):
        servicio.abrir_turno(db, crear_usuario("vendedor"), D("0"), None, None)


def test_abrir_con_uno_de_ayer_409_con_la_fecha(db, crear_usuario):
    ayer = _turno_de_ayer(db, crear_usuario("admin"))
    with pytest.raises(ReglaDeNegocio, match=f"{ayer.fecha_apertura:%d/%m/%Y}"):
        servicio.abrir_turno(db, crear_usuario("vendedor"), D("0"), None, None)


def test_abrir_con_efectivo_negativo_400(db, crear_usuario):
    with pytest.raises(DatoInvalido):
        servicio.abrir_turno(db, crear_usuario("vendedor"), D("-1"), None, None)


def test_turno_para_operar_sin_turno_409(db, crear_usuario):
    with pytest.raises(ReglaDeNegocio, match="No hay un turno de caja abierto."):
        servicio.turno_para_operar(db, crear_usuario("vendedor"), None)


def test_turno_para_operar_con_turno_de_ayer_bloquea(db, crear_usuario):
    ayer = _turno_de_ayer(db, crear_usuario("admin"))
    with pytest.raises(ReglaDeNegocio, match=f"Hay un turno del {ayer.fecha_apertura:%d/%m/%Y} sin cerrar"):
        servicio.turno_para_operar(db, crear_usuario("vendedor"), None)


def test_turno_para_operar_suma_al_usuario_una_sola_vez(db, crear_usuario):
    turno = servicio.abrir_turno(db, crear_usuario("vendedor"), D("0"), None, None)
    otro = crear_usuario("vendedor")
    assert servicio.turno_para_operar(db, otro, None).id == turno.id
    servicio.turno_para_operar(db, otro, None)
    filas = db.scalars(select(TurnoUsuario).where(TurnoUsuario.turno_id == turno.id,
                                                  TurnoUsuario.usuario_id == otro.id)).all()
    assert len(filas) == 1
    assert _acciones(db, turno.id).count("turno.unirse") == 1


def test_unirse_sin_turno_409(db, crear_usuario):
    with pytest.raises(ReglaDeNegocio):
        servicio.unirse_a_turno(db, crear_usuario("vendedor"), None)


def test_obtener_turno_activo_devuelve_el_de_ayer(db, crear_usuario):
    ayer = _turno_de_ayer(db, crear_usuario("admin"))
    activo = servicio.obtener_turno_activo(db)
    assert activo.id == ayer.id and servicio.es_de_dia_anterior(activo)


def test_registrar_retiro(db, crear_usuario):
    supervisor = crear_usuario("supervisor")
    turno = servicio.abrir_turno(db, supervisor, D("10000"), None, None)
    retiro = servicio.registrar_retiro(db, supervisor, D("3000"), "  Pago a proveedor ", None)
    assert (retiro.turno_id, retiro.monto, retiro.motivo) == (turno.id, D("3000"), "Pago a proveedor")
    assert db.scalar(select(Auditoria.id).where(Auditoria.accion == "caja.retiro_efectivo",
                                                Auditoria.entidad_id == retiro.id)) is not None
    assert [r.id for r in servicio.listar_retiros(db, turno.id)] == [retiro.id]


@pytest.mark.parametrize("monto, motivo", [(D("0"), "x"), (D("-5"), "x"), (D("10"), "   ")])
def test_retiro_invalido_400(db, crear_usuario, monto, motivo):
    supervisor = crear_usuario("supervisor")
    servicio.abrir_turno(db, supervisor, D("0"), None, None)
    with pytest.raises(DatoInvalido):
        servicio.registrar_retiro(db, supervisor, monto, motivo, None)


def test_retiro_sin_turno_de_hoy_409(db, crear_usuario):
    _turno_de_ayer(db, crear_usuario("admin"))
    with pytest.raises(ReglaDeNegocio):
        servicio.registrar_retiro(db, crear_usuario("supervisor"), D("10"), "x", None)


def test_listar_turnos_filtra_por_estado_y_fecha(db, crear_usuario):
    admin = crear_usuario("admin")
    ayer = _turno_de_ayer(db, admin)
    turnos, total = servicio.listar_turnos(db, estado=EstadoTurno.ABIERTO)
    assert ayer.id in [t.id for t in turnos] and total >= 1
    hoy = ahora_db().date()
    turnos, _ = servicio.listar_turnos(db, desde=hoy, hasta=hoy)
    assert ayer.id not in [t.id for t in turnos]
