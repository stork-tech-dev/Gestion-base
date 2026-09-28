from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditoriaInventario, AuditoriaItem, Categoria, EstadoAuditoriaInventario, Moneda, MotivoBaja,
    MovimientoStock, Producto, Proveedor, TipoMovimientoStock, Usuario, Venta,
)


@pytest.fixture
def base(db, crear_usuario):
    usuario = crear_usuario("admin")
    cat = Categoria(nombre="Stock cat", nivel=1)
    prov = Proveedor(nombre="Stock prov", moneda=Moneda.ARS)
    db.add_all([cat, prov])
    db.flush()
    producto = Producto(sku="AA001", verificador="9", descripcion="Con stock", categoria_id=cat.id,
                        proveedor_id=prov.id, costo=Decimal("1"), margen=Decimal("0"), precio_venta=Decimal("1"))
    motivo = db.scalar(select(MotivoBaja).limit(1))
    db.add(producto)
    db.flush()
    db.refresh(producto)
    return {"usuario": usuario, "producto": producto, "motivo": motivo, "categoria": cat}


def _mov(base, **extra):
    datos = dict(tipo=TipoMovimientoStock.INGRESO_PROVEEDOR, producto_id=base["producto"].id, cantidad=5,
                 stock_resultante=5, usuario_id=base["usuario"].id)
    datos.update(extra)
    return MovimientoStock(**datos)


def test_stock_y_minimo_por_defecto(db, base):
    p = base["producto"]
    assert (p.stock, p.stock_minimo, p.bajo_minimo) == (0, 0, False)
    p.stock_minimo, p.stock = 3, 3
    assert p.bajo_minimo
    p.stock = 4
    assert not p.bajo_minimo
    p.stock_minimo = -1
    with pytest.raises(IntegrityError):
        db.flush()


def test_movimiento_valido(db, base):
    db.add(_mov(base))
    db.flush()
    assert db.execute(text("SELECT tipo::text FROM movimientos_stock")).scalars().all()[-1] == "ingreso_proveedor"


@pytest.mark.parametrize("extra", [
    {"cantidad": 0},
    {"cantidad": -1},                                                          # ingreso negativo
    {"tipo": TipoMovimientoStock.BAJA, "cantidad": 2},                        # baja positiva
    {"tipo": TipoMovimientoStock.BAJA, "cantidad": -2},                       # baja sin motivo
    {"tipo": TipoMovimientoStock.VENTA, "cantidad": -1},                      # venta sin referencia
    {"tipo": TipoMovimientoStock.ANULACION_VENTA, "cantidad": 1},             # anulación sin referencia
    {"tipo": TipoMovimientoStock.AJUSTE_AUDITORIA, "cantidad": 1},            # ajuste sin auditoría
])
def test_checks_de_movimientos(db, base, extra):
    db.add(_mov(base, **extra))
    with pytest.raises(IntegrityError):
        db.flush()


def test_baja_con_motivo_y_venta_con_referencia(db, base):
    # referencia_venta_id es FK (sesión 06): no acepta un id inventado.
    venta = Venta(numero="V-100002", usuario_id=base["usuario"].id)
    db.add(venta)
    db.flush()
    db.add_all([_mov(base, tipo=TipoMovimientoStock.BAJA, cantidad=-1, motivo_baja_id=base["motivo"].id),
                _mov(base, tipo=TipoMovimientoStock.VENTA, cantidad=-1, referencia_venta_id=venta.id)])
    db.flush()


def test_una_sola_auditoria_en_curso_y_diferencia_generada(db, base):
    a = AuditoriaInventario(usuario_id=base["usuario"].id)
    db.add(a)
    db.flush()
    assert a.estado is EstadoAuditoriaInventario.EN_CURSO
    item = AuditoriaItem(auditoria_id=a.id, producto_id=base["producto"].id, cantidad_sistema=5, cantidad_contada=3)
    db.add(item)
    db.flush()
    db.refresh(item)
    assert item.diferencia == -2
    db.add(AuditoriaInventario(usuario_id=base["usuario"].id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_item_unico_y_contada_no_negativa(db, base):
    a = AuditoriaInventario(usuario_id=base["usuario"].id)
    db.add(a)
    db.flush()
    db.add(AuditoriaItem(auditoria_id=a.id, producto_id=base["producto"].id, cantidad_sistema=0, cantidad_contada=-1))
    with pytest.raises(IntegrityError):
        db.flush()
