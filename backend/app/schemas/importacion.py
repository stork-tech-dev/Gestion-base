"""Esquemas de la importación inicial desde Excel (sesión 08)."""
from enum import Enum

from pydantic import BaseModel


class TipoImportacion(str, Enum):
    PROVEEDORES = "proveedores"
    CLIENTES = "clientes"
    PRODUCTOS = "productos"


class ErrorImportacion(BaseModel):
    fila: int                  # número de fila en el Excel (el encabezado es la 1)
    columna: str | None        # None = error de la fila en general
    error: str


class ResultadoImportacion(BaseModel):
    tipo: TipoImportacion
    filas_leidas: int
    filas_validas: int         # filas sin error (en validar: las que se crearían)
    creados: int               # 0 si no se aplicó
    categorias_nuevas: list[str]   # caminos "Ropa > Remeras" (solo productos)
    errores: list[ErrorImportacion]
    aplicado: bool
