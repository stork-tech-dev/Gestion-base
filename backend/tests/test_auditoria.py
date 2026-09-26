from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.utils import ahora_db
from app.models import MotivoBaja
from app.services.auditoria import listar_auditoria


class Color(Enum):
    ROJO = "rojo"


def test_registrar_auditoria_guarda_json_seguro_sin_sensibles(db):
    registro = registrar_auditoria(
        db,
        accion="prueba.crear",
        entidad="prueba",
        entidad_id=7,
        usuario_id=3,
        ip_origen="200.1.1.1",
        estado_nuevo={
            "precio": Decimal("10.50"),
            "cuando": date(2026, 1, 2),
            "color": Color.ROJO,
            "password_hash": "secreto",
            "clave_especial": "1234",
        },
    )
    assert registro.id is not None
    assert registro.estado_nuevo == {"precio": "10.50", "cuando": "2026-01-02", "color": "rojo"}
    assert registro.estado_anterior is None
    assert registro.timestamp.tzinfo is None
    assert abs((ahora_db() - registro.timestamp).total_seconds()) < 5


def test_snapshot_de_modelo_y_campos(db):
    motivo = MotivoBaja(nombre="Prueba snapshot", activo=True)
    db.add(motivo)
    db.flush()
    assert snapshot(motivo) == {"id": motivo.id, "nombre": "Prueba snapshot", "activo": True}
    assert snapshot(motivo, campos=["nombre"]) == {"nombre": "Prueba snapshot"}
    assert snapshot(None) is None


def test_registrar_auditoria_rechaza_estado_anterior_con_cambios_pendientes(db):
    """Si se pasa el objeto mapeado YA modificado (sin flushear) como
    estado_anterior, el snapshot tomado acá adentro daría el estado nuevo:
    debe fallar, no guardar auditoría incorrecta en silencio."""
    motivo = MotivoBaja(nombre="Original", activo=True)
    db.add(motivo)
    db.flush()
    motivo.nombre = "Modificado"  # cambio pendiente, todavía no flusheado
    with pytest.raises(ValueError, match="ANTES del cambio"):
        registrar_auditoria(db, accion="prueba.editar", entidad="prueba", estado_anterior=motivo)


def test_registrar_auditoria_acepta_objeto_mapeado_sin_cambios_pendientes(db):
    """El patrón correcto: snapshot(obj) ANTES de modificar, como dict."""
    motivo = MotivoBaja(nombre="Original", activo=True)
    db.add(motivo)
    db.flush()
    antes = snapshot(motivo)
    motivo.nombre = "Modificado"
    registro = registrar_auditoria(
        db, accion="prueba.editar", entidad="prueba", estado_anterior=antes, estado_nuevo=motivo
    )
    assert registro.estado_anterior == {"id": motivo.id, "nombre": "Original", "activo": True}
    assert registro.estado_nuevo == {"id": motivo.id, "nombre": "Modificado", "activo": True}


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE auditoria SET accion = 'x'", "DELETE FROM auditoria", "TRUNCATE auditoria"],
)
def test_auditoria_es_inmutable_en_la_base(db, sentencia):
    registrar_auditoria(db, accion="prueba.inmutable", entidad="prueba")
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)


def test_listar_auditoria_filtra_y_ordena(db):
    for accion, usuario in [("zzventa.crear", 1), ("zzventa.anular", 2), ("zzproducto.editar", 1)]:
        registrar_auditoria(db, accion=accion, entidad=accion.split(".")[0], usuario_id=usuario, entidad_id=5)

    registros, total = listar_auditoria(db, accion="zzventa.")
    assert total == 2
    assert [r.accion for r in registros] == ["zzventa.anular", "zzventa.crear"]  # timestamp desc, id desc

    _, total = listar_auditoria(db, accion="zz", usuario_id=1)
    assert total == 2
    _, total = listar_auditoria(db, entidad="ZZPRODUCTO", entidad_id=5)
    assert total == 1

    hoy = ahora_db().date()
    _, total = listar_auditoria(db, accion="zz", desde=hoy, hasta=hoy)
    assert total == 3
    _, total = listar_auditoria(db, accion="zz", desde=hoy + timedelta(days=1))
    assert total == 0


def test_listar_auditoria_escapa_comodines_de_ilike(db):
    """"zz_x" (con _ literal) no debe matchear "zzAx": _ es comodín de un
    solo carácter en LIKE/ILIKE y debe escaparse antes de armar el patrón."""
    registrar_auditoria(db, accion="zzcomodinAx.crear", entidad="zzcomodin")
    _, total = listar_auditoria(db, accion="zzcomodin_x")
    assert total == 0
    _, total = listar_auditoria(db, accion="zzcomodinAx")
    assert total == 1


def test_listar_auditoria_pagina_y_limita_tamano(db):
    for i in range(3):
        registrar_auditoria(db, accion=f"zzpag.{i}", entidad="zzpag")
    registros, total = listar_auditoria(db, accion="zzpag.", pagina=2, tamano=2)
    assert total == 3 and len(registros) == 1
    registros, _ = listar_auditoria(db, accion="zzpag.", tamano=10_000)
    assert len(registros) == 3  # el tope (200) no rompe
