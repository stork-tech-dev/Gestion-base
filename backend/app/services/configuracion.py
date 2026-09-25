"""Lectura de configuracion_sistema: única vía para todos los services."""
from sqlalchemy import select

from app.models.configuracion import ConfiguracionSistema


def obtener_configuracion(db) -> ConfiguracionSistema:
    config = db.scalar(select(ConfiguracionSistema).limit(1))
    if config is None:
        raise RuntimeError("Falta la fila de configuracion_sistema: ejecutar migrations/seed.sql")
    return config
