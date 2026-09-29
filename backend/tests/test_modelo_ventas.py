from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    Cliente, CondicionIva, EstadoVenta, MedioDePago, PlanCuotas, Venta, VentaItem, VentaPago,
)
from tests.fabricas import catalogo


def test_seed_medios_de_pago(db):
    nombres = set(db.scalars(select(MedioDePago.nombre)))
    assert {"Efectivo", "Débito", "Tarjeta de Crédito", "Transferencia"} <= nombres
    efectivo = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    assert efectivo.nombre == "Efectivo" and efectivo.soporta_cuotas is False
    credito = db.scalar(select(MedioDePago).where(MedioDePago.nombre == "Tarjeta de Crédito"))
    assert credito.soporta_cuotas is True


def test_un_solo_medio_efectivo(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(MedioDePago(nombre="Otro efectivo", es_efectivo=True))
            db.flush()


def test_efectivo_no_admite_cuotas(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE medios_de_pago SET soporta_cuotas = TRUE WHERE es_efectivo"))


def test_cliente_no_consumidor_final_exige_cuit(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Cliente(nombre="Sin CUIT", condicion_iva=CondicionIva.RESPONSABLE_INSCRIPTO))
            db.flush()


def test_plan_disponible_para_y_sin_interes(db):
    plan = PlanCuotas(cuotas=3, recargo_cliente=Decimal("0"), costo_medio=Decimal("5"),
                      monto_minimo=Decimal("10000"), activo=True)
    assert plan.sin_interes is True
    assert plan.disponible_para(Decimal("10000")) is True
    assert plan.disponible_para(Decimal("9999.99")) is False


def test_venta_en_curso_unica_por_usuario(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    db.add(Venta(numero="V-900001", usuario_id=vendedor.id))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Venta(numero="V-900002", usuario_id=vendedor.id))
            db.flush()


def test_check_estado_confirmada_exige_codigo(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Venta(numero="V-900003", usuario_id=vendedor.id, estado=EstadoVenta.CONFIRMADA))
            db.flush()


def test_item_en_promocion_no_lleva_descuento(db, crear_usuario):
    admin = crear_usuario("admin")
    producto = catalogo(db, admin)["alta"]("Remera modelo")
    venta = Venta(numero="V-900004", usuario_id=admin.id)
    db.add(venta)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(VentaItem(venta_id=venta.id, producto_id=producto.id, precio_unitario=1000, precio_lista=1000,
                             costo_unitario=500, descuento_item=10, precio_final=900, en_promocion=True, orden=1))
            db.flush()


def test_pago_monto_total_es_monto_mas_recargo(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    venta = Venta(numero="V-900005", usuario_id=vendedor.id)
    db.add(venta)
    db.flush()
    medio = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(VentaPago(venta_id=venta.id, medio_de_pago_id=medio.id, monto=100, recargo=10, monto_total=100))
            db.flush()


def test_fk_movimiento_a_venta(db):
    fk = db.scalar(text("SELECT 1 FROM pg_constraint WHERE conname = 'fk_movimientos_stock_referencia_venta'"))
    assert fk == 1
