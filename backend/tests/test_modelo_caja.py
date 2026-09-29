"""Tests de la migración 0007: restricciones que viven en la base."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.utils import ahora_db
from app.models import (
    Arqueo, ArqueoItem, EstadoTurno, MedioDePago, MedioPagoArqueoConfig, RolPermiso, Rol, Turno,
)

D = Decimal


def _turno(db, usuario, **extra):
    turno = Turno(efectivo_apertura=D("100"), usuario_apertura_id=usuario.id, fecha_apertura=ahora_db(), **extra)
    db.add(turno)
    db.flush()
    return turno


def test_no_puede_haber_dos_turnos_abiertos(db, crear_usuario):
    usuario = crear_usuario("admin")
    _turno(db, usuario)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _turno(db, usuario)


def test_turno_cerrado_exige_fecha_y_usuario_de_cierre(db, crear_usuario):
    usuario = crear_usuario("admin")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _turno(db, usuario, estado=EstadoTurno.CERRADO)


def test_diferencia_es_columna_generada(db, crear_usuario):
    usuario = crear_usuario("admin")
    turno = _turno(db, usuario)
    efectivo = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    arqueo = Arqueo(turno_id=turno.id, usuario_id=usuario.id, total_esperado=D("1000"), total_declarado=D("900"))
    arqueo.items = [ArqueoItem(medio_de_pago_id=efectivo.id, monto_esperado=D("1000"), monto_declarado=D("900"))]
    db.add(arqueo)
    db.flush()
    db.refresh(arqueo)
    assert arqueo.diferencia == D("-100.00")
    assert arqueo.items[0].diferencia == D("-100.00")


def test_item_de_arqueo_es_medio_o_grupo(db, crear_usuario):
    usuario = crear_usuario("admin")
    turno = _turno(db, usuario)
    arqueo = Arqueo(turno_id=turno.id, usuario_id=usuario.id, total_esperado=D("0"), total_declarado=D("0"))
    db.add(arqueo)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(ArqueoItem(arqueo_id=arqueo.id, monto_esperado=D("0"), monto_declarado=D("0")))
            db.flush()


def test_seed_agrupa_debito_y_credito_en_la_terminal(db):
    filas = db.execute(
        select(MedioDePago.nombre, MedioPagoArqueoConfig.grupo_terminal)
        .join(MedioPagoArqueoConfig, MedioPagoArqueoConfig.medio_de_pago_id == MedioDePago.id)
        .where(MedioPagoArqueoConfig.agrupa_en_terminal.is_(True))
    ).all()
    assert sorted(filas) == [("Débito", "Clover/Payway"), ("Tarjeta de Crédito", "Clover/Payway")]


def test_permisos_de_caja_sembrados(db):
    def permiso(rol, recurso):
        return db.scalar(select(RolPermiso).join(Rol, Rol.id == RolPermiso.rol_id)
                         .where(Rol.nombre == rol, RolPermiso.modulo == "caja",
                                RolPermiso.recurso.is_(None) if recurso is None else RolPermiso.recurso == recurso))
    sup = permiso("supervisor", None)
    assert sup.puede_ver and sup.puede_crear
    vend = permiso("vendedor", None)
    assert vend.puede_ver and not vend.puede_crear
    assert permiso("vendedor", "caja.arqueo").puede_crear
    assert permiso("vendedor", "caja.retiro") is None
