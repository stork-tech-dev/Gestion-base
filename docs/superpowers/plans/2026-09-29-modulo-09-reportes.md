# Módulo 09 — Reportes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seis reportes de solo lectura (ventas por período, medios de pago, vendedores, productos más vendidos, rentabilidad y stock valorizado), consultables en pantalla y exportables a Excel y PDF, sobre un motor único.

**Architecture:** Cada reporte es una `DefinicionReporte` (columnas + consulta SQL agregada) en `app/reports/definiciones/<clave>.py`, registrada en `REPORTES`. El motor (`app/reports/motor.py`) valida los filtros, corre la consulta, normaliza cada valor según el tipo de su columna y exporta a Excel (`core/excel.py`) o PDF (una sola plantilla). `services/reportes.py` orquesta y audita las exportaciones; el router expone JSON, Excel y PDF con los mismos query params. La pantalla es una sola, genérica, armada con las columnas que devuelve la API.

**Tech Stack:** FastAPI 0.115 (query params como modelo Pydantic), SQLAlchemy 2 (CTE recursiva, `GROUP BY`), PostgreSQL 15, openpyxl, WeasyPrint, Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/09_reportes.md` + `docs/superpowers/specs/2026-09-29-modulo-09-reportes-design.md` + `CLAUDE.md`. Donde este plan y el spec difieran, manda la sección "Decisiones y desvíos" de este plan.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `modulo-09-reportes` (ya creada desde `dev`). UN commit por tarea: `feat(reportes): …` + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout de otra rama. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo:** verificar con tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest -p no:warnings`, suite completa antes de cada commit). JS: `node --check` y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores `DatoInvalido` 400 / `SinPermiso` 403 / `NoEncontrado` 404 / `ReglaDeNegocio` 409 / `NoProcesable` 422 (nuevo en la Task 1); auditoría con `registrar_auditoria`. Routers hacen `db.commit()`.
- Dinero: siempre `Decimal`, nunca `float`. Redondeo con `core/utils.py::redondear` (half-up, 2 decimales).
- **Toda agregación en SQL (`GROUP BY`)**, nunca trayendo filas de detalle a Python. En Python solo se combinan filas YA agregadas (etiquetas, cocientes, unir anuladas con confirmadas).
- La API devuelve datos crudos (Principio 1): Decimal como string, fechas ISO. Excepción aceptada: la etiqueta de un grupo (nombre del vendedor, camino de la categoría, "3 cuotas +10%") es texto.
- **Venta que cuenta** = `estado = 'confirmada'`, filtrada por `confirmada_en`. `en_curso` nunca aparece; `anulada` solo en las columnas "Anuladas" de `ventas-periodo`.
- El stock se agrega con `services.stock.STOCK_SQL` (Task 1), nunca con `Producto.stock` directo (decisión multi-local).
- Pantallas: `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; sin `x-html`; reusar macros de `templates/components/`; mobile-first, tablas en `overflow-x-auto`.

## Decisiones y desvíos

Decisiones de producto (usuario, al inicio del módulo):

1. **Anuladas en `ventas-periodo`** cuentan en el período de su `anulada_en`.
2. **`ventas-periodo` no admite `proveedor_id` ni `categoria_id`** (422).
3. **`stock-valorizado`**: columnas "Ganancia potencial" ($) y "Margen potencial %" (ganancia / valorizado a venta).
4. **Costo del medio sin plan = 0** (no se toca el módulo 06).

Desvíos técnicos:

5. **`REPORTES` vive en `app/reports/definiciones/__init__.py`** (no en `motor.py`): las definiciones importan `Columna` y `DefinicionReporte` del motor, así que el registro en el motor sería una importación circular. Agregar un reporte = escribir su módulo + una línea en ese registro.
6. **`columnas` es una función de los filtros** (`columnas(filtros) -> list[Columna]`): "Período" es fecha o mes, "Grupo" se llama Categoría o Proveedor, y `productos-vendidos` por producto tiene Código + Descripción.
7. **`agrupaciones`** es un campo de la definición (la primera es la de por defecto). `nivel` por defecto 1 y solo se acepta al agrupar por categoría (con otra agrupación → 422). `orden` por defecto `unidades`, `limite` por defecto 50.
8. **Filtros por reporte:** `ventas-periodo`: fechas + agrupar (dia|mes). `medios-pago`: fechas + `medio_de_pago_id` + `usuario_id`. `vendedores`: fechas + `usuario_id`. `productos-vendidos`: fechas + agrupar (producto|categoria) + nivel + orden + limite + proveedor + categoría. `rentabilidad`: fechas + agrupar (dia|mes|categoria|proveedor) + nivel + proveedor + categoría. `stock-valorizado`: agrupar (categoria|proveedor) + nivel + proveedor + categoría.
9. **422** para: filtro no admitido con valor, parámetro desconocido (`extra="forbid"`), agrupación no admitida, `nivel` sin agrupar por categoría, `desde > hasta`, y los rangos de Pydantic (`nivel` 1-5, `limite` 1-500, ids 1..2^63-1). **409** para un rango de más de 366 días (contando ambos extremos).
10. **`GET /api/v1/reportes/opciones`** (REPORTES ver): proveedores, categorías (camino + nivel), vendedores (usuarios con alguna venta confirmada o anulada, incluidos los inactivos) y medios (incluidos los inactivos). La pantalla no pide catálogos de otros módulos (evita el 403 del pendiente del módulo 05).
11. **Totales**: en SQL, sobre el mismo conjunto filtrado. En `productos-vendidos` son de TODO el conjunto filtrado (no solo las `limite` filas mostradas): así "% del total" de cada fila es sobre el total real y la fila de totales siempre dice 100 %.
12. **Porcentajes** viajan como número de 0 a 100 con 2 decimales ("48.72"); la pantalla muestra 1 decimal, el Excel usa formato `0.0"%"`.
13. **`ticket promedio` y `margen %` con divisor 0 → 0.**
14. **Orden de las filas:** períodos cronológicos; medios por nombre y plan (sin plan primero); vendedores por total desc; productos por `orden` (desempate por la otra medida); rentabilidad por categoría/proveedor y stock valorizado por importe desc.
15. **Auditoría:** `accion="reporte.exportar"`, `entidad="reporte"`, `entidad_id=None`, `estado_nuevo={"clave", "formato" ("excel"|"pdf"), "filtros" (normalizados, sin nulos)}`. Consultar en JSON no audita.
16. **Nombre de archivo:** `reporte-<clave>-<desde>_<hasta>.<ext>`; `stock-valorizado` (sin fechas) usa la fecha de hoy.
17. Categoría inexistente en `categoria_id` → sin filas (no 404), igual que un proveedor inexistente.

---

## File Structure

```
backend/app/core/errores.py                      (mod) T1  NoProcesable (422)
backend/app/core/etiquetas.py                    (mod) T1  AGRUPACIONES, ORDENES
backend/app/core/excel.py                        (mod) T1  generar_reporte
backend/app/services/stock.py                    (mod) T1  STOCK_SQL
backend/app/schemas/reportes.py                  (new) T1  TipoColumna, Agrupar, Orden, FiltrosReporte, respuestas
backend/app/reports/motor.py                     (new) T1  Columna, DefinicionReporte, normalizar_filtros, generar, exportar_*
backend/app/reports/definiciones/__init__.py     (new) T1  REPORTES, obtener_reporte   (mod) T2 suma 5 reportes
backend/app/reports/definiciones/_comunes.py     (new) T1  piezas SQL compartidas
backend/app/reports/definiciones/stock_valorizado.py (new) T1
backend/app/reports/definiciones/ventas_periodo.py   (new) T2
backend/app/reports/definiciones/medios_pago.py      (new) T2
backend/app/reports/definiciones/vendedores.py       (new) T2
backend/app/reports/definiciones/productos_vendidos.py (new) T2
backend/app/reports/definiciones/rentabilidad.py     (new) T2
backend/app/templates/reports/reporte.html       (new) T1  plantilla PDF única
backend/app/services/reportes.py                 (new) T1  catalogo, consultar, exportar, opciones
backend/app/api/v1/reportes.py                   (new) T1
backend/app/api/v1/__init__.py                   (mod) T1
backend/app/api/pages.py                         (mod) T3  PAGINA_REPORTES, hub y pantalla
backend/app/templates/pages/reportes/hub.html    (new) T3
backend/app/templates/pages/reportes/reporte.html (new) T3
backend/app/static/js/reporte.js                 (new) T3
backend/tests/test_excel.py                      (mod) T1
backend/tests/test_reportes.py                   (new) T1
backend/tests/test_reportes_ventas.py            (new) T2
backend/tests/test_paginas_reportes.py           (new) T3
backend/tests_js/reporte.test.mjs                (new) T3
```

---

### Task 1: Motor, exportadores, API y reporte de stock valorizado

**Revisión:** CON revisor (dinero, permisos, auditoría).

**Files:**
- Modify: `backend/app/core/errores.py`, `backend/app/core/etiquetas.py`, `backend/app/core/excel.py`, `backend/app/services/stock.py`, `backend/app/api/v1/__init__.py`
- Create: `backend/app/schemas/reportes.py`, `backend/app/reports/motor.py`, `backend/app/reports/definiciones/__init__.py`, `backend/app/reports/definiciones/_comunes.py`, `backend/app/reports/definiciones/stock_valorizado.py`, `backend/app/templates/reports/reporte.html`, `backend/app/services/reportes.py`, `backend/app/api/v1/reportes.py`
- Test: `backend/tests/test_excel.py`, `backend/tests/test_reportes.py`

**Interfaces:**
- Produces (lo usan las Tasks 2 y 3):
  - `app.schemas.reportes`: `TipoColumna` (`TEXTO, ENTERO, MONEDA, PORCENTAJE, FECHA, MES`), `Agrupar` (`DIA, MES, PRODUCTO, CATEGORIA, PROVEEDOR`), `Orden` (`UNIDADES, IMPORTE`), `FiltrosReporte`.
  - `app.reports.motor`: `Columna(clave, titulo, tipo)`, `DefinicionReporte(clave, nombre, descripcion, filtros_admitidos, columnas, consulta, agrupaciones=())`, `titulo_de_agrupacion(agrupar) -> str`.
  - `app.reports.definiciones._comunes`: `ventas_confirmadas(filtros) -> list`, `unidades_por_venta(filtros)` (subquery `venta_id, unidades`), `periodo(columna, agrupar)`, `condiciones_de_producto(db, filtros) -> list`, `grupo_de_producto(db, filtros) -> (unir, grupo_id_label, etiquetas: dict)`, `costo_en_pesos()`, `filas_y_totales(db, consulta, grupos, medidas, *, orden=None, limite=None) -> (list[dict], dict)`, `dividir(a, b) -> Decimal`, `porcentaje(parte, total) -> Decimal`.
  - `app.reports.definiciones`: `REPORTES: dict[str, DefinicionReporte]`, `obtener_reporte(clave)`.
  - `app.core.etiquetas`: `AGRUPACIONES`, `ORDENES` (listas de `(valor, texto)`).
  - `app.services.stock.STOCK_SQL`.

- [ ] **Step 1: Error 422, etiquetas y accesor SQL del stock**

En `backend/app/core/errores.py`, después de `ReglaDeNegocio`:

```python
class NoProcesable(ErrorDeNegocio):
    """Parámetros bien formados que no aplican (ej. un filtro que el reporte no admite)."""
    status_code = 422
```

Al final de `backend/app/core/etiquetas.py`:

```python
# Reportes (sesión 09): "Agrupar por" y "Orden" de la pantalla, del Excel y del PDF.
AGRUPACIONES = [
    ("dia", "Día"),
    ("mes", "Mes"),
    ("producto", "Producto"),
    ("categoria", "Categoría"),
    ("proveedor", "Proveedor"),
]
ORDENES = [
    ("unidades", "Unidades"),
    ("importe", "Importe"),
]
```

En `backend/app/services/stock.py`, después de los imports:

```python
# Única expresión SQL del stock de un producto (hoy, el del único local). Los
# reportes que agregan stock en la base la usan en vez de Producto.stock: el
# día que haya multi-local se cambia acá y no en cada consulta.
STOCK_SQL = Producto.stock
```

- [ ] **Step 2: Test de `generar_reporte` (Excel)**

Agregar a `backend/tests/test_excel.py` (sumar a los imports existentes lo que falte: `date`, `Decimal`, `BytesIO`, `load_workbook`, `generar_reporte`):

```python
def test_generar_reporte_titulo_filtros_formatos_y_totales():
    contenido = generar_reporte(
        "Ventas por período",
        [("Desde", "01/03/2025"), ("Hasta", "31/03/2025")],
        [("Período", "DD/MM/YYYY"), ("Total", '"$" #,##0.00'), ("Nombre", None)],
        [[date(2025, 3, 1), Decimal("10.50"), "=HYPERLINK(1)"]],
        ["Total", Decimal("10.50"), None],
    )
    hoja = load_workbook(BytesIO(contenido)).active
    assert hoja["A1"].value == "Ventas por período" and hoja["A1"].font.bold
    assert hoja["A2"].value == "Desde: 01/03/2025" and hoja["A3"].value == "Hasta: 31/03/2025"
    assert hoja["A4"].value is None                       # fila en blanco antes de la tabla
    assert [c.value for c in hoja[5]] == ["Período", "Total", "Nombre"] and hoja["A5"].font.bold
    assert hoja["A6"].number_format == "DD/MM/YYYY" and hoja["B6"].number_format == '"$" #,##0.00'
    assert hoja["C6"].value == "=HYPERLINK(1)" and hoja["C6"].data_type == "s"   # nunca una fórmula
    assert hoja["A7"].value == "Total" and hoja["A7"].font.bold and hoja["B7"].value == 10.5
    assert hoja.freeze_panes == "A6"
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_excel.py -q`
Expected: FAIL (`ImportError: cannot import name 'generar_reporte'`).

- [ ] **Step 3: `generar_reporte` en `core/excel.py`**

Actualizar el docstring del módulo ("…la importación inicial (módulo 08) y los reportes (módulo 09).") y agregar después de `generar_plantilla`:

```python
def generar_reporte(titulo: str, filtros: list[tuple[str, str]], columnas: list[tuple[str, str | None]],
                    filas: list[list], totales: list) -> bytes:
    """Libro de un reporte (módulo 09): título, filtros aplicados, una fila en
    blanco, encabezados en negrita, filas, fila de totales en negrita, formato
    numérico por columna (`columnas` = [(título, formato de Excel o None)]),
    anchos ajustados y panel congelado bajo el encabezado. Protegido contra
    fórmulas con `_textos_como_texto`."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte"
    hoja.cell(row=1, column=1, value=titulo).font = Font(bold=True, size=14)
    fila = 2
    for etiqueta, valor in filtros:
        hoja.cell(row=fila, column=1, value=f"{etiqueta}: {valor}")
        fila += 1
    encabezado = fila + 1   # una fila en blanco entre los filtros y la tabla
    for indice, (nombre, _) in enumerate(columnas, start=1):
        hoja.cell(row=encabezado, column=indice, value=nombre).font = Font(bold=True)
    for desplazamiento, valores in enumerate([*filas, totales], start=1):
        for indice, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=encabezado + desplazamiento, column=indice, value=valor)
            formato = columnas[indice - 1][1]
            if formato:
                celda.number_format = formato
    for celda in hoja[encabezado + len(filas) + 1]:
        celda.font = Font(bold=True)
    for indice, (nombre, _) in enumerate(columnas, start=1):
        valores = [nombre, *(f[indice - 1] for f in filas), totales[indice - 1]]
        largo = max(len(str(v)) for v in valores if v is not None)
        hoja.column_dimensions[get_column_letter(indice)].width = min(max(12, largo + 4), 60)
    hoja.freeze_panes = f"A{encabezado + 1}"
    _textos_como_texto(hoja)

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_excel.py -q`
Expected: PASS.

- [ ] **Step 4: Schemas `backend/app/schemas/reportes.py`**

```python
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
```

- [ ] **Step 5: Motor `backend/app/reports/motor.py`**

```python
"""Motor único de reportes (sesión 09). Una DefinicionReporte (columnas +
consulta SQL agregada) alcanza para el JSON, el Excel y el PDF: agregar un
reporte es escribir su módulo en app/reports/definiciones/ y sumarlo al
registro REPORTES de esa carpeta, sin tocar exportadores, plantilla ni pantalla."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.core import excel
from app.core.errores import NoProcesable, ReglaDeNegocio
from app.core.etiquetas import AGRUPACIONES, ORDENES
from app.core.templates import STATIC_DIR
from app.core.utils import ahora, ahora_db, redondear
from app.models import MedioDePago, Proveedor, Usuario
from app.reports import pdf
from app.schemas.reportes import Agrupar, FiltrosReporte, Orden, TipoColumna
from app.services.categorias import caminos

RANGO_MAXIMO_DIAS = 366
NIVEL_POR_DEFECTO = 1
LIMITE_POR_DEFECTO = 50
PLANTILLA_PDF = "reports/reporte.html"
COLUMNAS_PDF_VERTICAL = 6   # con más columnas, A4 apaisado
NUMERICOS = (TipoColumna.ENTERO, TipoColumna.MONEDA, TipoColumna.PORCENTAJE)
FORMATO_EXCEL = {
    TipoColumna.TEXTO: None,
    TipoColumna.ENTERO: "#,##0",
    TipoColumna.MONEDA: '"$" #,##0.00',
    TipoColumna.PORCENTAJE: '0.0"%"',
    TipoColumna.FECHA: "DD/MM/YYYY",
    TipoColumna.MES: "MM/YYYY",
}


@dataclass(frozen=True)
class Columna:
    clave: str
    titulo: str
    tipo: TipoColumna


@dataclass(frozen=True)
class DefinicionReporte:
    clave: str
    nombre: str
    descripcion: str
    filtros_admitidos: tuple[str, ...]
    # Las columnas pueden depender de los filtros (ej. "Período" es fecha o mes según `agrupar`).
    columnas: Callable[[FiltrosReporte], list[Columna]]
    # consulta(db, filtros) -> (filas, totales): dicts por clave de columna, agregados en SQL.
    consulta: Callable
    agrupaciones: tuple[Agrupar, ...] = ()   # la primera es la de por defecto

    @property
    def usa_fechas(self) -> bool:
        return "desde" in self.filtros_admitidos


def titulo_de_agrupacion(agrupar: Agrupar) -> str:
    """Título de la columna del grupo ("Día", "Categoría"…): mismos textos que el selector."""
    return dict(AGRUPACIONES)[agrupar.value]


def normalizar_filtros(definicion: DefinicionReporte, filtros: FiltrosReporte, hoy: date | None = None) -> FiltrosReporte:
    """Valida los filtros contra lo que admite el reporte y completa los
    valores por defecto. NoProcesable (422) si llega un filtro que el reporte
    no admite o que no aplica; ReglaDeNegocio (409) si el rango supera
    RANGO_MAXIMO_DIAS (contando ambos extremos)."""
    datos = filtros.model_dump(exclude_none=True)
    no_admitidos = sorted(set(datos) - set(definicion.filtros_admitidos))
    if no_admitidos:
        raise NoProcesable(f"El reporte '{definicion.nombre}' no admite: {', '.join(no_admitidos)}.")
    if definicion.usa_fechas:
        hoy = hoy or ahora().date()
        datos.setdefault("desde", hoy.replace(day=1))
        datos.setdefault("hasta", hoy)
        if datos["desde"] > datos["hasta"]:
            raise NoProcesable("La fecha 'desde' no puede ser posterior a 'hasta'.")
        if (datos["hasta"] - datos["desde"]).days + 1 > RANGO_MAXIMO_DIAS:
            raise ReglaDeNegocio(f"El rango de fechas no puede superar los {RANGO_MAXIMO_DIAS} días.")
    if definicion.agrupaciones:
        datos.setdefault("agrupar", definicion.agrupaciones[0])
        if datos["agrupar"] not in definicion.agrupaciones:
            raise NoProcesable(f"El reporte '{definicion.nombre}' no se agrupa por '{datos['agrupar'].value}'.")
    if "nivel" in definicion.filtros_admitidos:
        if datos.get("agrupar") is Agrupar.CATEGORIA:
            datos.setdefault("nivel", NIVEL_POR_DEFECTO)
        elif "nivel" in datos:
            raise NoProcesable("El nivel de categoría solo se usa al agrupar por categoría.")
    if "orden" in definicion.filtros_admitidos:
        datos.setdefault("orden", Orden.UNIDADES)
    if "limite" in definicion.filtros_admitidos:
        datos.setdefault("limite", LIMITE_POR_DEFECTO)
    return FiltrosReporte(**datos)


def _valor(tipo: TipoColumna, valor):
    """Valor crudo normalizado por tipo: enteros como int, importes y
    porcentajes con 2 decimales (un SUM sin filas da NULL → 0), fechas como date."""
    if tipo is TipoColumna.ENTERO:
        return int(valor or 0)
    if tipo in (TipoColumna.MONEDA, TipoColumna.PORCENTAJE):
        return redondear(valor or 0)
    if tipo in (TipoColumna.FECHA, TipoColumna.MES) and isinstance(valor, datetime):
        return valor.date()
    return valor


def _normalizar_fila(columnas: list[Columna], fila: dict) -> dict:
    return {c.clave: _valor(c.tipo, fila.get(c.clave)) for c in columnas}


def generar(db, definicion: DefinicionReporte, filtros: FiltrosReporte) -> dict:
    """Corre la consulta del reporte. Devuelve {clave, nombre, filtros
    (normalizados), columnas (list[Columna]), filas, totales, generado_en}."""
    filtros = normalizar_filtros(definicion, filtros)
    columnas = definicion.columnas(filtros)
    filas, totales = definicion.consulta(db, filtros)
    return {
        "clave": definicion.clave,
        "nombre": definicion.nombre,
        "filtros": filtros,
        "columnas": columnas,
        "filas": [_normalizar_fila(columnas, f) for f in filas],
        "totales": _normalizar_fila(columnas, totales),
        "generado_en": ahora_db(),
    }


def _nombre(db, modelo, id_: int) -> str:
    objeto = db.get(modelo, id_)
    return objeto.nombre if objeto is not None else f"#{id_}"


def describir_filtros(db, filtros: FiltrosReporte) -> list[tuple[str, str]]:
    """Filtros aplicados en texto legible (encabezado del Excel y del PDF)."""
    partes = []
    if filtros.desde:
        partes.append(("Desde", f"{filtros.desde:%d/%m/%Y}"))
    if filtros.hasta:
        partes.append(("Hasta", f"{filtros.hasta:%d/%m/%Y}"))
    if filtros.agrupar:
        partes.append(("Agrupar por", titulo_de_agrupacion(filtros.agrupar)))
    if filtros.nivel:
        partes.append(("Nivel de categoría", str(filtros.nivel)))
    if filtros.orden:
        partes.append(("Orden", dict(ORDENES)[filtros.orden.value]))
    if filtros.limite:
        partes.append(("Límite", str(filtros.limite)))
    if filtros.proveedor_id:
        partes.append(("Proveedor", _nombre(db, Proveedor, filtros.proveedor_id)))
    if filtros.categoria_id:
        partes.append(("Categoría", caminos(db).get(filtros.categoria_id, f"#{filtros.categoria_id}")))
    if filtros.usuario_id:
        partes.append(("Vendedor", _nombre(db, Usuario, filtros.usuario_id)))
    if filtros.medio_de_pago_id:
        partes.append(("Medio de pago", _nombre(db, MedioDePago, filtros.medio_de_pago_id)))
    return partes


def _con_etiqueta_total(valores: list) -> list:
    """Fila de totales: "Total" en la primera celda (siempre la del grupo, que no se totaliza)."""
    return ["Total", *valores[1:]]


def exportar_excel(db, resultado: dict) -> bytes:
    columnas = resultado["columnas"]
    return excel.generar_reporte(
        resultado["nombre"],
        describir_filtros(db, resultado["filtros"]),
        [(c.titulo, FORMATO_EXCEL[c.tipo]) for c in columnas],
        [[fila[c.clave] for c in columnas] for fila in resultado["filas"]],
        _con_etiqueta_total([resultado["totales"][c.clave] for c in columnas]),
    )


def _miles(valor, decimales: int = 2) -> str:
    """1234.5 → "1.234,50" (formato argentino)."""
    texto = f"{Decimal(valor):,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formatear(valor, tipo: TipoColumna) -> str:
    """Celda del PDF en formato argentino (el JSON y el Excel van crudos)."""
    if valor is None:
        return ""
    if tipo is TipoColumna.ENTERO:
        return _miles(valor, 0)
    if tipo is TipoColumna.MONEDA:
        return "$ " + _miles(valor)
    if tipo is TipoColumna.PORCENTAJE:
        return _miles(valor, 1) + " %"
    if tipo is TipoColumna.FECHA:
        return f"{valor:%d/%m/%Y}"
    if tipo is TipoColumna.MES:
        return f"{valor:%m/%Y}"
    return str(valor)


def exportar_pdf(db, resultado: dict) -> bytes:
    columnas = resultado["columnas"]
    logo = STATIC_DIR / "img" / "logo.svg"
    return pdf.imprimir(PLANTILLA_PDF, {
        "titulo": resultado["nombre"],
        "filtros": describir_filtros(db, resultado["filtros"]),
        "columnas": columnas,
        "alineaciones": ["numero" if c.tipo in NUMERICOS else "" for c in columnas],
        "filas": [[formatear(fila[c.clave], c.tipo) for c in columnas] for fila in resultado["filas"]],
        "totales": _con_etiqueta_total([formatear(resultado["totales"][c.clave], c.tipo) for c in columnas]),
        "apaisado": len(columnas) > COLUMNAS_PDF_VERTICAL,
        "emitido": f"{ahora():%d/%m/%Y %H:%M}",
        "logo": logo.resolve().as_uri() if logo.is_file() else None,
    })
```

- [ ] **Step 6: Piezas SQL comunes `backend/app/reports/definiciones/_comunes.py`**

```python
"""Piezas SQL compartidas por las definiciones de reportes (una sola
definición de "venta que cuenta", período, rama de categoría, categoría de
nivel N, costo en pesos y agregado filas + totales)."""
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import aliased

from app.core.utils import rango_fechas, redondear
from app.models import Categoria, EstadoVenta, Moneda, Producto, Proveedor, Venta, VentaItem
from app.schemas.reportes import Agrupar
from app.services.categorias import caminos, rama_de_ids


def ventas_confirmadas(filtros) -> list:
    """Condiciones de "venta que cuenta": confirmada, con confirmada_en en el
    rango (día completo). Las anuladas y en curso nunca suman."""
    return [Venta.estado == EstadoVenta.CONFIRMADA, *rango_fechas(Venta.confirmada_en, filtros.desde, filtros.hasta)]


def unidades_por_venta(filtros):
    """Subconsulta (venta_id, unidades) de las ventas que cuentan: se une a
    `ventas` sin multiplicar sus importes (venta_items tiene una fila por unidad)."""
    return (select(VentaItem.venta_id, func.count(VentaItem.id).label("unidades"))
            .join(Venta, Venta.id == VentaItem.venta_id)
            .where(*ventas_confirmadas(filtros))
            .group_by(VentaItem.venta_id)
            .subquery("unidades_por_venta"))


def periodo(columna, agrupar: Agrupar):
    """Día, o primer día del mes, de un TIMESTAMP (hora del negocio) como DATE."""
    return cast(func.date_trunc("month" if agrupar is Agrupar.MES else "day", columna), Date)


def condiciones_de_producto(db, filtros) -> list:
    """Filtros opcionales por proveedor y por rama de categoría del producto."""
    condiciones = []
    if filtros.proveedor_id:
        condiciones.append(Producto.proveedor_id == filtros.proveedor_id)
    if filtros.categoria_id:
        condiciones.append(Producto.categoria_id.in_(rama_de_ids(db, filtros.categoria_id)))
    return condiciones


def _categoria_de_nivel(nivel: int):
    """Subconsulta (categoria_id, grupo_id): cada categoría → su ancestro de
    nivel `nivel`, o ella misma si su rama es más corta. CTE recursiva que
    sube por los padres; `padre.nivel < nivel_ancestro` garantiza que termine
    aunque el árbol tuviera un ciclo."""
    ancestros = select(
        Categoria.id.label("categoria_id"), Categoria.id.label("ancestro_id"),
        Categoria.nivel.label("nivel_categoria"), Categoria.nivel.label("nivel_ancestro"),
    ).cte("ancestros", recursive=True)
    actual, padre = aliased(Categoria), aliased(Categoria)
    ancestros = ancestros.union_all(
        select(ancestros.c.categoria_id, padre.id, ancestros.c.nivel_categoria, padre.nivel)
        .select_from(ancestros)
        .join(actual, actual.id == ancestros.c.ancestro_id)
        .join(padre, (padre.id == actual.parent_id) & (padre.nivel < ancestros.c.nivel_ancestro))
    )
    return (select(ancestros.c.categoria_id, ancestros.c.ancestro_id.label("grupo_id"))
            .where(ancestros.c.nivel_ancestro == func.least(ancestros.c.nivel_categoria, nivel))
            .subquery("categoria_de_nivel"))


def grupo_de_producto(db, filtros):
    """Agrupación de productos por categoría (al nivel pedido) o por proveedor.
    Devuelve (unir, grupo, etiquetas): `unir(sentencia)` suma el JOIN que
    haga falta, `grupo` es la columna "grupo_id" y `etiquetas[grupo_id]` el
    texto del grupo (camino de la categoría o nombre del proveedor)."""
    if filtros.agrupar is Agrupar.CATEGORIA:
        mapa = _categoria_de_nivel(filtros.nivel)
        return (lambda sentencia: sentencia.join(mapa, mapa.c.categoria_id == Producto.categoria_id),
                mapa.c.grupo_id.label("grupo_id"), caminos(db))
    return (lambda sentencia: sentencia, Producto.proveedor_id.label("grupo_id"),
            dict(db.execute(select(Proveedor.id, Proveedor.nombre)).all()))


def costo_en_pesos():
    """Mismo cálculo que Producto.costo_en_pesos (dólar ACTUAL del proveedor),
    en SQL. Necesita el JOIN con proveedores."""
    return case((Proveedor.moneda == Moneda.USD, func.round(Producto.costo * Proveedor.dolar_actual, 2)),
                else_=Producto.costo)


def filas_y_totales(db, consulta, grupos: list, medidas: list, *, orden=None, limite=None):
    """Agrega en SQL. `consulta(*columnas)` devuelve el SELECT con sus JOIN y
    WHERE; se ejecuta agrupado por `grupos` (filas) y sin agrupar (totales,
    sobre el mismo conjunto filtrado y sin `limite`)."""
    sentencia = consulta(*grupos, *medidas).group_by(*grupos).order_by(*(orden if orden is not None else grupos))
    if limite:
        sentencia = sentencia.limit(limite)
    filas = [dict(fila) for fila in db.execute(sentencia).mappings()]
    totales = dict(db.execute(consulta(*medidas)).mappings().one())
    return filas, totales


def dividir(dividendo, divisor) -> Decimal:
    """Cociente con 2 decimales; 0 si el divisor es 0 (ticket promedio sin ventas)."""
    return redondear(Decimal(dividendo or 0) / Decimal(divisor)) if divisor else Decimal("0.00")


def porcentaje(parte, total) -> Decimal:
    """parte / total × 100 con 2 decimales; 0 si el total es 0."""
    return dividir(Decimal(parte or 0) * 100, total)
```

- [ ] **Step 7: Stock valorizado `backend/app/reports/definiciones/stock_valorizado.py`**

```python
"""Stock valorizado: foto ACTUAL (sin fechas) del stock de los productos
activos, con stock y sin stock infinito, a costo (en pesos, con el dólar
actual del proveedor) y a precio de venta."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Producto, Proveedor
from app.reports.definiciones._comunes import (
    condiciones_de_producto, costo_en_pesos, filas_y_totales, grupo_de_producto, porcentaje,
)
from app.reports.motor import Columna, DefinicionReporte, titulo_de_agrupacion
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T
from app.services.stock import STOCK_SQL


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("grupo", titulo_de_agrupacion(filtros.agrupar), T.TEXTO),
        Columna("productos", "Productos", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("valorizado_costo", "Valorizado a costo", T.MONEDA),
        Columna("valorizado_venta", "Valorizado a venta", T.MONEDA),
        Columna("ganancia_potencial", "Ganancia potencial", T.MONEDA),
        Columna("margen_potencial", "Margen potencial %", T.PORCENTAJE),
    ]


def _consulta(db, filtros):
    unir, grupo, etiquetas = grupo_de_producto(db, filtros)
    condiciones = [Producto.activo.is_(True), Producto.stock_infinito.is_(False), STOCK_SQL > 0,
                   *condiciones_de_producto(db, filtros)]

    def consulta(*columnas):
        sentencia = select(*columnas).select_from(Producto).join(Proveedor, Proveedor.id == Producto.proveedor_id)
        return unir(sentencia).where(*condiciones)

    valorizado_costo = func.sum(costo_en_pesos() * STOCK_SQL).label("valorizado_costo")
    filas, totales = filas_y_totales(db, consulta, [grupo], [
        func.count(Producto.id).label("productos"),
        func.sum(STOCK_SQL).label("unidades"),
        valorizado_costo,
        func.sum(Producto.precio_venta * STOCK_SQL).label("valorizado_venta"),
    ], orden=[valorizado_costo.desc(), grupo])
    for fila in [*filas, totales]:
        fila["ganancia_potencial"] = Decimal(fila["valorizado_venta"] or 0) - Decimal(fila["valorizado_costo"] or 0)
        fila["margen_potencial"] = porcentaje(fila["ganancia_potencial"], fila["valorizado_venta"])
    for fila in filas:
        fila["grupo"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="stock-valorizado",
    nombre="Stock valorizado",
    descripcion="Stock actual valorizado a costo y a precio de venta",
    filtros_admitidos=("agrupar", "nivel", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.CATEGORIA, Agrupar.PROVEEDOR),
)
```

- [ ] **Step 8: Registro `backend/app/reports/definiciones/__init__.py`**

```python
"""Registro único de reportes: clave → definición, en el orden del hub.
Agregar un reporte = escribir su módulo en esta carpeta y sumarlo acá (vive
acá y no en el motor porque las definiciones importan el motor)."""
from app.core.errores import NoEncontrado
from app.reports.definiciones import stock_valorizado

REPORTES = {d.clave: d for d in (
    stock_valorizado.DEFINICION,
)}


def obtener_reporte(clave: str):
    definicion = REPORTES.get(clave)
    if definicion is None:
        raise NoEncontrado("Reporte no encontrado")
    return definicion
```

- [ ] **Step 9: Plantilla PDF `backend/app/templates/reports/reporte.html`**

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
{# Plantilla ÚNICA de todos los reportes (motor.exportar_pdf): los valores
   llegan ya formateados y alineados; acá no hay lógica por reporte. #}
<style>
  @page {
    size: A4{% if apaisado %} landscape{% endif %};
    margin: 12mm;
    @bottom-right { content: "Página " counter(page) " de " counter(pages); font-size: 8pt; color: #555; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "DejaVu Sans", sans-serif; font-size: 9pt; color: #111; }
  .cabecera { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 5mm; }
  .marca img { max-height: 14mm; max-width: 50mm; }
  .marca span { font-size: 14pt; font-weight: bold; }
  .emitido { color: #555; font-size: 8pt; }
  h1 { font-size: 15pt; margin-bottom: 2mm; }
  .filtros { color: #444; margin-bottom: 5mm; }
  .filtros span { margin-right: 4mm; }
  table { width: 100%; border-collapse: collapse; }
  thead { display: table-header-group; }
  th, td { border: 0.3mm solid #ccc; padding: 1.2mm 1.8mm; text-align: left; }
  th { background: #f0f0f0; }
  .numero { text-align: right; white-space: nowrap; }
  tfoot td { font-weight: bold; background: #f7f7f7; }
  .vacio { text-align: center; color: #555; padding: 6mm; }
</style>
</head>
<body>
  <div class="cabecera">
    <div class="marca">{% if logo %}<img src="{{ logo }}" alt="{{ APP_NAME }}">{% else %}<span>{{ APP_NAME }}</span>{% endif %}</div>
    <div class="emitido">Emitido el {{ emitido }}</div>
  </div>
  <h1>{{ titulo }}</h1>
  {% if filtros %}
  <div class="filtros">{% for etiqueta, valor in filtros %}<span><strong>{{ etiqueta }}:</strong> {{ valor }}</span>{% endfor %}</div>
  {% endif %}
  <table>
    <thead>
      <tr>{% for c in columnas %}<th class="{{ alineaciones[loop.index0] }}">{{ c.titulo }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
      {% for fila in filas %}
      <tr>{% for valor in fila %}<td class="{{ alineaciones[loop.index0] }}">{{ valor }}</td>{% endfor %}</tr>
      {% else %}
      <tr><td class="vacio" colspan="{{ columnas|length }}">No hay datos para los filtros elegidos.</td></tr>
      {% endfor %}
    </tbody>
    {% if filas %}
    <tfoot>
      <tr>{% for valor in totales %}<td class="{{ alineaciones[loop.index0] }}">{{ valor }}</td>{% endfor %}</tr>
    </tfoot>
    {% endif %}
  </table>
</body>
</html>
```

- [ ] **Step 10: Service `backend/app/services/reportes.py`**

```python
"""Reportes (sesión 09): solo lectura. Consultar no audita; exportar a Excel
o PDF sí (`reporte.exportar`, en la transacción que confirma el router)."""
from dataclasses import asdict

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria
from app.core.utils import ahora
from app.models import Categoria, EstadoVenta, MedioDePago, Proveedor, Usuario, Venta
from app.reports import motor
from app.reports.definiciones import REPORTES, obtener_reporte
from app.schemas.ventas import Referencia
from app.services.categorias import caminos

# formato → (extensión, exportador)
FORMATOS = {"excel": ("xlsx", motor.exportar_excel), "pdf": ("pdf", motor.exportar_pdf)}


def catalogo() -> list[dict]:
    return [{"clave": d.clave, "nombre": d.nombre, "descripcion": d.descripcion,
             "filtros_admitidos": list(d.filtros_admitidos), "agrupaciones": list(d.agrupaciones)}
            for d in REPORTES.values()]


def consultar(db, clave: str, filtros) -> dict:
    resultado = motor.generar(db, obtener_reporte(clave), filtros)
    return {**resultado, "columnas": [asdict(c) for c in resultado["columnas"]]}


def _sufijo(filtros) -> str:
    if filtros.desde:
        return f"{filtros.desde.isoformat()}_{filtros.hasta.isoformat()}"
    return ahora().date().isoformat()   # stock valorizado: foto de hoy


def exportar(db, autor, clave: str, filtros, formato: str, ip: str | None) -> tuple[bytes, str]:
    """(contenido, nombre de archivo). Genera primero y audita después: si la
    generación falla no queda registro; si falla el registro, no hay archivo."""
    resultado = motor.generar(db, obtener_reporte(clave), filtros)
    extension, exportador = FORMATOS[formato]
    contenido = exportador(db, resultado)
    aplicados = resultado["filtros"]
    registrar_auditoria(
        db, accion="reporte.exportar", entidad="reporte", usuario_id=autor.id, ip_origen=ip,
        estado_nuevo={"clave": clave, "formato": formato,
                      "filtros": aplicados.model_dump(mode="json", exclude_none=True)},
    )
    return contenido, f"reporte-{clave}-{_sufijo(aplicados)}.{extension}"


def opciones(db) -> dict:
    """Catálogos de los filtros. Vendedores: quienes tienen alguna venta
    confirmada o anulada (aunque hoy estén inactivos); medios: todos."""
    rutas = caminos(db)
    categorias = sorted(
        ({"id": id_, "nombre": rutas[id_], "nivel": nivel}
         for id_, nivel in db.execute(select(Categoria.id, Categoria.nivel))),
        key=lambda c: c["nombre"].lower(),
    )
    vendieron = select(Venta.usuario_id).where(Venta.estado != EstadoVenta.EN_CURSO)
    vendedores = db.scalars(select(Usuario).where(Usuario.id.in_(vendieron)).order_by(func.lower(Usuario.nombre)))
    return {
        "proveedores": [Referencia.de(p) for p in db.scalars(select(Proveedor).order_by(func.lower(Proveedor.nombre)))],
        "categorias": categorias,
        "vendedores": [Referencia.de(u) for u in vendedores],
        "medios_de_pago": [Referencia.de(m) for m in db.scalars(select(MedioDePago).order_by(func.lower(MedioDePago.nombre)))],
    }
```

- [ ] **Step 11: Router `backend/app/api/v1/reportes.py` y registro**

```python
"""Reportes (sesión 09): catálogo, opciones de filtros y cada reporte en
JSON, Excel y PDF con los mismos query params. Todo pide REPORTES ver.
Rutas fijas ("" y /opciones) declaradas ANTES de /{clave}."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TIPO_XLSX
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.reportes import FiltrosReporte, OpcionesReportes, ReporteCatalogo, ReporteResponse
from app.services import reportes as servicio

router = APIRouter(prefix="/reportes", tags=["reportes"])

puede_ver = requiere_permiso(Modulo.REPORTES, "ver")
Filtros = Annotated[FiltrosReporte, Query()]


@router.get("", response_model=list[ReporteCatalogo])
def catalogo(_: Usuario = Depends(puede_ver)):
    return servicio.catalogo()


@router.get("/opciones", response_model=OpcionesReportes)
def opciones(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.opciones(db)


@router.get("/{clave}", response_model=ReporteResponse)
def reporte(clave: str, filtros: Filtros, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.consultar(db, clave, filtros)


def _exportar(db, autor, request, clave, filtros, formato, media_type, disposicion) -> Response:
    contenido, nombre = servicio.exportar(db, autor, clave, filtros, formato, ip_de_request(request))
    db.commit()
    return Response(content=contenido, media_type=media_type,
                    headers={"Content-Disposition": f'{disposicion}; filename="{nombre}"'})


@router.get(
    "/{clave}/excel",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}}}},
)
def excel(clave: str, filtros: Filtros, request: Request, db: Session = Depends(get_db),
          autor: Usuario = Depends(puede_ver)):
    return _exportar(db, autor, request, clave, filtros, "excel", TIPO_XLSX, "attachment")


@router.get(
    "/{clave}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def pdf(clave: str, filtros: Filtros, request: Request, db: Session = Depends(get_db),
        autor: Usuario = Depends(puede_ver)):
    return _exportar(db, autor, request, clave, filtros, "pdf", "application/pdf", "inline")
```

En `backend/app/api/v1/__init__.py`: sumar `reportes` al import (orden alfabético dentro del paréntesis) y al final `api_router.include_router(reportes.router)`.

- [ ] **Step 12: Tests `backend/tests/test_reportes.py`**

```python
"""Reportes (sesión 09), Task 1: motor (filtros, rango, 404/422/403),
exportación a Excel y PDF con auditoría, opciones de filtros y el reporte de
stock valorizado. Los reportes de ventas: test_reportes_ventas.py."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.errores import NoProcesable, ReglaDeNegocio
from app.core.excel import TIPO_XLSX
from app.models import Auditoria
from app.reports.definiciones._comunes import porcentaje
from app.reports.motor import DefinicionReporte, normalizar_filtros
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.schemas.reportes import FiltrosReporte
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

API = "/api/v1/reportes"


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


@pytest.fixture
def h(headers_de, admin):
    return headers_de(admin)


@pytest.fixture
def stock(db, admin):
    """Árbol R > S > T, R > U y W; un proveedor en pesos y otro en dólares
    (dólar 1000). Solo cuentan los productos en T (3 u.), U (2 u.) y W (5 u.):
    el resto cae por inactivo, sin stock o con stock infinito."""
    def categoria(nombre, padre=None):
        return servicio_categorias.crear_categoria(
            db, admin, CategoriaCrear(nombre=nombre, parent_id=padre.id if padre else None), None)

    r = categoria("Rep R")
    s = categoria("Rep S", r)
    t = categoria("Rep T", s)
    u = categoria("Rep U", r)
    w = categoria("Rep W")
    ars = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Rep pesos", moneda="ars"), None)
    usd = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre="Rep dolares", moneda="usd", dolar_actual="1000"), None)

    def alta(descripcion, cat, proveedor, costo, stock_inicial=0, **extra):
        return servicio_productos.crear_producto(db, admin, ProductoCrear(
            descripcion=descripcion, categoria_id=cat.id, proveedor_id=proveedor.id, costo=costo, margen="50",
            stock_inicial=stock_inicial, **extra), None)

    productos = {"t": alta("Rep en T", t, ars, "1000", 3), "u": alta("Rep en U", u, usd, "2.50", 2),
                 "w": alta("Rep en W", w, ars, "400", 5)}
    alta("Rep inactivo", w, ars, "100", 4).activo = False
    alta("Rep sin stock", w, ars, "100")
    # Solo test: un producto de stock infinito con stock cargado no debe valorizarse.
    alta("Rep infinito", w, ars, "100", stock_infinito=True).stock = 7
    db.flush()
    return {"categorias": {"r": r, "s": s, "t": t, "u": u, "w": w}, "ars": ars, "usd": usd, "productos": productos}


def _pedir(client, h, clave, **params):
    r = client.get(f"{API}/{clave}", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _exportaciones(db) -> int:
    return db.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.accion == "reporte.exportar"))


# --- Catálogo, permisos y validación ------------------------------------------

def test_catalogo_lista_los_reportes_con_sus_filtros(client, h):
    r = client.get(API, headers=h)
    assert r.status_code == 200
    stock = next(x for x in r.json() if x["clave"] == "stock-valorizado")
    assert stock["agrupaciones"] == ["categoria", "proveedor"]
    assert "desde" not in stock["filtros_admitidos"] and "proveedor_id" in stock["filtros_admitidos"]


@pytest.mark.parametrize("ruta", ["", "/opciones", "/stock-valorizado", "/stock-valorizado/excel",
                                  "/stock-valorizado/pdf"])
def test_vendedor_sin_reportes_ver_403(client, headers_de, crear_usuario, ruta):
    assert client.get(f"{API}{ruta}", headers=headers_de(crear_usuario("vendedor"))).status_code == 403


def test_supervisor_ve_reportes(client, headers_de, crear_usuario):
    assert client.get(f"{API}/stock-valorizado", headers=headers_de(crear_usuario("supervisor"))).status_code == 200


@pytest.mark.parametrize("sufijo", ["", "/excel", "/pdf"])
def test_clave_inexistente_404(client, h, sufijo):
    assert client.get(f"{API}/no-existe{sufijo}", headers=h).status_code == 404


@pytest.mark.parametrize("params", [
    {"desde": "2026-01-01"},               # stock valorizado no usa fechas
    {"usuario_id": 1},                     # ni vendedor
    {"agrupar": "dia"},                    # agrupación que no admite
    {"agrupar": "proveedor", "nivel": 2},  # nivel sin agrupar por categoría
    {"nivel": 6},                          # fuera de 1-5
    {"proveedor_id": 2**63},               # mayor que BIGINT
    {"inventado": "x"},                    # parámetro desconocido
])
def test_filtro_no_admitido_422(client, h, params):
    assert client.get(f"{API}/stock-valorizado", params=params, headers=h).status_code == 422


_CON_FECHAS = DefinicionReporte(clave="prueba", nombre="Prueba", descripcion="", filtros_admitidos=("desde", "hasta"),
                                columnas=lambda f: [], consulta=lambda db, f: ([], {}))


def test_fechas_por_defecto_del_primero_del_mes_a_hoy():
    f = normalizar_filtros(_CON_FECHAS, FiltrosReporte(), hoy=date(2026, 9, 29))
    assert (f.desde, f.hasta) == (date(2026, 9, 1), date(2026, 9, 29))


def test_rango_de_366_dias_se_acepta_y_de_367_da_409():
    normalizar_filtros(_CON_FECHAS, FiltrosReporte(desde=date(2024, 1, 1), hasta=date(2024, 12, 31)))  # bisiesto
    with pytest.raises(ReglaDeNegocio, match="366 días"):
        normalizar_filtros(_CON_FECHAS, FiltrosReporte(desde=date(2024, 1, 1), hasta=date(2025, 1, 1)))


def test_desde_posterior_a_hasta_422():
    with pytest.raises(NoProcesable):
        normalizar_filtros(_CON_FECHAS, FiltrosReporte(desde=date(2026, 9, 2), hasta=date(2026, 9, 1)))


# --- Stock valorizado ---------------------------------------------------------

def test_por_defecto_agrupa_por_categoria_de_nivel_1(client, h, stock):
    datos = _pedir(client, h, "stock-valorizado")
    assert datos["filtros"]["agrupar"] == "categoria" and datos["filtros"]["nivel"] == 1
    assert datos["columnas"][0] == {"clave": "grupo", "titulo": "Categoría", "tipo": "texto"}
    assert {f["grupo"]: f["unidades"] for f in datos["filas"]} == {"Rep R": 5, "Rep W": 5}


def test_por_proveedor_valoriza_a_costo_en_pesos_y_a_venta(client, h, stock):
    t, u, w = (stock["productos"][k] for k in "tuw")
    filas = {f["grupo"]: f for f in _pedir(client, h, "stock-valorizado", agrupar="proveedor")["filas"]}
    assert set(filas) == {"Rep pesos", "Rep dolares"}
    pesos = filas["Rep pesos"]
    assert pesos["productos"] == 2 and pesos["unidades"] == 8
    assert Decimal(pesos["valorizado_costo"]) == t.costo_en_pesos * 3 + w.costo_en_pesos * 5
    assert Decimal(pesos["valorizado_venta"]) == t.precio_venta * 3 + w.precio_venta * 5
    dolares = filas["Rep dolares"]
    assert dolares["valorizado_costo"] == "5000.00"                  # 2,50 × 1000 × 2
    assert Decimal(dolares["valorizado_venta"]) == u.precio_venta * 2
    assert Decimal(dolares["ganancia_potencial"]) == Decimal(dolares["valorizado_venta"]) - Decimal("5000.00")


def test_por_categoria_lleva_cada_producto_a_su_ancestro_del_nivel(client, h, stock):
    def por_nivel(nivel):
        filas = _pedir(client, h, "stock-valorizado", agrupar="categoria", nivel=nivel)["filas"]
        return {f["grupo"]: f["unidades"] for f in filas}

    assert por_nivel(2) == {"Rep R > Rep S": 3, "Rep R > Rep U": 2, "Rep W": 5}
    # Las ramas más cortas que el nivel pedido quedan en su propia categoría.
    assert por_nivel(3) == {"Rep R > Rep S > Rep T": 3, "Rep R > Rep U": 2, "Rep W": 5}


def test_filtra_por_rama_y_por_proveedor(client, h, stock):
    rama = _pedir(client, h, "stock-valorizado", agrupar="proveedor", categoria_id=stock["categorias"]["r"].id)
    assert {f["grupo"]: f["unidades"] for f in rama["filas"]} == {"Rep pesos": 3, "Rep dolares": 2}
    proveedor = _pedir(client, h, "stock-valorizado", agrupar="proveedor", proveedor_id=stock["usd"].id)
    assert [f["grupo"] for f in proveedor["filas"]] == ["Rep dolares"]


def test_totales_calculados_sobre_totales(client, h, stock):
    datos = _pedir(client, h, "stock-valorizado", agrupar="proveedor")
    totales = datos["totales"]
    assert totales["grupo"] is None and totales["productos"] == 3 and totales["unidades"] == 10
    assert Decimal(totales["valorizado_costo"]) == sum(Decimal(f["valorizado_costo"]) for f in datos["filas"])
    ganancia = Decimal(totales["valorizado_venta"]) - Decimal(totales["valorizado_costo"])
    assert Decimal(totales["margen_potencial"]) == porcentaje(ganancia, Decimal(totales["valorizado_venta"]))


# --- Exportaciones y auditoría ------------------------------------------------

def test_consultar_en_pantalla_no_audita(client, h, db, stock):
    _pedir(client, h, "stock-valorizado")
    assert _exportaciones(db) == 0


def test_excel_con_los_mismos_totales_que_el_json_y_auditado(client, h, db, stock, admin):
    datos = _pedir(client, h, "stock-valorizado", agrupar="proveedor")
    r = client.get(f"{API}/stock-valorizado/excel", params={"agrupar": "proveedor"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith(TIPO_XLSX)
    assert 'attachment; filename="reporte-stock-valorizado-' in r.headers["content-disposition"]
    hoja = load_workbook(BytesIO(r.content)).active
    ultima = [c.value for c in hoja[hoja.max_row]]
    assert ultima[0] == "Total"
    for indice, columna in enumerate(datos["columnas"][1:], start=1):
        assert Decimal(str(ultima[indice])) == Decimal(str(datos["totales"][columna["clave"]]))
    registro = db.scalars(select(Auditoria).where(Auditoria.accion == "reporte.exportar")).one()
    assert registro.usuario_id == admin.id and registro.entidad == "reporte" and registro.entidad_id is None
    assert registro.estado_nuevo == {"clave": "stock-valorizado", "formato": "excel", "filtros": {"agrupar": "proveedor"}}


def test_pdf_inline_y_auditado(client, h, db, stock):
    r = client.get(f"{API}/stock-valorizado/pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith('inline; filename="reporte-stock-valorizado-')
    registro = db.scalars(select(Auditoria).where(Auditoria.accion == "reporte.exportar")).one()
    assert registro.estado_nuevo["formato"] == "pdf"
    assert registro.estado_nuevo["filtros"] == {"agrupar": "categoria", "nivel": 1}


def test_pdf_sin_datos_se_genera_igual(client, h):
    r = client.get(f"{API}/stock-valorizado/pdf", params={"proveedor_id": 2**62}, headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


# --- Opciones -----------------------------------------------------------------

def test_opciones_devuelve_los_catalogos_de_los_filtros(client, h, stock):
    r = client.get(f"{API}/opciones", headers=h)
    assert r.status_code == 200
    datos = r.json()
    assert set(datos) == {"proveedores", "categorias", "vendedores", "medios_de_pago"}
    assert {"id": stock["usd"].id, "nombre": "Rep dolares"} in datos["proveedores"]
    assert {"id": stock["categorias"]["t"].id, "nombre": "Rep R > Rep S > Rep T", "nivel": 3} in datos["categorias"]
```

- [ ] **Step 13: Correr, corregir y commitear**

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_reportes.py tests/test_excel.py -q`
Expected: PASS. Luego la suite completa: `docker compose exec -T backend pytest -p no:warnings -q` → PASS.

Si `test_filtro_no_admitido_422` con `{"inventado": "x"}` da 200, FastAPI no está aplicando `extra="forbid"` al modelo de query: verificar que `Filtros = Annotated[FiltrosReporte, Query()]` se use tal cual (no `Depends()`).

```bash
git add backend/app/core/errores.py backend/app/core/etiquetas.py backend/app/core/excel.py backend/app/services/stock.py \
  backend/app/schemas/reportes.py backend/app/reports/motor.py backend/app/reports/definiciones \
  backend/app/templates/reports/reporte.html backend/app/services/reportes.py backend/app/api/v1/reportes.py \
  backend/app/api/v1/__init__.py backend/tests/test_excel.py backend/tests/test_reportes.py
git commit -m "feat(reportes): motor de reportes, exportación a Excel y PDF y stock valorizado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Los cinco reportes de ventas

**Revisión:** CON revisor (dinero: rentabilidad, costo congelado, recargos, anuladas).

**Files:**
- Create: `backend/app/reports/definiciones/ventas_periodo.py`, `medios_pago.py`, `vendedores.py`, `productos_vendidos.py`, `rentabilidad.py`
- Modify: `backend/app/reports/definiciones/__init__.py`
- Test: `backend/tests/test_reportes_ventas.py`

**Interfaces:**
- Consumes (Task 1): `Columna`, `DefinicionReporte`, `titulo_de_agrupacion` (motor); `ventas_confirmadas`, `unidades_por_venta`, `periodo`, `condiciones_de_producto`, `grupo_de_producto`, `filas_y_totales`, `dividir`, `porcentaje` (`_comunes`); `Agrupar`, `Orden`, `TipoColumna` (schemas); `rango_fechas` (`core/utils.py`).
- Produces: cinco `DEFINICION` más en `REPORTES`, en el orden del hub: ventas-periodo, medios-pago, vendedores, productos-vendidos, rentabilidad, stock-valorizado.

**Datos del test (todo en hora del negocio; rango `2025-03-01`..`2025-04-30`):**

| Venta | Vendedor | Fecha | Ítems (producto: lista → final, costo) | Pagos |
|---|---|---|---|---|
| V1 | Ana | conf. 03/03 10:00 | A: 2000→2000, A: 2000→1800, A: 2000→2000 (costo 1000 c/u); D: 20000→20000 (costo 10000) | Contado 25800 |
| V2 | Beto | conf. 03/03 18:00 | B: 1000→1000 (costo 500) | Tarjeta plan 3 cuotas +10 %, costo_medio 5 %: 1000 + recargo 100 |
| V3 | Ana | conf. 20/03 | D: 20000→19000 (costo 10000) | Contado 10000 + Tarjeta sin plan 9000 |
| V4 | Beto | conf. 05/03, **anulada 02/04** | A: 2000→2000 | Contado 2000 |
| V5 | Ana | **en curso** | B | — |
| V6 | Ana | conf. **27/02** (fuera del rango) | B | Contado 1000 |

Productos: A en R > S > T (proveedor en pesos), D en R > U (proveedor en dólares, dólar 1000, costo 10), B en W (pesos).

- [ ] **Step 1: Tests `backend/tests/test_reportes_ventas.py`**

```python
"""Reportes de ventas (sesión 09, Task 2). Las ventas se arman a mano (sin
services.ventas) para controlar fechas e importes y verificar cada número.
Ver la tabla de datos en el plan del módulo 09 (Task 2)."""
import itertools
from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import EstadoVenta, MedioDePago, PlanCuotas, Venta, VentaItem, VentaPago
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

API = "/api/v1/reportes"
RANGO = {"desde": "2025-03-01", "hasta": "2025-04-30"}
D = Decimal
_numeros = itertools.count(1)


def _venta(db, usuario, items, pagos, *, confirmada_en=None, anulada=None, en_curso=False):
    """`items` = [(producto, precio_lista, precio_final, costo_unitario)];
    `pagos` = [(medio, plan o None, monto)] (el recargo sale del plan);
    `anulada` = (fecha de anulación, usuario que anula)."""
    n = next(_numeros)
    cobros = []
    for medio, plan, monto in pagos:
        recargo = (D(monto) * plan.recargo_cliente / 100).quantize(D("0.01")) if plan else D("0")
        cobros.append((medio, plan, D(monto), recargo))
    subtotal = sum((D(i[1]) for i in items), D("0"))
    cobrable = sum((D(i[2]) for i in items), D("0"))
    recargo_total = sum((c[3] for c in cobros), D("0"))
    venta = Venta(numero=f"RT-{n:06d}", usuario_id=usuario.id, subtotal=subtotal, descuento_total=subtotal - cobrable,
                  recargo_total=recargo_total, total=cobrable + recargo_total,
                  estado=EstadoVenta.EN_CURSO if en_curso else EstadoVenta.CONFIRMADA)
    if not en_curso:
        venta.codigo_cambio = f"RT{n:06d}"
        venta.confirmada_en = confirmada_en
    if anulada:
        venta.estado = EstadoVenta.ANULADA
        venta.anulada_en, quien = anulada
        venta.anulada_por_id = quien.id
        venta.motivo_anulacion = "Prueba de reportes"
    db.add(venta)
    db.flush()
    for orden, (producto, lista, final, costo) in enumerate(items):
        db.add(VentaItem(venta_id=venta.id, producto_id=producto.id, precio_lista=D(lista), precio_unitario=D(lista),
                         precio_final=D(final), costo_unitario=D(costo), en_promocion=D(final) < D(lista), orden=orden))
    for medio, plan, monto, recargo in cobros:
        db.add(VentaPago(venta_id=venta.id, medio_de_pago_id=medio.id, plan_cuotas_id=plan.id if plan else None,
                         monto=monto, recargo=recargo, monto_total=monto + recargo))
    db.flush()
    return venta


@pytest.fixture
def e(db, crear_usuario):
    admin = crear_usuario("admin")
    ana = crear_usuario("vendedor", nombre="Ana Rep")
    beto = crear_usuario("vendedor", nombre="Beto Rep")

    def categoria(nombre, padre=None):
        return servicio_categorias.crear_categoria(
            db, admin, CategoriaCrear(nombre=nombre, parent_id=padre.id if padre else None), None)

    r = categoria("Rep R")
    s = categoria("Rep S", r)
    t = categoria("Rep T", s)
    u = categoria("Rep U", r)
    w = categoria("Rep W")
    ars = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Rep pesos", moneda="ars"), None)
    usd = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre="Rep dolares", moneda="usd", dolar_actual="1000"), None)

    def alta(descripcion, cat, proveedor, costo):
        return servicio_productos.crear_producto(db, admin, ProductoCrear(
            descripcion=descripcion, categoria_id=cat.id, proveedor_id=proveedor.id, costo=costo, margen="0"), None)

    pa, pb, pd = alta("Rep A", t, ars, "1000"), alta("Rep B", w, ars, "500"), alta("Rep D", u, usd, "10")
    contado = MedioDePago(nombre="Contado Rep")
    tarjeta = MedioDePago(nombre="Tarjeta Rep", soporta_cuotas=True)
    db.add_all([contado, tarjeta])
    db.flush()
    plan = PlanCuotas(medio_de_pago_id=tarjeta.id, cuotas=3, recargo_cliente=D("10"), costo_medio=D("5"))
    db.add(plan)
    db.flush()

    a = (pa, "2000", "2000", "1000")
    _venta(db, ana, [a, (pa, "2000", "1800", "1000"), a, (pd, "20000", "20000", "10000")],
           [(contado, None, "25800")], confirmada_en=datetime(2025, 3, 3, 10))
    _venta(db, beto, [(pb, "1000", "1000", "500")], [(tarjeta, plan, "1000")], confirmada_en=datetime(2025, 3, 3, 18))
    _venta(db, ana, [(pd, "20000", "19000", "10000")], [(contado, None, "10000"), (tarjeta, None, "9000")],
           confirmada_en=datetime(2025, 3, 20, 12))
    _venta(db, beto, [a], [(contado, None, "2000")], confirmada_en=datetime(2025, 3, 5, 12),
           anulada=(datetime(2025, 4, 2, 11), admin))
    _venta(db, ana, [(pb, "1000", "1000", "500")], [], en_curso=True)
    _venta(db, ana, [(pb, "1000", "1000", "500")], [(contado, None, "1000")], confirmada_en=datetime(2025, 2, 27, 12))
    return {"admin": admin, "ana": ana, "beto": beto, "cat": {"r": r, "w": w}, "ars": ars, "usd": usd,
            "pa": pa, "pb": pb, "pd": pd, "contado": contado, "tarjeta": tarjeta}


@pytest.fixture
def h(headers_de, e):
    return headers_de(e["admin"])


def _pedir(client, h, clave, **params):
    r = client.get(f"{API}/{clave}", params={**RANGO, **params}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _sin(fila, *claves):
    return {k: v for k, v in fila.items() if k not in claves}


# --- Ventas por período -------------------------------------------------------

def test_ventas_por_dia_con_anuladas_por_fecha_de_anulacion(client, h, e):
    datos = _pedir(client, h, "ventas-periodo")
    assert [c["tipo"] for c in datos["columnas"][:1]] == ["fecha"]
    assert datos["filas"] == [
        {"periodo": "2025-03-03", "ventas": 2, "unidades": 5, "subtotal": "27000.00", "descuentos": "200.00",
         "recargos": "100.00", "total": "26900.00", "ticket_promedio": "13450.00", "anuladas": 0,
         "anuladas_monto": "0.00"},
        {"periodo": "2025-03-20", "ventas": 1, "unidades": 1, "subtotal": "20000.00", "descuentos": "1000.00",
         "recargos": "0.00", "total": "19000.00", "ticket_promedio": "19000.00", "anuladas": 0,
         "anuladas_monto": "0.00"},
        {"periodo": "2025-04-02", "ventas": 0, "unidades": 0, "subtotal": "0.00", "descuentos": "0.00",
         "recargos": "0.00", "total": "0.00", "ticket_promedio": "0.00", "anuladas": 1, "anuladas_monto": "2000.00"},
    ]
    assert datos["totales"] == {
        "periodo": None, "ventas": 3, "unidades": 6, "subtotal": "47000.00", "descuentos": "1200.00",
        "recargos": "100.00", "total": "45900.00", "ticket_promedio": "15300.00", "anuladas": 1,
        "anuladas_monto": "2000.00"}


def test_ventas_por_mes(client, h, e):
    datos = _pedir(client, h, "ventas-periodo", agrupar="mes")
    assert datos["columnas"][0]["tipo"] == "mes"
    assert [(f["periodo"], f["ventas"], f["total"], f["anuladas"]) for f in datos["filas"]] == [
        ("2025-03-01", 3, "45900.00", 0), ("2025-04-01", 0, "0.00", 1)]


def test_ventas_periodo_no_admite_proveedor_ni_categoria(client, h, e):
    for params in ({"proveedor_id": e["ars"].id}, {"categoria_id": e["cat"]["r"].id}):
        assert client.get(f"{API}/ventas-periodo", params={**RANGO, **params}, headers=h).status_code == 422


def test_rango_de_mas_de_366_dias_409(client, h, e):
    r = client.get(f"{API}/ventas-periodo", params={"desde": "2024-01-01", "hasta": "2025-01-01"}, headers=h)
    assert r.status_code == 409


# --- Medios de pago -----------------------------------------------------------

def test_medios_de_pago_con_plan_recargo_y_costo_del_medio(client, h, e):
    datos = _pedir(client, h, "medios-pago")
    assert datos["filas"] == [
        {"medio": "Contado Rep", "plan": "Un pago", "pagos": 2, "monto": "35800.00", "recargo": "0.00",
         "total_cobrado": "35800.00", "costo_medio": "0.00", "neto": "35800.00"},
        {"medio": "Tarjeta Rep", "plan": "Un pago", "pagos": 1, "monto": "9000.00", "recargo": "0.00",
         "total_cobrado": "9000.00", "costo_medio": "0.00", "neto": "9000.00"},
        {"medio": "Tarjeta Rep", "plan": "3 cuotas +10%", "pagos": 1, "monto": "1000.00", "recargo": "100.00",
         "total_cobrado": "1100.00", "costo_medio": "55.00", "neto": "1045.00"},   # 1100 × 5 %
    ]
    assert _sin(datos["totales"], "medio", "plan") == {
        "pagos": 4, "monto": "45800.00", "recargo": "100.00", "total_cobrado": "45900.00", "costo_medio": "55.00",
        "neto": "45845.00"}


def test_medios_de_pago_filtra_por_vendedor_y_por_medio(client, h, e):
    beto = _pedir(client, h, "medios-pago", usuario_id=e["beto"].id)["filas"]
    assert [(f["medio"], f["plan"]) for f in beto] == [("Tarjeta Rep", "3 cuotas +10%")]
    contado = _pedir(client, h, "medios-pago", medio_de_pago_id=e["contado"].id)["filas"]
    assert [f["medio"] for f in contado] == ["Contado Rep"]


# --- Vendedores ---------------------------------------------------------------

def test_vendedores(client, h, e):
    datos = _pedir(client, h, "vendedores")
    assert datos["filas"] == [
        {"vendedor": "Ana Rep", "ventas": 2, "unidades": 5, "total": "44800.00", "ticket_promedio": "22400.00",
         "descuentos": "1200.00"},
        {"vendedor": "Beto Rep", "ventas": 1, "unidades": 1, "total": "1100.00", "ticket_promedio": "1100.00",
         "descuentos": "0.00"},
    ]
    assert datos["totales"] == {"vendedor": None, "ventas": 3, "unidades": 6, "total": "45900.00",
                                "ticket_promedio": "15300.00", "descuentos": "1200.00"}


def test_vendedores_no_admite_medio(client, h, e):
    r = client.get(f"{API}/vendedores", params={**RANGO, "medio_de_pago_id": e["contado"].id}, headers=h)
    assert r.status_code == 422


# --- Productos más vendidos ---------------------------------------------------

def test_productos_por_unidades_y_por_importe(client, h, e):
    pa, pb, pd = e["pa"], e["pb"], e["pd"]
    por_unidades = _pedir(client, h, "productos-vendidos")
    assert [c["clave"] for c in por_unidades["columnas"]] == ["codigo", "descripcion", "unidades", "importe", "porcentaje"]
    assert por_unidades["filas"] == [
        {"codigo": pa.codigo_con_verificador, "descripcion": "Rep A", "unidades": 3, "importe": "5800.00",
         "porcentaje": "12.66"},
        {"codigo": pd.codigo_con_verificador, "descripcion": "Rep D", "unidades": 2, "importe": "39000.00",
         "porcentaje": "85.15"},
        {"codigo": pb.codigo_con_verificador, "descripcion": "Rep B", "unidades": 1, "importe": "1000.00",
         "porcentaje": "2.18"},
    ]
    assert por_unidades["totales"] == {"codigo": None, "descripcion": None, "unidades": 6, "importe": "45800.00",
                                       "porcentaje": "100.00"}
    por_importe = _pedir(client, h, "productos-vendidos", orden="importe")
    assert [f["descripcion"] for f in por_importe["filas"]] == ["Rep D", "Rep A", "Rep B"]


def test_productos_limite_no_achica_los_totales(client, h, e):
    datos = _pedir(client, h, "productos-vendidos", limite=1)
    assert [f["descripcion"] for f in datos["filas"]] == ["Rep A"]
    assert datos["totales"]["importe"] == "45800.00" and datos["totales"]["unidades"] == 6
    assert client.get(f"{API}/productos-vendidos", params={**RANGO, "limite": 501}, headers=h).status_code == 422


def test_productos_por_categoria_de_nivel(client, h, e):
    nivel_1 = _pedir(client, h, "productos-vendidos", agrupar="categoria")
    assert [c["clave"] for c in nivel_1["columnas"]] == ["categoria", "unidades", "importe", "porcentaje"]
    assert nivel_1["filas"] == [
        {"categoria": "Rep R", "unidades": 5, "importe": "44800.00", "porcentaje": "97.82"},
        {"categoria": "Rep W", "unidades": 1, "importe": "1000.00", "porcentaje": "2.18"},
    ]
    nivel_2 = _pedir(client, h, "productos-vendidos", agrupar="categoria", nivel=2)
    assert [(f["categoria"], f["unidades"]) for f in nivel_2["filas"]] == [
        ("Rep R > Rep S", 3), ("Rep R > Rep U", 2), ("Rep W", 1)]


def test_productos_filtra_por_proveedor_y_por_rama(client, h, e):
    pesos = _pedir(client, h, "productos-vendidos", proveedor_id=e["ars"].id)
    assert [(f["descripcion"], f["porcentaje"]) for f in pesos["filas"]] == [("Rep A", "85.29"), ("Rep B", "14.71")]
    rama = _pedir(client, h, "productos-vendidos", categoria_id=e["cat"]["r"].id)
    assert [f["descripcion"] for f in rama["filas"]] == ["Rep A", "Rep D"]


# --- Rentabilidad -------------------------------------------------------------

def test_rentabilidad_por_proveedor_sin_recargos(client, h, e):
    datos = _pedir(client, h, "rentabilidad", agrupar="proveedor")
    assert datos["filas"] == [
        {"grupo": "Rep dolares", "unidades": 2, "importe": "39000.00", "costo": "20000.00", "ganancia": "19000.00",
         "margen": "48.72"},
        {"grupo": "Rep pesos", "unidades": 4, "importe": "6800.00", "costo": "3500.00", "ganancia": "3300.00",
         "margen": "48.53"},
    ]
    # Importe = Σ precio_final (45800): el recargo de 100 de V2 no entra.
    assert datos["totales"] == {"grupo": None, "unidades": 6, "importe": "45800.00", "costo": "23500.00",
                                "ganancia": "22300.00", "margen": "48.69"}


def test_rentabilidad_por_dia_mes_y_categoria(client, h, e):
    por_dia = _pedir(client, h, "rentabilidad")
    assert datos_de(por_dia) == [("2025-03-03", 5, "26800.00", "13500.00", "49.63"),
                                 ("2025-03-20", 1, "19000.00", "10000.00", "47.37")]
    assert datos_de(_pedir(client, h, "rentabilidad", agrupar="mes")) == [
        ("2025-03-01", 6, "45800.00", "23500.00", "48.69")]
    assert datos_de(_pedir(client, h, "rentabilidad", agrupar="categoria")) == [
        ("Rep R", 5, "44800.00", "23000.00", "48.66"), ("Rep W", 1, "1000.00", "500.00", "50.00")]


def datos_de(respuesta):
    return [(f["grupo"], f["unidades"], f["importe"], f["costo"], f["margen"]) for f in respuesta["filas"]]


def test_rentabilidad_usa_el_costo_congelado(client, h, e, db):
    antes = _pedir(client, h, "rentabilidad", agrupar="proveedor")["totales"]
    e["usd"].dolar_actual = D("2000")
    e["pa"].costo = D("5000")
    db.flush()
    assert _pedir(client, h, "rentabilidad", agrupar="proveedor")["totales"] == antes


def test_rentabilidad_no_admite_agrupar_por_producto(client, h, e):
    assert client.get(f"{API}/rentabilidad", params={**RANGO, "agrupar": "producto"}, headers=h).status_code == 422


# --- Exportaciones y opciones -------------------------------------------------

@pytest.mark.parametrize("clave", ["ventas-periodo", "medios-pago", "vendedores", "productos-vendidos",
                                   "rentabilidad", "stock-valorizado"])
def test_excel_y_pdf_de_cada_reporte(client, h, e, clave):
    params = {} if clave == "stock-valorizado" else RANGO
    datos = client.get(f"{API}/{clave}", params=params, headers=h).json()
    r = client.get(f"{API}/{clave}/excel", params=params, headers=h)
    assert r.status_code == 200
    hoja = load_workbook(BytesIO(r.content)).active
    ultima = [c.value for c in hoja[hoja.max_row]]
    assert ultima[0] == "Total"
    for indice, columna in enumerate(datos["columnas"][1:], start=1):
        valor = datos["totales"][columna["clave"]]
        if valor is not None:
            assert Decimal(str(ultima[indice])) == Decimal(str(valor))
    pdf = client.get(f"{API}/{clave}/pdf", params=params, headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_nombre_del_excel_lleva_el_rango(client, h, e):
    r = client.get(f"{API}/ventas-periodo/excel", params=RANGO, headers=h)
    assert 'filename="reporte-ventas-periodo-2025-03-01_2025-04-30.xlsx"' in r.headers["content-disposition"]


def test_catalogo_en_el_orden_del_hub(client, h, e):
    assert [x["clave"] for x in client.get(API, headers=h).json()] == [
        "ventas-periodo", "medios-pago", "vendedores", "productos-vendidos", "rentabilidad", "stock-valorizado"]


def test_opciones_vendedores_que_vendieron_aunque_esten_inactivos(client, h, e, db, crear_usuario):
    crear_usuario("vendedor", nombre="Sin ventas Rep")
    e["beto"].activo = False
    e["tarjeta"].activo = False
    db.flush()
    datos = client.get(f"{API}/opciones", headers=h).json()
    nombres = [v["nombre"] for v in datos["vendedores"]]
    assert "Ana Rep" in nombres and "Beto Rep" in nombres and "Sin ventas Rep" not in nombres
    assert "Tarjeta Rep" in [m["nombre"] for m in datos["medios_de_pago"]]
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_reportes_ventas.py -q`
Expected: FAIL (404 en los reportes que todavía no existen).

- [ ] **Step 2: `backend/app/reports/definiciones/ventas_periodo.py`**

```python
"""Ventas por período: ventas confirmadas por día o mes de `confirmada_en`
y, aparte, las anuladas por el período en que se ANULARON (decisión del
módulo: coincide con el arqueo del turno que las descontó)."""
from sqlalchemy import func, select

from app.core.utils import rango_fechas
from app.models import EstadoVenta, Venta
from app.reports.definiciones._comunes import dividir, filas_y_totales, periodo, unidades_por_venta, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("periodo", "Período", T.MES if filtros.agrupar is Agrupar.MES else T.FECHA),
        Columna("ventas", "Ventas", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("subtotal", "Subtotal", T.MONEDA),
        Columna("descuentos", "Descuentos", T.MONEDA),
        Columna("recargos", "Recargos", T.MONEDA),
        Columna("total", "Total", T.MONEDA),
        Columna("ticket_promedio", "Ticket promedio", T.MONEDA),
        Columna("anuladas", "Anuladas (cant.)", T.ENTERO),
        Columna("anuladas_monto", "Anuladas ($)", T.MONEDA),
    ]


def _consulta(db, filtros):
    unidades = unidades_por_venta(filtros)

    def confirmadas(*columnas):
        return (select(*columnas).select_from(Venta)
                .outerjoin(unidades, unidades.c.venta_id == Venta.id)
                .where(*ventas_confirmadas(filtros)))

    filas, totales = filas_y_totales(db, confirmadas, [periodo(Venta.confirmada_en, filtros.agrupar).label("periodo")], [
        func.count(Venta.id).label("ventas"),
        func.sum(unidades.c.unidades).label("unidades"),
        func.sum(Venta.subtotal).label("subtotal"),
        func.sum(Venta.descuento_total).label("descuentos"),
        func.sum(Venta.recargo_total).label("recargos"),
        func.sum(Venta.total).label("total"),
    ])

    def anuladas(*columnas):
        return (select(*columnas).select_from(Venta)
                .where(Venta.estado == EstadoVenta.ANULADA,
                       *rango_fechas(Venta.anulada_en, filtros.desde, filtros.hasta)))

    filas_anuladas, totales_anuladas = filas_y_totales(
        db, anuladas, [periodo(Venta.anulada_en, filtros.agrupar).label("periodo")],
        [func.count(Venta.id).label("anuladas"), func.sum(Venta.total).label("anuladas_monto")])

    # Unión de los dos conjuntos YA agregados: un período puede tener solo ventas, solo anuladas o ambas.
    por_periodo = {fila["periodo"]: fila for fila in filas}
    for fila in filas_anuladas:
        por_periodo.setdefault(fila["periodo"], {"periodo": fila["periodo"]}).update(fila)
    filas = [por_periodo[p] for p in sorted(por_periodo)]
    totales.update(totales_anuladas)
    for fila in [*filas, totales]:
        fila["ticket_promedio"] = dividir(fila.get("total"), fila.get("ventas"))
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="ventas-periodo",
    nombre="Ventas por período",
    descripcion="Ventas, unidades, descuentos, recargos y anuladas por día o por mes",
    filtros_admitidos=("desde", "hasta", "agrupar"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.DIA, Agrupar.MES),
)
```

- [ ] **Step 3: `backend/app/reports/definiciones/medios_pago.py`**

```python
"""Ventas por medio de pago y plan de cuotas. El costo del medio es una
ESTIMACIÓN (total cobrado × costo_medio del plan); un pago sin plan tiene
costo 0 (decisión del módulo: costo_medio solo existe en los planes)."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import MedioDePago, PlanCuotas, Venta, VentaPago
from app.reports.definiciones._comunes import filas_y_totales, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte
from app.schemas.reportes import TipoColumna as T


def etiqueta_plan(cuotas: int | None, recargo) -> str:
    """"Un pago" (sin plan) o "N cuotas +X%" (el recargo solo si hay)."""
    if cuotas is None:
        return "Un pago"
    texto = "1 cuota" if cuotas == 1 else f"{cuotas} cuotas"
    if recargo:
        texto += f" +{format(Decimal(recargo).normalize(), 'f').replace('.', ',')}%"
    return texto


def _columnas(_filtros) -> list[Columna]:
    return [
        Columna("medio", "Medio", T.TEXTO),
        Columna("plan", "Plan", T.TEXTO),
        Columna("pagos", "Pagos", T.ENTERO),
        Columna("monto", "Monto", T.MONEDA),
        Columna("recargo", "Recargo", T.MONEDA),
        Columna("total_cobrado", "Total cobrado", T.MONEDA),
        Columna("costo_medio", "Costo del medio (estimado)", T.MONEDA),
        Columna("neto", "Neto", T.MONEDA),
    ]


def _consulta(db, filtros):
    condiciones = ventas_confirmadas(filtros)
    if filtros.medio_de_pago_id:
        condiciones.append(VentaPago.medio_de_pago_id == filtros.medio_de_pago_id)
    if filtros.usuario_id:
        condiciones.append(Venta.usuario_id == filtros.usuario_id)

    def consulta(*columnas):
        return (select(*columnas).select_from(VentaPago)
                .join(Venta, Venta.id == VentaPago.venta_id)
                .join(MedioDePago, MedioDePago.id == VentaPago.medio_de_pago_id)
                .outerjoin(PlanCuotas, PlanCuotas.id == VentaPago.plan_cuotas_id)
                .where(*condiciones))

    costo = func.round(VentaPago.monto_total * func.coalesce(PlanCuotas.costo_medio, 0) / 100, 2)
    filas, totales = filas_y_totales(
        db, consulta,
        [MedioDePago.id.label("medio_id"), MedioDePago.nombre.label("medio"), PlanCuotas.id.label("plan_id"),
         PlanCuotas.cuotas.label("cuotas"), PlanCuotas.recargo_cliente.label("recargo_plan")],
        [func.count(VentaPago.id).label("pagos"), func.sum(VentaPago.monto).label("monto"),
         func.sum(VentaPago.recargo).label("recargo"), func.sum(VentaPago.monto_total).label("total_cobrado"),
         func.sum(costo).label("costo_medio")],
        orden=[func.lower(MedioDePago.nombre), MedioDePago.id, PlanCuotas.cuotas.asc().nulls_first(),
               PlanCuotas.recargo_cliente, PlanCuotas.id],
    )
    for fila in [*filas, totales]:
        fila["neto"] = Decimal(fila["total_cobrado"] or 0) - Decimal(fila["costo_medio"] or 0)
    for fila in filas:
        fila["plan"] = etiqueta_plan(fila["cuotas"], fila["recargo_plan"])
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="medios-pago",
    nombre="Ventas por medio de pago",
    descripcion="Cobros por medio y plan de cuotas, con recargos y costo estimado del medio",
    filtros_admitidos=("desde", "hasta", "medio_de_pago_id", "usuario_id"),
    columnas=_columnas,
    consulta=_consulta,
)
```

- [ ] **Step 4: `backend/app/reports/definiciones/vendedores.py`**

```python
"""Ventas por vendedor (quien cargó y confirmó la venta)."""
from sqlalchemy import func, select

from app.models import Usuario, Venta
from app.reports.definiciones._comunes import dividir, filas_y_totales, unidades_por_venta, ventas_confirmadas
from app.reports.motor import Columna, DefinicionReporte
from app.schemas.reportes import TipoColumna as T


def _columnas(_filtros) -> list[Columna]:
    return [
        Columna("vendedor", "Vendedor", T.TEXTO),
        Columna("ventas", "Ventas", T.ENTERO),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("total", "Total", T.MONEDA),
        Columna("ticket_promedio", "Ticket promedio", T.MONEDA),
        Columna("descuentos", "Descuentos otorgados", T.MONEDA),
    ]


def _consulta(db, filtros):
    unidades = unidades_por_venta(filtros)
    condiciones = ventas_confirmadas(filtros)
    if filtros.usuario_id:
        condiciones.append(Venta.usuario_id == filtros.usuario_id)

    def consulta(*columnas):
        return (select(*columnas).select_from(Venta)
                .join(Usuario, Usuario.id == Venta.usuario_id)
                .outerjoin(unidades, unidades.c.venta_id == Venta.id)
                .where(*condiciones))

    total = func.sum(Venta.total).label("total")
    filas, totales = filas_y_totales(
        db, consulta, [Usuario.id.label("usuario_id"), Usuario.nombre.label("vendedor")],
        [func.count(Venta.id).label("ventas"), func.sum(unidades.c.unidades).label("unidades"), total,
         func.sum(Venta.descuento_total).label("descuentos")],
        orden=[total.desc(), func.lower(Usuario.nombre), Usuario.id],
    )
    for fila in [*filas, totales]:
        fila["ticket_promedio"] = dividir(fila["total"], fila["ventas"])
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="vendedores",
    nombre="Ventas por vendedor",
    descripcion="Ventas, unidades, ticket promedio y descuentos de cada vendedor",
    filtros_admitidos=("desde", "hasta", "usuario_id"),
    columnas=_columnas,
    consulta=_consulta,
)
```

- [ ] **Step 5: `backend/app/reports/definiciones/productos_vendidos.py`**

```python
"""Productos más vendidos, por producto o por categoría (al nivel pedido).
Importe = Σ precio_final (ya con descuentos y promociones). Los totales son
de TODO el conjunto filtrado, no solo de las `limite` filas mostradas."""
from sqlalchemy import func, select

from app.models import Producto, Venta, VentaItem
from app.reports.definiciones._comunes import (
    condiciones_de_producto, filas_y_totales, grupo_de_producto, porcentaje, ventas_confirmadas,
)
from app.reports.motor import Columna, DefinicionReporte
from app.schemas.reportes import Agrupar, Orden
from app.schemas.reportes import TipoColumna as T


def _columnas(filtros) -> list[Columna]:
    if filtros.agrupar is Agrupar.CATEGORIA:
        grupo = [Columna("categoria", "Categoría", T.TEXTO)]
    else:
        grupo = [Columna("codigo", "Código", T.TEXTO), Columna("descripcion", "Descripción", T.TEXTO)]
    return [*grupo, Columna("unidades", "Unidades", T.ENTERO), Columna("importe", "Importe vendido", T.MONEDA),
            Columna("porcentaje", "% del total", T.PORCENTAJE)]


def _consulta(db, filtros):
    condiciones = [*ventas_confirmadas(filtros), *condiciones_de_producto(db, filtros)]
    if filtros.agrupar is Agrupar.CATEGORIA:
        unir, grupo, etiquetas = grupo_de_producto(db, filtros)
        grupos = [grupo]
    else:
        unir, etiquetas = (lambda sentencia: sentencia), None
        grupos = [Producto.id.label("producto_id"), (Producto.sku + Producto.verificador).label("codigo"),
                  Producto.descripcion.label("descripcion")]

    def consulta(*columnas):
        sentencia = (select(*columnas).select_from(VentaItem)
                     .join(Venta, Venta.id == VentaItem.venta_id)
                     .join(Producto, Producto.id == VentaItem.producto_id))
        return unir(sentencia).where(*condiciones)

    unidades = func.count(VentaItem.id).label("unidades")
    importe = func.sum(VentaItem.precio_final).label("importe")
    principal, desempate = (unidades, importe) if filtros.orden is Orden.UNIDADES else (importe, unidades)
    filas, totales = filas_y_totales(db, consulta, grupos, [unidades, importe],
                                     orden=[principal.desc(), desempate.desc(), grupos[0]], limite=filtros.limite)
    for fila in [*filas, totales]:
        fila["porcentaje"] = porcentaje(fila["importe"], totales["importe"])
    if etiquetas is not None:
        for fila in filas:
            fila["categoria"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="productos-vendidos",
    nombre="Productos más vendidos",
    descripcion="Ranking por unidades o importe, por producto o por categoría",
    filtros_admitidos=("desde", "hasta", "agrupar", "nivel", "orden", "limite", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.PRODUCTO, Agrupar.CATEGORIA),
)
```

Nota: en el bucle de `porcentaje`, `totales` se procesa último, así que la fila de totales usa `totales["importe"]` antes de sumarle la clave `porcentaje` (no la pisa).

- [ ] **Step 6: `backend/app/reports/definiciones/rentabilidad.py`**

```python
"""Rentabilidad: importe vendido (Σ precio_final) menos costo CONGELADO de
cada unidad (venta_items.costo_unitario). Los recargos por cuotas son
financieros y no entran; cambiar después el costo o el dólar no la altera."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Producto, Venta, VentaItem
from app.reports.definiciones._comunes import (
    condiciones_de_producto, filas_y_totales, grupo_de_producto, periodo, porcentaje, ventas_confirmadas,
)
from app.reports.motor import Columna, DefinicionReporte, titulo_de_agrupacion
from app.schemas.reportes import Agrupar
from app.schemas.reportes import TipoColumna as T

TIPO_DEL_GRUPO = {Agrupar.DIA: T.FECHA, Agrupar.MES: T.MES}


def _columnas(filtros) -> list[Columna]:
    return [
        Columna("grupo", titulo_de_agrupacion(filtros.agrupar), TIPO_DEL_GRUPO.get(filtros.agrupar, T.TEXTO)),
        Columna("unidades", "Unidades", T.ENTERO),
        Columna("importe", "Importe vendido", T.MONEDA),
        Columna("costo", "Costo", T.MONEDA),
        Columna("ganancia", "Ganancia bruta", T.MONEDA),
        Columna("margen", "Margen %", T.PORCENTAJE),
    ]


def _consulta(db, filtros):
    condiciones = [*ventas_confirmadas(filtros), *condiciones_de_producto(db, filtros)]
    importe = func.sum(VentaItem.precio_final).label("importe")
    if filtros.agrupar in TIPO_DEL_GRUPO:
        unir, etiquetas = (lambda sentencia: sentencia), None
        grupo = periodo(Venta.confirmada_en, filtros.agrupar).label("grupo")
        orden = [grupo]
    else:
        unir, grupo, etiquetas = grupo_de_producto(db, filtros)
        orden = [importe.desc(), grupo]

    def consulta(*columnas):
        sentencia = (select(*columnas).select_from(VentaItem)
                     .join(Venta, Venta.id == VentaItem.venta_id)
                     .join(Producto, Producto.id == VentaItem.producto_id))
        return unir(sentencia).where(*condiciones)

    filas, totales = filas_y_totales(db, consulta, [grupo], [
        func.count(VentaItem.id).label("unidades"), importe, func.sum(VentaItem.costo_unitario).label("costo"),
    ], orden=orden)
    for fila in [*filas, totales]:
        fila["ganancia"] = Decimal(fila["importe"] or 0) - Decimal(fila["costo"] or 0)
        fila["margen"] = porcentaje(fila["ganancia"], fila["importe"])
    if etiquetas is not None:
        for fila in filas:
            fila["grupo"] = etiquetas.get(fila["grupo_id"], "")
    return filas, totales


DEFINICION = DefinicionReporte(
    clave="rentabilidad",
    nombre="Rentabilidad",
    descripcion="Importe vendido, costo, ganancia bruta y margen",
    filtros_admitidos=("desde", "hasta", "agrupar", "nivel", "proveedor_id", "categoria_id"),
    columnas=_columnas,
    consulta=_consulta,
    agrupaciones=(Agrupar.DIA, Agrupar.MES, Agrupar.CATEGORIA, Agrupar.PROVEEDOR),
)
```

- [ ] **Step 7: Registrar en `backend/app/reports/definiciones/__init__.py`**

```python
from app.reports.definiciones import (
    medios_pago, productos_vendidos, rentabilidad, stock_valorizado, vendedores, ventas_periodo,
)

REPORTES = {d.clave: d for d in (
    ventas_periodo.DEFINICION,
    medios_pago.DEFINICION,
    vendedores.DEFINICION,
    productos_vendidos.DEFINICION,
    rentabilidad.DEFINICION,
    stock_valorizado.DEFINICION,
)}
```

- [ ] **Step 8: Correr, corregir y commitear**

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_reportes_ventas.py tests/test_reportes.py -q`
Expected: PASS. Si un número no coincide, recalcularlo a mano contra la tabla de datos de esta tarea ANTES de tocar el test: los esperados están derivados de esa tabla. Luego la suite completa → PASS.

```bash
git add backend/app/reports/definiciones backend/tests/test_reportes_ventas.py
git commit -m "feat(reportes): reportes de ventas, medios de pago, vendedores, productos y rentabilidad

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pantallas (sidebar, hub y pantalla genérica)

**Revisión:** sin revisor por tarea (la cubre la revisión final).

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/reportes/hub.html`, `backend/app/templates/pages/reportes/reporte.html`, `backend/app/static/js/reporte.js`
- Test: `backend/tests/test_paginas_reportes.py`, `backend/tests_js/reporte.test.mjs`

**Interfaces:**
- Consumes: `REPORTES` (Task 1/2); API `GET /api/v1/reportes/{clave}` (`ReporteResponse`), `/opciones`, `/{clave}/excel`, `/{clave}/pdf`; `AGRUPACIONES`, `ORDENES` (`core/etiquetas.py`); globales de `app.js`: `pedir`, `ultimaRespuesta`, `toast`, `pesos`, `fecha`, `abrirPdf`.
- Produces: `window.reporteLogica` (`filtrosIniciales`, `queryDeFiltros`, `formatear`, `alineacion`) y el componente Alpine `window.reporte`.

- [ ] **Step 1: Tests de páginas `backend/tests/test_paginas_reportes.py`**

```python
"""Pantallas de Reportes (sesión 09): ítem del sidebar, hub y pantalla genérica."""
from app.api.pages import MENU_SIDEBAR

CLAVES = ("ventas-periodo", "medios-pago", "vendedores", "productos-vendidos", "rentabilidad", "stock-valorizado")


def test_reportes_va_entre_caja_y_configuraciones():
    urls = [item["url"] for item in MENU_SIDEBAR]
    assert urls[urls.index("/caja") + 1] == "/reportes"
    assert urls[urls.index("/reportes") + 1] == "/configuracion"


def test_admin_ve_el_item_y_el_hub_con_los_seis_reportes(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    assert 'href="/reportes"' in cliente.get("/").text
    html = cliente.get("/reportes").text
    for clave in CLAVES:
        assert f'href="/reportes/{clave}"' in html


def test_supervisor_ve_la_pantalla_de_un_reporte(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("supervisor")).get("/reportes/rentabilidad")
    assert r.status_code == 200
    assert "Rentabilidad" in r.text and "/static/js/reporte.js" in r.text
    assert 'id="reporte-proveedor"' in r.text and 'id="reporte-categoria"' in r.text


def test_vendedor_no_ve_reportes(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert 'href="/reportes"' not in cliente.get("/").text
    assert cliente.get("/reportes").status_code == 403
    assert cliente.get("/reportes/rentabilidad").status_code == 403


def test_reporte_inexistente_404(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("admin")).get("/reportes/no-existe").status_code == 404


def test_la_pantalla_muestra_solo_los_filtros_que_admite(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    periodo = cliente.get("/reportes/ventas-periodo").text
    assert 'id="reporte-desde"' in periodo and 'id="reporte-agrupar"' in periodo
    assert 'id="reporte-proveedor"' not in periodo and 'id="reporte-limite"' not in periodo
    stock = cliente.get("/reportes/stock-valorizado").text
    assert 'id="reporte-desde"' not in stock and 'id="reporte-nivel"' in stock
    medios = cliente.get("/reportes/medios-pago").text
    assert 'id="reporte-vendedor"' in medios and 'id="reporte-medio"' in medios
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_paginas_reportes.py -q`
Expected: FAIL.

- [ ] **Step 2: Rutas en `backend/app/api/pages.py`**

Imports: sumar `AGRUPACIONES, ORDENES` al import de `app.core.etiquetas` (o agregarlo si hoy importa solo algunas constantes) y `from app.reports.definiciones import REPORTES`. Si `PaginaNoEncontrada` y `ahora_db` no están importados en el módulo, ya se usan en él (`PaginaNoEncontrada` es clase local; `ahora_db` se usa en `resumen_ventas`).

Después de `PAGINA_CERRAR_TURNO`:

```python
# Ítem del sidebar del módulo de reportes (sesión 09): hub "Reportes".
PAGINA_REPORTES = {"nombre": "Reportes", "url": "/reportes", "icono": "reportes", "modulo": Modulo.REPORTES}
# Tarjetas del hub: una por reporte del registro, con el mismo permiso que el ítem.
SECCIONES_REPORTES: list[dict] = [
    {"nombre": d.nombre, "descripcion": d.descripcion, "title": d.descripcion,
     "url": f"/reportes/{d.clave}", "modulo": Modulo.REPORTES}
    for d in REPORTES.values()
]
```

En `MENU_SIDEBAR`, `PAGINA_REPORTES` entre `PAGINA_CAJA` y el ítem "Configuraciones".

Al final del archivo (después de las rutas de Caja):

```python
# --- Reportes (sesión 09) --------------------------------------------------------

@router.get("/reportes")
def reportes_hub(request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_pagina(PAGINA_REPORTES, actual="/reportes"))):
    return _pagina(request, "pages/reportes/hub.html",
                   contexto_base(request, db, "/reportes", usuario, secciones=SECCIONES_REPORTES))


@router.get("/reportes/{clave}")
def reporte(clave: str, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(requiere_pagina(PAGINA_REPORTES, actual="/reportes"))):
    """Pantalla genérica: los filtros que se muestran salen de la definición;
    las columnas, de la respuesta de la API."""
    definicion = REPORTES.get(clave)
    if definicion is None:
        raise PaginaNoEncontrada(contexto_base(request, db, "/reportes", usuario))
    etiquetas = dict(AGRUPACIONES)
    hoy = ahora_db().date()
    return _pagina(request, "pages/reportes/reporte.html", contexto_base(
        request, db, "/reportes", usuario,
        reporte={"clave": definicion.clave, "nombre": definicion.nombre,
                 "filtros_admitidos": list(definicion.filtros_admitidos),
                 "agrupaciones": [a.value for a in definicion.agrupaciones]},
        agrupaciones=[(a.value, etiquetas[a.value]) for a in definicion.agrupaciones],
        ordenes=ORDENES,
        hoy_iso=hoy.isoformat(),
        inicio_mes_iso=hoy.replace(day=1).isoformat(),
    ))
```

- [ ] **Step 3: Hub `backend/app/templates/pages/reportes/hub.html`**

```html
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/hub.html" import hub %}
{% block titulo %}Reportes · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Reportes") }}
{{ hub(secciones) }}
{% endblock %}
```

- [ ] **Step 4: Pantalla `backend/app/templates/pages/reportes/reporte.html`**

```html
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/table.html" import barra_filtros %}
{% from "components/combobox.html" import combobox %}
{% block titulo %}{{ reporte.nombre }} · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{# Pantalla genérica de los seis reportes: los filtros salen de la definición
   (solo se muestran los que el reporte admite) y las columnas de la respuesta
   de la API. Tabla agregada: sin paginación, con fila de totales al pie.
   Filtros con "Buscar" explícito (Principio 5, alto volumen). Excel y PDF
   usan los filtros de la última búsqueda, es decir, lo que se ve. #}
{% set admite = reporte.filtros_admitidos %}
<div x-data="reporte({ clave: {{ reporte.clave|js }}, admitidos: {{ admite|js }}, agrupaciones: {{ reporte.agrupaciones|js }}, hoyIso: {{ hoy_iso|js }}, inicioMesIso: {{ inicio_mes_iso|js }} })">
  {% call encabezado(reporte.nombre, "/reportes", "Reportes") %}
    <a class="boton boton-secundario" :href="urlExportar('excel')" :class="aplicados ? '' : 'pointer-events-none opacity-50'"
       :aria-disabled="!aplicados" target="_blank" rel="noopener">Excel</a>
    <button type="button" class="boton boton-secundario" :disabled="!aplicados" @click="abrirPdf()">PDF</button>
  {% endcall %}

  {% call barra_filtros(total="filas.length", etiqueta="filas", buscar="buscar()") %}
    {% if "desde" in admite %}
    <div class="flex flex-col gap-1">
      <label for="reporte-desde" class="text-lg font-medium text-texto">Desde</label>
      <input id="reporte-desde" type="date" class="campo" x-model="filtros.desde">
    </div>
    <div class="flex flex-col gap-1">
      <label for="reporte-hasta" class="text-lg font-medium text-texto">Hasta</label>
      <input id="reporte-hasta" type="date" class="campo" x-model="filtros.hasta">
    </div>
    {% endif %}
    {% if agrupaciones %}
    <div class="flex flex-col gap-1">
      <label for="reporte-agrupar" class="text-lg font-medium text-texto">Agrupar por</label>
      <select id="reporte-agrupar" class="campo" x-model="filtros.agrupar">
        {% for valor, texto in agrupaciones %}<option value="{{ valor }}">{{ texto }}</option>{% endfor %}
      </select>
    </div>
    {% endif %}
    {% if "nivel" in admite %}
    <div class="flex flex-col gap-1" x-show="filtros.agrupar === 'categoria'">
      <label for="reporte-nivel" class="text-lg font-medium text-texto">Nivel de categoría</label>
      <select id="reporte-nivel" class="campo" x-model="filtros.nivel">
        {% for n in range(1, 6) %}<option value="{{ n }}">Nivel {{ n }}</option>{% endfor %}
      </select>
    </div>
    {% endif %}
    {% if "orden" in admite %}
    <div class="flex flex-col gap-1">
      <label for="reporte-orden" class="text-lg font-medium text-texto">Ordenar por</label>
      <select id="reporte-orden" class="campo" x-model="filtros.orden">
        {% for valor, texto in ordenes %}<option value="{{ valor }}">{{ texto }}</option>{% endfor %}
      </select>
    </div>
    {% endif %}
    {% if "limite" in admite %}
    <div class="flex flex-col gap-1">
      <label for="reporte-limite" class="text-lg font-medium text-texto">Límite</label>
      <input id="reporte-limite" type="number" min="1" max="500" step="1" inputmode="numeric" class="campo" x-model="filtros.limite">
    </div>
    {% endif %}
    {% if "proveedor_id" in admite %}{{ combobox("reporte-proveedor", "opciones.proveedores", "filtros.proveedor_id", texto="nombre", etiqueta="Proveedor") }}{% endif %}
    {% if "categoria_id" in admite %}{{ combobox("reporte-categoria", "opciones.categorias", "filtros.categoria_id", texto="nombre", etiqueta="Categoría") }}{% endif %}
    {% if "usuario_id" in admite %}{{ combobox("reporte-vendedor", "opciones.vendedores", "filtros.usuario_id", texto="nombre", etiqueta="Vendedor") }}{% endif %}
    {% if "medio_de_pago_id" in admite %}{{ combobox("reporte-medio", "opciones.medios_de_pago", "filtros.medio_de_pago_id", texto="nombre", etiqueta="Medio de pago") }}{% endif %}
  {% endcall %}

  <div class="tarjeta overflow-hidden p-0">
    <div class="overflow-x-auto">
      <table class="tabla">
        <thead>
          <tr>
            <template x-for="columna in columnas" :key="columna.clave">
              <th scope="col" :class="alineacion(columna)" x-text="columna.titulo"></th>
            </template>
          </tr>
        </thead>
        <tbody>
          <template x-for="(fila, indice) in filas" :key="indice">
            <tr>
              <template x-for="columna in columnas" :key="columna.clave">
                <td :class="alineacion(columna)" x-text="celda(fila, columna)"></td>
              </template>
            </tr>
          </template>
          <tr x-show="cargando"><td :colspan="columnas.length || 1" class="py-10 text-center text-texto-muted">Cargando…</td></tr>
          <tr x-show="!cargando && !filas.length"><td :colspan="columnas.length || 1" class="py-10 text-center text-texto-muted">No hay datos para los filtros elegidos.</td></tr>
        </tbody>
        <tfoot x-show="!cargando && filas.length" x-cloak class="border-t-2 border-borde font-semibold text-texto-header">
          <tr>
            <template x-for="(columna, indice) in columnas" :key="columna.clave">
              <td :class="alineacion(columna)" x-text="celdaTotal(columna, indice)"></td>
            </template>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/reporte.js') }}"></script>{% endblock %}
```

- [ ] **Step 5: Tests JS `backend/tests_js/reporte.test.mjs`**

```js
// Tests de la pantalla genérica de reportes (backend/app/static/js/reporte.js):
// funciones puras de window.reporteLogica. Mismos stubs mínimos que
// ventas.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_REPORTE = new URL('../app/static/js/reporte.js', import.meta.url);

function cargar() {
  const document = {
    addEventListener: () => {},
    documentElement: { classList: { contains: () => false } },
    createElement: () => ({}),
  };
  const window = {
    document,
    addEventListener: () => {},
    dispatchEvent: () => {},
    localStorage: {},
    fetch: () => Promise.resolve({ status: 204 }),
  };
  const contexto = {
    window,
    document,
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; },
    URLSearchParams,
    fetch: () => Promise.reject(new Error('sin red')),
    setTimeout: () => 0,
    clearTimeout: () => {},
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_REPORTE, 'utf8'), contexto);
  return window.reporteLogica;
}

const L = cargar();
const PRODUCTOS = ['desde', 'hasta', 'agrupar', 'nivel', 'orden', 'limite', 'proveedor_id', 'categoria_id'];

test('filtros iniciales: mes actual, primera agrupación y valores por defecto', () => {
  const f = L.filtrosIniciales({ admitidos: PRODUCTOS, agrupaciones: ['producto', 'categoria'],
                                 hoyIso: '2026-09-29', inicioMesIso: '2026-09-01' });
  assert.deepEqual({ ...f }, { desde: '2026-09-01', hasta: '2026-09-29', agrupar: 'producto', nivel: '1',
                               orden: 'unidades', limite: '50', proveedor_id: null, categoria_id: null });
});

test('filtros iniciales sin fechas (stock valorizado)', () => {
  const f = L.filtrosIniciales({ admitidos: ['agrupar', 'nivel'], agrupaciones: ['categoria', 'proveedor'],
                                 hoyIso: '2026-09-29', inicioMesIso: '2026-09-01' });
  assert.deepEqual({ ...f }, { agrupar: 'categoria', nivel: '1' });
});

test('query: omite vacíos y no admitidos; el nivel solo al agrupar por categoría', () => {
  const q = L.queryDeFiltros(
    { desde: '2026-09-01', hasta: '', agrupar: 'producto', nivel: '2', proveedor_id: 7, usuario_id: 3, categoria_id: null },
    ['desde', 'hasta', 'agrupar', 'nivel', 'proveedor_id', 'categoria_id']);
  assert.deepEqual({ ...q }, { desde: '2026-09-01', agrupar: 'producto', proveedor_id: '7' });
  assert.equal(L.queryDeFiltros({ agrupar: 'categoria', nivel: '2' }, ['agrupar', 'nivel']).nivel, '2');
});

test('formato de cada tipo de columna', () => {
  assert.equal(L.formatear('1234.50', 'moneda'), '$ 1.234,50');
  assert.equal(L.formatear(1234, 'entero'), '1.234');
  assert.equal(L.formatear('47.92', 'porcentaje'), '47,9 %');
  assert.equal(L.formatear('2025-03-01', 'fecha'), '01/03/2025');
  assert.equal(L.formatear('2025-03-01', 'mes'), '03/2025');
  assert.equal(L.formatear('Rep R > Rep S', 'texto'), 'Rep R > Rep S');
  assert.equal(L.formatear(null, 'moneda'), '');
});

test('alineación: solo los números a la derecha', () => {
  assert.match(L.alineacion('moneda'), /text-right/);
  assert.match(L.alineacion('porcentaje'), /text-right/);
  assert.equal(L.alineacion('texto'), '');
  assert.equal(L.alineacion('fecha'), '');
});
```

Run: `node --test backend/tests_js/`
Expected: FAIL (no existe `reporte.js`).

- [ ] **Step 6: `backend/app/static/js/reporte.js`**

```js
/* Pantalla genérica de reportes (/reportes/{clave}): filtros según lo que
   admite el reporte, tabla con las columnas que devuelve la API
   (app/api/v1/reportes.py) y fila de totales. Excel y PDF usan los filtros
   de la última búsqueda exitosa (lo que se está viendo). */
(function () {
  'use strict';

  const API = '/api/v1/reportes';
  const NUMERICOS = ['entero', 'moneda', 'porcentaje'];
  const CATALOGOS = ['proveedor_id', 'categoria_id', 'usuario_id', 'medio_de_pago_id'];

  // ---------- Lógica pura (testeada con node --test en tests_js/reporte.test.mjs) ----------
  window.reporteLogica = {
    // Por defecto: mes actual, primera agrupación del reporte, nivel 1,
    // orden por unidades y límite 50 (los mismos que completa el backend).
    filtrosIniciales: ({ admitidos, agrupaciones, hoyIso, inicioMesIso }) => {
      const filtros = {};
      if (admitidos.includes('desde')) { filtros.desde = inicioMesIso; filtros.hasta = hoyIso; }
      if (agrupaciones.length) filtros.agrupar = agrupaciones[0];
      if (admitidos.includes('nivel')) filtros.nivel = '1';
      if (admitidos.includes('orden')) filtros.orden = 'unidades';
      if (admitidos.includes('limite')) filtros.limite = '50';
      for (const clave of CATALOGOS) if (admitidos.includes(clave)) filtros[clave] = null;
      return filtros;
    },

    // Query de la API: solo los filtros admitidos y con valor; el nivel solo
    // al agrupar por categoría (el backend rechaza el resto con 422).
    queryDeFiltros: (filtros, admitidos) => {
      const params = {};
      for (const clave of admitidos) {
        const valor = filtros[clave];
        if (valor === null || valor === undefined) continue;
        const texto = String(valor).trim();
        if (!texto) continue;
        if (clave === 'nivel' && filtros.agrupar !== 'categoria') continue;
        params[clave] = texto;
      }
      return params;
    },

    // Celda según el tipo de columna (la API manda números crudos).
    formatear: (valor, tipo) => {
      if (valor === null || valor === undefined || valor === '') return '';
      switch (tipo) {
        case 'entero': return window.pesos(valor);
        case 'moneda': return '$ ' + window.pesos(valor);
        case 'porcentaje':
          return Number(valor).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' %';
        case 'fecha': return window.fecha(valor);
        case 'mes': return window.fecha(valor).slice(3);   // "01/03/2025" → "03/2025"
        default: return String(valor);
      }
    },

    alineacion: (tipo) => (NUMERICOS.includes(tipo) ? 'text-right whitespace-nowrap' : ''),
  };
  const L = window.reporteLogica;

  window.reporte = function ({ clave, admitidos, agrupaciones, hoyIso, inicioMesIso }) {
    const iniciales = () => L.filtrosIniciales({ admitidos, agrupaciones, hoyIso, inicioMesIso });
    return {
      filtros: iniciales(),
      aplicados: null,   // query de la última búsqueda exitosa (la usan Excel y PDF)
      opciones: { proveedores: [], categorias: [], vendedores: [], medios_de_pago: [] },
      columnas: [],
      filas: [],
      totales: {},
      cargando: false,
      _ultima: window.ultimaRespuesta(),

      init() {
        this.buscar();
        if (CATALOGOS.some((c) => admitidos.includes(c))) this._cargarOpciones();
      },

      async _cargarOpciones() {
        try {
          this.opciones = await window.pedir(`${API}/opciones`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      limpiarFiltros() {
        this.filtros = iniciales();
        this.buscar();
      },

      async buscar() {
        const params = L.queryDeFiltros(this.filtros, admitidos);
        this.cargando = true;
        try {
          const respuesta = await this._ultima(window.pedir(`${API}/${clave}?${new URLSearchParams(params)}`));
          if (respuesta === undefined) return;   // llegó un pedido más nuevo
          this.columnas = respuesta.columnas;
          this.filas = respuesta.filas;
          this.totales = respuesta.totales;
          this.aplicados = params;
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      urlExportar(formato) {
        if (!this.aplicados) return '#';
        return `${API}/${clave}/${formato}?${new URLSearchParams(this.aplicados)}`;
      },

      abrirPdf() {
        if (this.aplicados) window.abrirPdf(this.urlExportar('pdf'));
      },

      // ---------- Celdas ----------
      alineacion(columna) { return L.alineacion(columna.tipo); },
      celda(fila, columna) { return L.formatear(fila[columna.clave], columna.tipo); },
      // Fila de totales: "Total" en la primera columna (la del grupo, que no se totaliza).
      celdaTotal(columna, indice) { return indice === 0 ? 'Total' : L.formatear(this.totales[columna.clave], columna.tipo); },
    };
  };
})();
```

- [ ] **Step 7: Correr, verificar y commitear**

Run:
```bash
node --check backend/app/static/js/reporte.js
node --test backend/tests_js/
docker compose exec -T backend pytest -p no:warnings -q
```
Expected: todo PASS.

Verificación manual rápida (sin crear datos en la base de desarrollo): abrir `/reportes` y `/reportes/rentabilidad` con el usuario admin que ya existe, a 320px y a 1440px: sin scroll horizontal de la página (la tabla scrollea dentro de su tarjeta), filtros apilados en mobile, "Excel" descarga y "PDF" abre en otra pestaña. Si no se puede verificar en el navegador, dejarlo anotado para la revisión final.

```bash
git add backend/app/api/pages.py backend/app/templates/pages/reportes backend/app/static/js/reporte.js \
  backend/tests/test_paginas_reportes.py backend/tests_js/reporte.test.mjs
git commit -m "feat(reportes): hub de reportes, pantalla genérica y exportación desde la pantalla

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cierre del módulo (lo hace el controlador, no un implementador)

1. Revisión final completa con Opus sobre `git diff dev...modulo-09-reportes`.
2. Una sola tanda de correcciones (`fix(reportes): correcciones de la revisión final del módulo 09`).
3. Actualizar `docs/pendientes.md` con lo que quede abierto (sección "Módulo 09: pendientes") y commitear el plan y el spec de diseño (`docs(reportes): …`).
4. Merge a la rama local `dev` (nunca a `main`, nunca push), cuando el usuario lo pida.
