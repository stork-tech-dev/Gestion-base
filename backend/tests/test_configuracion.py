from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.configuracion import obtener_configuracion


def test_obtener_configuracion_devuelve_los_valores_del_seed(db):
    config = obtener_configuracion(db)
    assert config.redondeo == Decimal("1000.00")
    assert config.margen_default == Decimal("100.00")
    assert config.descuento_maximo == Decimal("30.00")
    assert config.tope_descuento_venta == Decimal("50.00")


def test_configuracion_es_fila_unica(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta) "
                "VALUES (1, 1, 1, 1)"
            )
        )


@pytest.mark.parametrize(
    "columna, valor",
    [("descuento_maximo", 101), ("tope_descuento_venta", -1), ("margen_default", 1001), ("redondeo", -1)],
)
def test_configuracion_rechaza_valores_fuera_de_rango(db, columna, valor):
    with pytest.raises(IntegrityError):
        db.execute(text(f"UPDATE configuracion_sistema SET {columna} = :valor"), {"valor": valor})
