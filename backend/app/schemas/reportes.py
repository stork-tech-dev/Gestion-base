"""Reportes (sesión 09): filtros, catálogo, opciones y respuesta. Los importes
viajan crudos (Decimal como string, fechas ISO); el formato lo pone cada
consumidor (pantalla, Excel, PDF)."""
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ventas import Referencia

# BIGINT: un id mayor llegaría a la base y daría 500.
ID_MAXIMO = 2**63 - 1


class TipoColumna(str, Enum):
    TEXTO = "texto"
    ENTERO = "entero"
    MONEDA = "moneda"
    PORCENTAJE = "porcentaje"   # 0 a 100, no 0 a 1
    FECHA = "fecha"
    MES = "mes"                 # primer día del mes (ISO); se muestra mm/aaaa


class Agrupar(str, Enum):
    DIA = "dia"
    MES = "mes"
    PRODUCTO = "producto"
    CATEGORIA = "categoria"
    PROVEEDOR = "proveedor"


class Orden(str, Enum):
    UNIDADES = "unidades"
    IMPORTE = "importe"


class FiltrosReporte(BaseModel):
    """Query params comunes a todos los reportes. Cada reporte acepta solo los
    suyos (`DefinicionReporte.filtros_admitidos`, el resto → 422) y el motor
    completa los valores por defecto (`motor.normalizar_filtros`)."""

    model_config = ConfigDict(extra="forbid")

    desde: date | None = None
    hasta: date | None = None
    agrupar: Agrupar | None = None
    nivel: int | None = Field(default=None, ge=1, le=5)
    orden: Orden | None = None
    limite: int | None = Field(default=None, ge=1, le=500)
    proveedor_id: int | None = Field(default=None, ge=1, le=ID_MAXIMO)
    categoria_id: int | None = Field(default=None, ge=1, le=ID_MAXIMO)
    usuario_id: int | None = Field(default=None, ge=1, le=ID_MAXIMO)
    medio_de_pago_id: int | None = Field(default=None, ge=1, le=ID_MAXIMO)


class ColumnaResponse(BaseModel):
    clave: str
    titulo: str
    tipo: TipoColumna


class ReporteCatalogo(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    filtros_admitidos: list[str]
    agrupaciones: list[Agrupar]


class ReporteResponse(BaseModel):
    clave: str
    nombre: str
    filtros: FiltrosReporte          # ya normalizados (con los valores por defecto)
    columnas: list[ColumnaResponse]
    filas: list[dict[str, Any]]      # {clave de columna: valor crudo}
    totales: dict[str, Any]          # mismas claves; las de texto van en null
    generado_en: datetime


class CategoriaOpcion(BaseModel):
    id: int
    nombre: str                      # camino completo ("Ropa > Remeras")
    nivel: int


class OpcionesReportes(BaseModel):
    """Catálogos de los filtros, con el permiso de Reportes (sin pedir los de otros módulos)."""
    proveedores: list[Referencia]
    categorias: list[CategoriaOpcion]
    vendedores: list[Referencia]
    medios_de_pago: list[Referencia]
