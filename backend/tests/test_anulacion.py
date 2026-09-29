"""Tests de services/ventas.anular_venta (sesión 06). El 403 sin el recurso
`venta.anular` se prueba en la API (Task 5)."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.core.utils import ahora_db
from app.models import Auditoria, EstadoTurno, EstadoVenta, MedioDePago, MovimientoStock, TipoMovimientoStock
from app.services import ventas as servicio
from app.services.stock import registrar_ingreso
from tests.fabricas import abrir_turno_de_test, catalogo


@pytest.fixture
def e(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    p10 = cat["alta"]("Campera anul", costo="10000")
    p8 = cat["alta"]("Buzo anul", costo="8000")
    for p in (p10, p8):
        registrar_ingreso(db, admin, p.id, 5, None, None)
    turno = abrir_turno_de_test(db, admin)
    return {"admin": admin, "p10": p10, "p8": p8, "turno": turno, "vendedor": crear_usuario("vendedor"),
            "supervisor": crear_usuario("supervisor")}


def _confirmada(db, e):
    autor = e["vendedor"]
    venta = servicio.iniciar_venta(db, autor, None)
    for p in (e["p10"], e["p10"], e["p8"]):
        venta, _ = servicio.agregar_item(db, autor, venta.id, producto_id=p.id)
    efectivo = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    venta = servicio.registrar_pagos(db, autor, venta.id,
                                     [{"medio_de_pago_id": efectivo.id, "monto": Decimal("1"), "plan_cuotas_id": None}])
    return servicio.confirmar_venta(db, autor, venta.id, venta.total, None)


def test_anular_venta_en_curso_409(db, e):
    venta = servicio.iniciar_venta(db, e["vendedor"], None)
    with pytest.raises(ReglaDeNegocio, match="se descarta, no se anula"):
        servicio.anular_venta(db, e["supervisor"], venta.id, "Error", None)


def test_anular_dos_veces_409(db, e):
    venta = _confirmada(db, e)
    servicio.anular_venta(db, e["supervisor"], venta.id, "Error de carga", None)
    with pytest.raises(ReglaDeNegocio, match="ya está anulada"):
        servicio.anular_venta(db, e["supervisor"], venta.id, "Otra vez", None)


def test_anular_sin_turno_de_hoy_409(db, e):
    venta = _confirmada(db, e)
    e["turno"].estado = EstadoTurno.CERRADO
    e["turno"].fecha_cierre = ahora_db()
    e["turno"].usuario_cierre_id = e["admin"].id
    db.flush()
    with pytest.raises(ReglaDeNegocio, match="No hay un turno de caja abierto."):
        servicio.anular_venta(db, e["supervisor"], venta.id, "Error", None)


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 501])
def test_motivo_obligatorio(db, e, motivo):
    venta = _confirmada(db, e)
    with pytest.raises(DatoInvalido, match="motivo de anulación es obligatorio"):
        servicio.anular_venta(db, e["supervisor"], venta.id, motivo, None)
    assert venta.estado is EstadoVenta.CONFIRMADA


def test_anular_reingresa_stock_y_sella(db, e):
    venta = _confirmada(db, e)
    db.refresh(e["p10"])
    assert e["p10"].stock == 3
    pagos_antes = [(p.id, p.monto, p.monto_total) for p in venta.pagos]
    total_antes = venta.total

    # La anula alguien distinto de quien vendió.
    venta = servicio.anular_venta(db, e["supervisor"], venta.id, "  Cliente se arrepintió  ", "10.0.0.1")

    assert venta.estado is EstadoVenta.ANULADA
    assert venta.anulada_en is not None and venta.anulada_por_id == e["supervisor"].id
    assert venta.motivo_anulacion == "Cliente se arrepintió"
    assert venta.turno_anulacion_id == e["turno"].id
    assert venta.total == total_antes
    assert [(p.id, p.monto, p.monto_total) for p in venta.pagos] == pagos_antes

    movimientos = db.scalars(select(MovimientoStock).where(
        MovimientoStock.referencia_venta_id == venta.id,
        MovimientoStock.tipo == TipoMovimientoStock.ANULACION_VENTA,
    ).order_by(MovimientoStock.id)).all()
    esperados = sorted([(e["p10"].id, 2), (e["p8"].id, 1)])
    assert [(m.producto_id, m.cantidad) for m in movimientos] == esperados
    db.refresh(e["p10"])
    db.refresh(e["p8"])
    assert e["p10"].stock == 5 and e["p8"].stock == 5

    audit = db.scalars(select(Auditoria).where(Auditoria.accion == "venta.anular",
                                               Auditoria.entidad_id == venta.id)).all()
    assert len(audit) == 1
    assert audit[0].usuario_id == e["supervisor"].id and audit[0].ip_origen == "10.0.0.1"
    assert audit[0].estado_anterior["estado"] == "confirmada"
    assert audit[0].estado_nuevo["motivo_anulacion"] == "Cliente se arrepintió"
    assert audit[0].estado_nuevo["estado"] == "anulada"
