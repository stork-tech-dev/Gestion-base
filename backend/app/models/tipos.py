"""Tipos compartidos por los modelos."""
from sqlalchemy import Enum as SAEnum


def enum_db(tipo, nombre: str) -> SAEnum:
    """Enum de Postgres que guarda los VALORES (en minúscula), no los nombres
    de los miembros. El tipo se crea en la migración, no desde el modelo."""
    return SAEnum(tipo, name=nombre, values_callable=lambda e: [i.value for i in e])
