"""Verifica que conftest._verificar_entorno_seguro aborte toda la corrida
(pytest.exit) antes de recrear la base si algo indica que podría no ser la
base de test (ver conftest.py::_recrear_base)."""
import pytest

from config import settings
from tests.conftest import _verificar_entorno_seguro


def test_aborta_si_hay_database_url_override(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL_OVERRIDE", "postgresql://otra/base")
    with pytest.raises(pytest.exit.Exception):
        _verificar_entorno_seguro()


def test_aborta_si_postgres_db_no_termina_en_test(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL_OVERRIDE", None)
    monkeypatch.setattr(settings, "POSTGRES_DB", "gestion")
    with pytest.raises(pytest.exit.Exception):
        _verificar_entorno_seguro()


def test_no_aborta_con_configuracion_de_test_correcta(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL_OVERRIDE", None)
    monkeypatch.setattr(settings, "POSTGRES_DB", "gestion_test")
    _verificar_entorno_seguro()  # no debe lanzar
