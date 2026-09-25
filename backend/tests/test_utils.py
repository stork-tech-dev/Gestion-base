from datetime import timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import literal, select

from app.core.utils import (
    ahora,
    ahora_db,
    capitalizar_inicial,
    ip_de_request,
    normalizar_texto,
    redondear,
    redondear_hacia_abajo,
    redondear_hacia_arriba,
    sin_tildes,
    sin_tildes_sql,
)


def test_ahora_con_zona_y_ahora_db_sin_zona():
    assert ahora().tzinfo is not None
    assert ahora().utcoffset() is not None
    assert ahora_db().tzinfo is None
    # ahora_db es la misma hora local, sin zona
    assert abs((ahora().replace(tzinfo=None) - ahora_db()).total_seconds()) < 2


def test_redondear_half_up():
    assert redondear(Decimal("2.345")) == Decimal("2.35")
    assert redondear(Decimal("2.344")) == Decimal("2.34")
    assert redondear(2.5, 0) == Decimal("3")
    assert redondear("10") == Decimal("10.00")


def test_redondear_hacia_arriba_al_multiplo():
    assert redondear_hacia_arriba(Decimal("12001"), Decimal("1000")) == Decimal("13000.00")
    assert redondear_hacia_arriba(Decimal("12000"), 1000) == Decimal("12000.00")
    assert redondear_hacia_arriba(Decimal("0.01"), 100) == Decimal("100.00")


def test_redondear_hacia_arriba_multiplo_no_positivo_no_redondea():
    assert redondear_hacia_arriba(Decimal("12001.555"), 0) == Decimal("12001.56")
    assert redondear_hacia_arriba(Decimal("12001.5"), -5) == Decimal("12001.50")


def test_redondear_hacia_abajo_al_multiplo():
    assert redondear_hacia_abajo(Decimal("12999"), 1000) == Decimal("12000.00")
    assert redondear_hacia_abajo(Decimal("12000"), 1000) == Decimal("12000.00")
    assert redondear_hacia_abajo(Decimal("99.99"), 0) == Decimal("99.99")


def test_normalizar_texto():
    assert normalizar_texto("  hola    mundo ") == "hola mundo"
    assert normalizar_texto("   ") is None
    assert normalizar_texto("") is None
    assert normalizar_texto(None) is None


def test_capitalizar_inicial_no_toca_el_resto():
    assert capitalizar_inicial("remera AZUL talle M") == "Remera AZUL talle M"
    assert capitalizar_inicial("  ñandú  ") == "Ñandú"
    assert capitalizar_inicial(None) is None


def test_sin_tildes():
    assert sin_tildes("Córdoba Ñandú pingüino ÁÉÍÓÚÜ") == "Cordoba Nandu pinguino AEIOUU"
    assert sin_tildes(None) is None


def test_sin_tildes_sql_usa_la_misma_tabla(db):
    assert db.scalar(select(sin_tildes_sql(literal("Córdoba Ñandú")))) == "Cordoba Nandu"


def test_ip_de_request_respeta_x_forwarded_for():
    con_proxy = SimpleNamespace(
        headers={"x-forwarded-for": "200.1.1.1, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.2")
    )
    directo = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))
    sin_cliente = SimpleNamespace(headers={}, client=None)
    assert ip_de_request(con_proxy) == "200.1.1.1"
    assert ip_de_request(directo) == "10.0.0.2"
    assert ip_de_request(sin_cliente) is None
