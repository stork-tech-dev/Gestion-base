"""Tests de Settings (config.py): URL de conexión, zona horaria del engine
y defaults de seguridad que no deben llegar a producción."""
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url

from config import Settings, settings


def test_database_url_hace_url_encoding_de_password_con_caracteres_especiales():
    cfg = Settings(_env_file=None, POSTGRES_PASSWORD="p@ss/w#rd?+%")
    url = make_url(cfg.DATABASE_URL)
    assert url.password == "p@ss/w#rd?+%"


def test_engine_de_la_app_usa_la_zona_horaria_configurada(db):
    assert db.execute(text("SHOW timezone")).scalar() == settings.TIMEZONE


def test_produccion_exige_jwt_secret_distinto_del_default_y_de_32_o_mas_caracteres():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET="cambiar-en-produccion")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET="corto-de-menos-de-32")
    # Con un secreto propio y suficientemente largo no debe fallar.
    Settings(_env_file=None, APP_ENV="production", JWT_SECRET="x" * 32)


def test_fuera_de_produccion_no_exige_jwt_secret_fuerte():
    Settings(_env_file=None, APP_ENV="development", JWT_SECRET="cambiar-en-produccion")


def test_produccion_rechaza_el_secreto_de_ejemplo():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET="cambiar-por-un-secreto-largo-y-aleatorio")


def test_sesion_inactividad_siempre_debe_ser_mayor_o_igual_al_access_token():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JWT_ACCESS_TOKEN_MINUTES=30, SESION_INACTIVIDAD_MINUTOS=10)
    # Igual está permitido (>=).
    Settings(_env_file=None, JWT_ACCESS_TOKEN_MINUTES=30, SESION_INACTIVIDAD_MINUTOS=30)


def test_cors_origins_rechaza_asterisco():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS="*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS="http://localhost:8000,*")
    # Sin asterisco no debe fallar.
    Settings(_env_file=None, CORS_ORIGINS="http://localhost:8000,http://otra.com")
