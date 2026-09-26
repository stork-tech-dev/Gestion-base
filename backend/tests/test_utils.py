from datetime import timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import literal, select

from config import settings
from app.core.utils import (
    ahora,
    ahora_db,
    capitalizar_inicial,
    filtro_texto,
    ip_de_request,
    normalizar_texto,
    paginar,
    patron_ilike,
    rango_fechas,
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


def test_redondear_hacia_arriba_usa_half_up_en_centavos():
    # Tie case: 0.001 al múltiplo 0.005 debe redondear hacia arriba a 0.01
    assert redondear_hacia_arriba(Decimal("0.001"), Decimal("0.005")) == Decimal("0.01")


def test_redondear_hacia_abajo_usa_half_up_en_centavos():
    # Tie case: 0.009 al múltiplo 0.005 debe dar 0.01 (floor es 0.005, luego half-up)
    assert redondear_hacia_abajo(Decimal("0.009"), Decimal("0.005")) == Decimal("0.01")


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


def test_patron_ilike_escapa_comodines_de_like():
    assert patron_ilike("a_b%c") == "%a\\_b\\%c%"
    assert patron_ilike("x\\y") == "%x\\\\y%"


def test_filtro_texto_ignora_mayusculas_y_tildes(db):
    assert db.scalar(select(filtro_texto(literal("Depósito"), "deposito"))) is True
    assert db.scalar(select(filtro_texto(literal("Depósito"), "OTRA COSA"))) is False


def test_ip_de_request_con_0_proxies_ignora_xff_falsificado(monkeypatch):
    """0 proxies de confianza (default): XFF lo controla el cliente y se ignora."""
    monkeypatch.setattr(settings, "PROXIES_DE_CONFIANZA", 0)
    falsificado = SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4"}, client=SimpleNamespace(host="10.0.0.2")
    )
    directo = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))
    assert ip_de_request(falsificado) == "10.0.0.2"
    assert ip_de_request(directo) == "10.0.0.2"


def test_ip_de_request_con_1_proxy_toma_el_ultimo(monkeypatch):
    monkeypatch.setattr(settings, "PROXIES_DE_CONFIANZA", 1)
    con_proxy = SimpleNamespace(
        headers={"x-forwarded-for": "200.1.1.1, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.2")
    )
    assert ip_de_request(con_proxy) == "10.0.0.1"


def test_ip_de_request_con_2_proxies_toma_el_anteultimo(monkeypatch):
    monkeypatch.setattr(settings, "PROXIES_DE_CONFIANZA", 2)
    con_proxy = SimpleNamespace(
        headers={"x-forwarded-for": "200.1.1.1, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.2")
    )
    assert ip_de_request(con_proxy) == "200.1.1.1"


def test_ip_de_request_xff_con_menos_entradas_que_proxies_usa_client_host(monkeypatch):
    monkeypatch.setattr(settings, "PROXIES_DE_CONFIANZA", 2)
    xff_corto = SimpleNamespace(
        headers={"x-forwarded-for": "10.0.0.1"}, client=SimpleNamespace(host="10.0.0.2")
    )
    assert ip_de_request(xff_corto) == "10.0.0.2"


def test_ip_de_request_sin_cliente_devuelve_none(monkeypatch):
    monkeypatch.setattr(settings, "PROXIES_DE_CONFIANZA", 0)
    sin_cliente = SimpleNamespace(headers={}, client=None)
    assert ip_de_request(sin_cliente) is None


def test_paginar_hace_clamp():
    assert paginar(0, 0, 100) == (1, 1)
    assert paginar(3, 500, 100) == (3, 100)
    assert paginar(2, 10, 100) == (2, 10)


def test_rango_fechas_con_hasta_inclusivo(db):
    from datetime import date, datetime

    from sqlalchemy import DateTime, cast

    columna = cast(literal(datetime(2026, 9, 25, 23, 59, 59)), DateTime)
    assert rango_fechas(columna, None, None) == []
    condiciones = rango_fechas(columna, date(2026, 9, 25), date(2026, 9, 25))
    assert len(condiciones) == 2
    assert db.scalar(select(literal(True)).where(*condiciones)) is True
    assert db.scalar(select(literal(True)).where(*rango_fechas(columna, None, date(2026, 9, 24)))) is None
    assert db.scalar(select(literal(True)).where(*rango_fechas(columna, date(2026, 9, 26), None))) is None
