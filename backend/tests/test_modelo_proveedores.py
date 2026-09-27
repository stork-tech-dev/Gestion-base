from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.utils import ahora_db
from app.models import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial, Usuario


def _admin(db):
    return db.scalar(select(Usuario).where(Usuario.username == "admin"))


def test_proveedor_en_pesos_y_en_dolares(db):
    pesos = Proveedor(nombre="Textil Norte", moneda=Moneda.ARS)
    dolares = Proveedor(nombre="Importadora Sur", moneda=Moneda.USD, dolar_actual=Decimal("1250.50"))
    db.add_all([pesos, dolares])
    db.flush()
    assert pesos.estado is EstadoProveedor.ACTIVO and pesos.activo and not pesos.en_dolares
    assert dolares.en_dolares and dolares.dolar_actual == Decimal("1250.50")
    assert db.execute(text("SELECT moneda::text FROM proveedores WHERE id = :i"), {"i": dolares.id}).scalar_one() == "usd"


@pytest.mark.parametrize(
    "moneda, dolar",
    [(Moneda.ARS, Decimal("10")), (Moneda.USD, None), (Moneda.USD, Decimal("0")), (Moneda.USD, Decimal("-1"))],
)
def test_check_moneda_y_dolar(db, moneda, dolar):
    db.add(Proveedor(nombre="Con dólar mal cargado", moneda=moneda, dolar_actual=dolar))
    with pytest.raises(IntegrityError):
        db.flush()


def test_nombre_unico_sin_mayusculas_ni_tildes(db):
    db.add(Proveedor(nombre="Córdoba Textil", moneda=Moneda.ARS))
    db.flush()
    db.add(Proveedor(nombre="cordoba textil", moneda=Moneda.ARS))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE proveedor_dolar_historial SET valor_nuevo = 1", "DELETE FROM proveedor_dolar_historial",
     "TRUNCATE proveedor_dolar_historial"],
)
def test_historial_del_dolar_es_inmutable(db, sentencia):
    proveedor = Proveedor(nombre="Importadora Este", moneda=Moneda.USD, dolar_actual=Decimal("1000"))
    db.add(proveedor)
    db.flush()
    db.add(ProveedorDolarHistorial(
        proveedor_id=proveedor.id, valor_anterior=Decimal("1000"), valor_nuevo=Decimal("1100"),
        usuario_id=_admin(db).id, origen=OrigenCambioDolar.MANUAL, timestamp=ahora_db(),
    ))
    db.flush()
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)
