# Módulo 03 — Proveedores y valor del dólar: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ABM de proveedores (cada uno en pesos o en dólares), valor del dólar propio de cada proveedor con historial inmutable, cambio individual, cambio masivo (valor o porcentaje) e importación por Excel, más sus pantallas; y cerrar el pendiente prioritario del módulo 02 (carrera al cambiar el rol editando un usuario).

**Architecture:** Igual que el módulo 02: API REST (`/api/v1/proveedores`) con services sin commit, errores tipados y auditoría en la misma transacción; pantallas Jinja + componentes Alpine que consumen la API. Un núcleo único `_aplicar_cambio_dolar` para todo cambio de dólar. Utilidad común `core/excel.py` para leer/generar planillas (la reusa la importación del módulo 08). El recálculo de precios se engancha con import local a `services.productos` (llega en el módulo 04).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 15, openpyxl 3.1, Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/03_proveedores.md` + `CLAUDE.md` + `docs/pendientes.md` ("Módulo 02-B: pendientes" y "Patrones que 03-09 deben copiar").

## Global Constraints

- Código, textos y comentarios en español (voseo).
- **Git:** rama local `modulo-03-proveedores`. UN commit por tarea: `feat(proveedores): …` (o `fix(…): …` en correcciones) + línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase ni merge. Nunca commitear `.env`, `uploads/`, `backups/`.
- La carpeta está sincronizada con iCloud: si git o una lectura masiva se cuelga o da "Operation timed out", correr `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest …`, suite completa antes de cada commit). JS: `node --check` de cada archivo tocado y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores con `NoEncontrado`/`SinPermiso`/`ReglaDeNegocio`/`DatoInvalido`; auditoría con `registrar_auditoria` y `estado_anterior` como `snapshot` previo al cambio. Routers hacen `db.commit()`.
- Filtros de texto con `filtro_texto` (insensibles a mayúsculas y tildes). Montos como `Decimal` redondeados con `redondear` (half-up, 2 decimales).
- Pantallas: patrones de `docs/pendientes.md` → `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; `x-html` solo con datos pasados por `escaparHtml`/`estadoHtml`; escrituras con `pedir()`; listados con `ultimaRespuesta()`; `erroresDeCampos()` para 422; `confirmar()` antes de acciones destructivas; reusar macros de `templates/components/`. Los modales solo se cierran con la X.
- Proveedores es una tabla chica: sin paginación, filtros en tiempo real (debounce 400 ms en texto).

## Desvíos deliberados respecto del spec

1. El nombre del proveedor es único sin distinguir mayúsculas ni tildes (índice único en la base + validación con mensaje claro). El spec no lo decía, pero la importación del módulo 08 identifica proveedores por nombre y dos "Córdoba SA"/"cordoba sa" serían ambiguos.
2. Salir de `inhabilitado` hacia cualquier estado (no solo a `activo`) exige Admin.
3. `ProveedorResponse` incluye `activo` y `en_dolares` (propiedades del modelo) para las pantallas.
4. Los helpers de Excel (`leer_tabla`, `generar_plantilla`, `celda_decimal`, `celda_entero`) viven en `core/excel.py` desde este módulo (el 08 los reusa).
5. El enum de SQLAlchemy con `values_callable` se centraliza en `app/models/tipos.py::enum_db` (y lo usa también `sesiones.py`).

---

## File Structure

```
backend/app/static/js/usuarios.js                  (mod) Task 1: carrera de alCambiarRol
backend/tests_js/usuarios.test.mjs                 (new) Task 1
backend/app/core/excel.py                          (new) Task 2
backend/tests/test_excel.py                        (new) Task 2
backend/app/models/tipos.py                        (new) Task 3: enum_db
backend/app/models/proveedores.py                  (new) Task 3
backend/app/models/sesiones.py, __init__.py        (mod) Task 3
backend/migrations/versions/0003_proveedores.py    (new) Task 3
backend/tests/test_modelo_proveedores.py           (new) Task 3
backend/app/schemas/proveedores.py                 (new) Task 4 (+ Task 5)
backend/app/services/proveedores.py                (new) Task 4 (+ Task 5)
backend/tests/test_proveedores_service.py          (new) Task 4
backend/tests/test_dolar_service.py                (new) Task 5
backend/app/api/v1/proveedores.py, __init__.py     (new/mod) Task 6
backend/tests/test_proveedores_api.py              (new) Task 6
backend/app/api/pages.py                           (mod) Tasks 7-8
backend/app/templates/pages/proveedores/listado.html, _modal_ficha.html, _modal_form.html, _modal_baja.html (new) Task 7
backend/app/static/js/proveedores.js               (new) Task 7
backend/tests/test_paginas_proveedores.py          (new) Tasks 7-8
backend/app/templates/pages/proveedores/dolar_masivo.html, backend/app/static/js/dolar_masivo.js (new) Task 8
```

---

### Task 1: Carrera al cambiar el rol editando un usuario (pendiente del 02-B)

**Files:**
- Modify: `backend/app/static/js/usuarios.js`
- Create: `backend/tests_js/usuarios.test.mjs`

**Interfaces:**
- Consumes: `window.ultimaRespuesta()` (app.js), `window.pedir`, `window.toast`. Estado actual del componente `usuariosListado`: `accesosCargados`, `marcados`, `marcadosOriginales`, `accesos`, `form`, `alCambiarRol()`.
- Produces: `alCambiarRol()` bloquea el guardado (`accesosCargados = false`) mientras carga los accesos del rol nuevo, en el alta Y en la edición; ignora respuestas viejas (secuenciador `_ultimaRol`); si la carga falla, queda bloqueado y avisa "Volvé a elegir el rol.".

- [ ] **Step 1: Test que falla**

Leer `backend/tests_js/permisos.test.mjs` y `backend/tests_js/index.js` para seguir el mismo patrón (vm + `window` falso). Crear `backend/tests_js/usuarios.test.mjs` que cargue en el mismo contexto `backend/app/static/js/app.js` (con stubs mínimos: `document` con `addEventListener` y `documentElement.classList.contains`, `window.fetch`, `window.dispatchEvent`, `localStorage`, `matchMedia`, `setTimeout`/`clearTimeout`) para usar el `ultimaRespuesta` real, y después `usuarios.js`. Stub de `window.pedir` que devuelve promesas controladas por el test (un "deferred" por URL). Casos:
1. Edición (`form.id = 7`, `accesosCargados = true`): llamar `alCambiarRol()` con `form.rol_id = 3` → mientras la promesa no se resolvió, `accesosCargados === false`; al resolverla con una lista de accesos, `accesosCargados === true` y `accesos` es esa lista.
2. Dos cambios de rol seguidos (rol 3 y después rol 4) donde la respuesta del rol 3 llega DESPUÉS de la del rol 4 → el estado final (`accesos`) es el del rol 4 y `accesosCargados === true`.
3. Falla la carga (la promesa se rechaza con `Error('Sin conexión')`) → `accesosCargados === false` y se llamó `toast` con un mensaje que contiene "Volvé a elegir el rol.".
4. Alta sin rol (`form.id = null`, `form.rol_id = null`) → `accesosCargados === true` y `accesos` vacío.
Agregar el archivo al `index.js` si ese índice lista los tests a mano.

Run: `node --test backend/tests_js/` → FAIL (casos 1-3).

- [ ] **Step 2: Implementación**

En el estado del componente, junto a `_ultima`, agregar `_ultimaRol: window.ultimaRespuesta(),` y reemplazar `alCambiarRol()` por:
```js
      async alCambiarRol() {
        // Mientras cargan los accesos del rol nuevo no se puede guardar,
        // ni en el alta ni en la edición (quedarían sin reconciliar).
        if (!this.form.rol_id) {
          this.accesos = [];
          this.accesosCargados = !this.form.id;  // en el alta no hay nada que perder
          return;
        }
        this.accesosCargados = false;
        try {
          const delRol = await this._ultimaRol(window.pedir(`${API}/accesos?rol_id=${this.form.rol_id}`));
          if (delRol === undefined) return;  // llegó la respuesta de un rol elegido después
          const heredados = new Set(delRol.filter((a) => a.heredado).map((a) => a.clave));
          this.marcados = this.marcados.filter((clave) => !heredados.has(clave));
          this.accesos = delRol;
          this.accesosCargados = true;
        } catch (e) {
          window.toast(`${e.message} Volvé a elegir el rol.`, 'error');
        }
      },
```

- [ ] **Step 3: Verificar** — `node --test backend/tests_js/` (todo verde), `node --check backend/app/static/js/usuarios.js`, suite de pytest completa.

- [ ] **Step 4: Commit** — `fix(pantallas): no guardar accesos sin reconciliar al cambiar el rol de un usuario`. En el mismo commit, en `docs/pendientes.md`, borrar el ítem "Carrera al cambiar el rol editando un usuario" y el de "No hay tests de JS para la lógica del formulario de usuario".

---

### Task 2: Utilidad común de Excel (`core/excel.py`)

**Files:**
- Create: `backend/app/core/excel.py`
- Test: `backend/tests/test_excel.py`

**Interfaces:**
- Produces: `TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024`, `FILAS_MAXIMAS = 5000`, `TIPO_XLSX` (media type), `clave_columna(texto) -> str` (sin tildes, minúsculas, espacios colapsados), `leer_tabla(contenido: bytes, requeridas, opcionales=()) -> list[tuple[int, dict]]` (número de fila de Excel + `{columna: valor}` con las claves ya normalizadas; saltea filas vacías; 409 `ReglaDeNegocio` si el archivo está vacío, no es xlsx, supera 5 MB o 5000 filas, o faltan columnas requeridas), `generar_plantilla(hoja, columnas, instrucciones, filas=None) -> bytes` (hoja de datos con encabezados en negrita, anchos ajustados, panel congelado y filas precargadas; hoja "Instrucciones" con las filas dadas, la primera en negrita), `celda_decimal(valor) -> Decimal | None` (None si vacío; `ValueError` si no es número finito; acepta int/float/Decimal y texto "1.234,56", "1234,5", "1234.5"), `celda_entero(valor) -> int | None` (como `celda_decimal` pero exige entero).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_excel.py`:
```python
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from app.core.errores import ReglaDeNegocio
from app.core.excel import (
    FILAS_MAXIMAS,
    celda_decimal,
    celda_entero,
    clave_columna,
    generar_plantilla,
    leer_tabla,
)


def _xlsx(filas) -> bytes:
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_clave_columna():
    assert clave_columna("  Dólar   Nuevo ") == "dolar nuevo"
    assert clave_columna("Proveedor_ID") == "proveedor_id"
    assert clave_columna(None) == ""


def test_leer_tabla_ubica_columnas_por_nombre_y_saltea_vacias():
    contenido = _xlsx([
        ["Extra", "DOLAR_NUEVO", "Proveedor_ID"],
        ["x", 1250.5, 3],
        [None, None, None],
        ["", "  ", None],
        ["y", "1.300,25", "4"],
    ])
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    assert filas == [
        (2, {"proveedor_id": 3, "dolar_nuevo": 1250.5, "nombre": None}),
        (5, {"proveedor_id": "4", "dolar_nuevo": "1.300,25", "nombre": None}),
    ]


@pytest.mark.parametrize(
    "contenido, mensaje",
    [
        (b"", "vacío"),
        (b"no soy un excel", "no es un Excel"),
        (None, "Faltan columnas: dolar_nuevo"),
    ],
)
def test_leer_tabla_rechaza_archivos_invalidos(contenido, mensaje):
    if contenido is None:
        contenido = _xlsx([["proveedor_id"], [1]])
    with pytest.raises(ReglaDeNegocio) as error:
        leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"])
    assert mensaje in error.value.mensaje


def test_leer_tabla_limita_filas():
    contenido = _xlsx([["proveedor_id"]] + [[i] for i in range(FILAS_MAXIMAS + 1)])
    with pytest.raises(ReglaDeNegocio) as error:
        leer_tabla(contenido, ["proveedor_id"])
    assert str(FILAS_MAXIMAS) in error.value.mensaje


def test_plantilla_ida_y_vuelta():
    contenido = generar_plantilla(
        "Dolar", ["proveedor_id", "nombre", "dolar_nuevo"],
        [["Columna", "Qué poner"], ["dolar_nuevo", "El valor nuevo"]],
        filas=[[1, "Importadora Sur", Decimal("1250.50")]],
    )
    libro = load_workbook(BytesIO(contenido))
    assert libro.sheetnames == ["Dolar", "Instrucciones"]
    assert libro["Dolar"]["A1"].font.bold and libro["Dolar"].freeze_panes == "A2"
    assert libro["Instrucciones"]["A1"].value == "Columna"
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    assert filas == [(2, {"proveedor_id": 1, "dolar_nuevo": 1250.5, "nombre": "Importadora Sur"})]


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (None, None), ("", None), ("  ", None), (3, Decimal("3")), (1250.5, Decimal("1250.5")),
        (Decimal("7.25"), Decimal("7.25")), ("1.234,56", Decimal("1234.56")), ("1234,5", Decimal("1234.5")),
        ("1234.5", Decimal("1234.5")), (" 1 250 ", Decimal("1250")),
    ],
)
def test_celda_decimal(valor, esperado):
    assert celda_decimal(valor) == esperado


@pytest.mark.parametrize("valor", ["abc", "NaN", "Infinity", True, "1,2,3"])
def test_celda_decimal_invalida(valor):
    with pytest.raises(ValueError):
        celda_decimal(valor)


def test_celda_entero():
    assert celda_entero(12) == 12 and celda_entero(12.0) == 12 and celda_entero("7") == 7
    assert celda_entero(None) is None
    with pytest.raises(ValueError):
        celda_entero(3.5)
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec -T backend pytest tests/test_excel.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementación**

`backend/app/core/excel.py`:
```python
"""Lectura y generación de planillas Excel (.xlsx) con openpyxl.

Única vía para importar/exportar tablas simples: el dólar por proveedor
(módulo 03) y la importación inicial (módulo 08)."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from app.core.errores import ReglaDeNegocio
from app.core.utils import normalizar_texto, sin_tildes

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024
FILAS_MAXIMAS = 5000
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def clave_columna(texto) -> str:
    """Encabezado normalizado: sin tildes, en minúscula y con espacios colapsados."""
    if texto is None:
        return ""
    return sin_tildes(normalizar_texto(str(texto)) or "").lower()


def _fila_vacia(valores) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in valores)


def leer_tabla(contenido: bytes, requeridas, opcionales=()) -> list[tuple[int, dict]]:
    """Filas de la primera hoja como (número de fila en Excel, {columna: valor}).

    Las columnas se ubican por nombre de encabezado (cualquier orden, sin
    importar mayúsculas ni tildes; las columnas extra se ignoran). `requeridas`
    y `opcionales` se pasan ya normalizadas (ej. "proveedor_id")."""
    if not contenido:
        raise ReglaDeNegocio("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise ReglaDeNegocio("El archivo supera los 5 MB.")
    try:
        libro = load_workbook(BytesIO(contenido), read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, KeyError, OSError, ValueError) as exc:
        raise ReglaDeNegocio("El archivo no es un Excel (.xlsx) válido.") from exc
    try:
        filas = libro.worksheets[0].iter_rows(values_only=True)
        encabezado = next(filas, None)
        if encabezado is None:
            raise ReglaDeNegocio("El archivo no tiene encabezados.")
        posiciones: dict[str, int] = {}
        for indice, celda in enumerate(encabezado):
            clave = clave_columna(celda)
            if clave and clave not in posiciones:
                posiciones[clave] = indice
        faltan = [c for c in requeridas if c not in posiciones]
        if faltan:
            raise ReglaDeNegocio(f"Faltan columnas: {', '.join(faltan)}")
        resultado = []
        for numero, valores in enumerate(filas, start=2):
            if valores is None or _fila_vacia(valores):
                continue
            if len(resultado) >= FILAS_MAXIMAS:
                raise ReglaDeNegocio(f"El archivo supera las {FILAS_MAXIMAS} filas.")
            fila = {}
            for columna in (*requeridas, *opcionales):
                indice = posiciones.get(columna)
                fila[columna] = valores[indice] if indice is not None and indice < len(valores) else None
            resultado.append((numero, fila))
        return resultado
    finally:
        libro.close()


def generar_plantilla(hoja: str, columnas: list[str], instrucciones: list[list], filas=None) -> bytes:
    """Libro con la hoja de datos (encabezados en negrita, filas precargadas
    opcionales) y una hoja "Instrucciones" (la primera fila en negrita)."""
    libro = Workbook()
    datos = libro.active
    datos.title = hoja
    datos.append(list(columnas))
    for fila in filas or []:
        datos.append(list(fila))
    for celda in datos[1]:
        celda.font = Font(bold=True)
    for indice, columna in enumerate(columnas, start=1):
        largo = max([len(str(columna))] + [len(str(f[indice - 1] or "")) for f in (filas or []) if len(f) >= indice])
        datos.column_dimensions[get_column_letter(indice)].width = min(max(12, largo + 4), 60)
    datos.freeze_panes = "A2"

    ayuda = libro.create_sheet("Instrucciones")
    for fila in instrucciones:
        ayuda.append(list(fila))
    for celda in ayuda[1] if instrucciones else []:
        celda.font = Font(bold=True)
    for indice in range(1, max((len(f) for f in instrucciones), default=0) + 1):
        ayuda.column_dimensions[get_column_letter(indice)].width = 40

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def celda_decimal(valor) -> Decimal | None:
    """Número de una celda. Acepta números y texto con coma o punto decimal
    ("1.234,56", "1234,5", "1234.5"). None si está vacía; ValueError si no es
    un número finito."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError("no es un número")
    if isinstance(valor, (int, Decimal)):
        numero = Decimal(valor)
    elif isinstance(valor, float):
        numero = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace(" ", "")
        if not texto:
            return None
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError("no es un número") from exc
    if not numero.is_finite():
        raise ValueError("no es un número")
    return numero


def celda_entero(valor) -> int | None:
    numero = celda_decimal(valor)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise ValueError("no es un número entero")
    return int(numero)
```

- [ ] **Step 4: Correr y ver que pasa** — el archivo de tests y la suite completa.

- [ ] **Step 5: Commit** — `feat(proveedores): utilidad común de planillas Excel`.

---

### Task 3: Migración 0003 y modelos de proveedores

**Files:**
- Create: `backend/app/models/tipos.py`, `backend/app/models/proveedores.py`, `backend/migrations/versions/0003_proveedores.py`
- Modify: `backend/app/models/sesiones.py` (usar `enum_db`), `backend/app/models/__init__.py`
- Test: `backend/tests/test_modelo_proveedores.py`

**Interfaces:**
- Produces: `enum_db(tipo, nombre)` (SQLAlchemy `Enum` que guarda los valores en minúscula); `EstadoProveedor` (`ACTIVO`, `DESACTIVADO`, `INHABILITADO`), `Moneda` (`ARS`, `USD`), `OrigenCambioDolar` (`MANUAL`, `MASIVO_VALOR`, `MASIVO_PORCENTAJE`, `IMPORTACION_EXCEL`); modelo `Proveedor` (`id, nombre, pais, provincia, telefono, email, notas, estado, moneda, dolar_actual, created_at, updated_at`; propiedades `activo`, `en_dolares`); modelo `ProveedorDolarHistorial` (`id, proveedor_id, valor_anterior, valor_nuevo, usuario_id, origen, timestamp`).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_modelo_proveedores.py`:
```python
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.utils import ahora_db
from app.models import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial, Usuario


def _admin(db):
    return db.scalar(select(Usuario).where(Usuario.username == "admin"))


def test_proveedor_en_pesos_y_en_dolares(db):
    pesos = Proveedor(nombre="Textil Norte", moneda=Moneda.ARS)
    dolares = Proveedor(nombre="Importadora Sur", moneda=Moneda.USD, dolar_actual=Decimal("1250.50"))
    db.add_all([pesos, dolares])
    db.flush()
    assert pesos.estado is EstadoProveedor.ACTIVO and pesos.activo and not pesos.en_dolares
    assert dolares.en_dolares and dolares.dolar_actual == Decimal("1250.50")
    assert db.execute(text("SELECT moneda::text FROM proveedores WHERE id = :i"), {"i": dolares.id}).scalar_one() == "usd"


@pytest.mark.parametrize(
    "moneda, dolar",
    [(Moneda.ARS, Decimal("10")), (Moneda.USD, None), (Moneda.USD, Decimal("0")), (Moneda.USD, Decimal("-1"))],
)
def test_check_moneda_y_dolar(db, moneda, dolar):
    db.add(Proveedor(nombre="Con dólar mal cargado", moneda=moneda, dolar_actual=dolar))
    with pytest.raises(IntegrityError):
        db.flush()


def test_nombre_unico_sin_mayusculas_ni_tildes(db):
    db.add(Proveedor(nombre="Córdoba Textil", moneda=Moneda.ARS))
    db.flush()
    db.add(Proveedor(nombre="cordoba textil", moneda=Moneda.ARS))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE proveedor_dolar_historial SET valor_nuevo = 1", "DELETE FROM proveedor_dolar_historial",
     "TRUNCATE proveedor_dolar_historial"],
)
def test_historial_del_dolar_es_inmutable(db, sentencia):
    proveedor = Proveedor(nombre="Importadora Este", moneda=Moneda.USD, dolar_actual=Decimal("1000"))
    db.add(proveedor)
    db.flush()
    db.add(ProveedorDolarHistorial(
        proveedor_id=proveedor.id, valor_anterior=Decimal("1000"), valor_nuevo=Decimal("1100"),
        usuario_id=_admin(db).id, origen=OrigenCambioDolar.MANUAL, timestamp=ahora_db(),
    ))
    db.flush()
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec -T backend pytest tests/test_modelo_proveedores.py -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implementación**

`backend/app/models/tipos.py`:
```python
"""Tipos compartidos por los modelos."""
from sqlalchemy import Enum as SAEnum


def enum_db(tipo, nombre: str) -> SAEnum:
    """Enum de Postgres que guarda los VALORES (en minúscula), no los nombres
    de los miembros. El tipo se crea en la migración, no desde el modelo."""
    return SAEnum(tipo, name=nombre, values_callable=lambda e: [i.value for i in e])
```
En `backend/app/models/sesiones.py`, reemplazar el `SAEnum(ResultadoAcceso, name="resultado_acceso", values_callable=...)` por `enum_db(ResultadoAcceso, "resultado_acceso")` (import `from app.models.tipos import enum_db`; quitar el import de `SAEnum` si queda sin uso).

`backend/app/models/proveedores.py`:
```python
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tipos import enum_db


class EstadoProveedor(str, Enum):
    # Tres estados en lugar de un booleano: "desactivado" se reactiva
    # libremente; "inhabilitado" solo con Admin.
    ACTIVO = "activo"
    DESACTIVADO = "desactivado"
    INHABILITADO = "inhabilitado"


class Moneda(str, Enum):
    ARS = "ars"
    USD = "usd"


class OrigenCambioDolar(str, Enum):
    MANUAL = "manual"
    MASIVO_VALOR = "masivo_valor"
    MASIVO_PORCENTAJE = "masivo_porcentaje"
    IMPORTACION_EXCEL = "importacion_excel"


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    pais: Mapped[str | None] = mapped_column(String(200))
    provincia: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoProveedor] = mapped_column(enum_db(EstadoProveedor, "estado_proveedor"), default=EstadoProveedor.ACTIVO)
    moneda: Mapped[Moneda] = mapped_column(enum_db(Moneda, "moneda"), default=Moneda.ARS)
    # Solo proveedores en dólares (CHECK en la base).
    dolar_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def activo(self) -> bool:
        return self.estado is EstadoProveedor.ACTIVO

    @property
    def en_dolares(self) -> bool:
        return self.moneda is Moneda.USD


class ProveedorDolarHistorial(Base):
    """Cada cambio real del dólar de un proveedor (append-only en la base)."""

    __tablename__ = "proveedor_dolar_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedores.id", ondelete="CASCADE"))
    valor_anterior: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    valor_nuevo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    origen: Mapped[OrigenCambioDolar] = mapped_column(enum_db(OrigenCambioDolar, "origen_cambio_dolar"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
```
Exportar `EstadoProveedor`, `Moneda`, `OrigenCambioDolar`, `Proveedor`, `ProveedorDolarHistorial` en `backend/app/models/__init__.py` (también en `__all__`).

`backend/migrations/versions/0003_proveedores.py`:
```python
"""Proveedores (en pesos o en dólares) e historial inmutable del dólar.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE estado_proveedor AS ENUM ('activo', 'desactivado', 'inhabilitado');
        CREATE TYPE moneda AS ENUM ('ars', 'usd');
        CREATE TYPE origen_cambio_dolar AS ENUM ('manual', 'masivo_valor', 'masivo_porcentaje', 'importacion_excel');

        CREATE TABLE proveedores (
            id           BIGSERIAL PRIMARY KEY,
            nombre       VARCHAR(200) NOT NULL,
            pais         VARCHAR(200),
            provincia    VARCHAR(255),
            telefono     VARCHAR(50),
            email        VARCHAR(255),
            notas        TEXT,
            estado       estado_proveedor NOT NULL DEFAULT 'activo',
            moneda       moneda NOT NULL DEFAULT 'ars',
            dolar_actual NUMERIC(10,2),          -- solo proveedores en dólares
            created_at   TIMESTAMP NOT NULL DEFAULT now(),
            updated_at   TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_proveedores_moneda_dolar CHECK (
                (moneda = 'ars' AND dolar_actual IS NULL) OR
                (moneda = 'usd' AND dolar_actual IS NOT NULL AND dolar_actual > 0)
            )
        );
        CREATE INDEX ix_proveedores_nombre ON proveedores (nombre);
        CREATE INDEX ix_proveedores_estado ON proveedores (estado);
        CREATE INDEX ix_proveedores_moneda ON proveedores (moneda);
        -- Nombre único sin distinguir mayúsculas ni tildes (la importación
        -- del módulo 08 identifica proveedores por nombre).
        CREATE UNIQUE INDEX uq_proveedores_nombre
            ON proveedores (lower(translate(nombre, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')));

        CREATE TABLE proveedor_dolar_historial (
            id             BIGSERIAL PRIMARY KEY,
            proveedor_id   BIGINT NOT NULL REFERENCES proveedores (id) ON DELETE CASCADE,
            valor_anterior NUMERIC(10,2) NOT NULL,
            valor_nuevo    NUMERIC(10,2) NOT NULL,
            usuario_id     BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            origen         origen_cambio_dolar NOT NULL,
            timestamp      TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_proveedor_dolar_historial_proveedor_id ON proveedor_dolar_historial (proveedor_id);
        CREATE INDEX ix_proveedor_dolar_historial_timestamp ON proveedor_dolar_historial (timestamp);

        -- Append-only (los proveedores nunca se borran: baja lógica).
        CREATE FUNCTION proveedor_dolar_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla proveedor_dolar_historial es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_proveedor_dolar_no_update BEFORE UPDATE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        CREATE TRIGGER trg_proveedor_dolar_no_delete BEFORE DELETE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        CREATE TRIGGER trg_proveedor_dolar_no_truncate BEFORE TRUNCATE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        REVOKE UPDATE, DELETE, TRUNCATE ON proveedor_dolar_historial FROM CURRENT_USER;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE proveedor_dolar_historial;
        DROP FUNCTION proveedor_dolar_bloquear_modificacion();
        DROP TABLE proveedores;
        DROP TYPE origen_cambio_dolar;
        DROP TYPE moneda;
        DROP TYPE estado_proveedor;
        """
    )
```

- [ ] **Step 4: Migrar y correr los tests**

```bash
docker compose restart backend && docker compose exec -T backend alembic current     # 0003 (head)
docker compose exec -T backend pytest tests/test_modelo_proveedores.py tests/test_modelo_usuarios.py -v
docker compose exec -T backend alembic downgrade -1 && docker compose exec -T backend alembic upgrade head
docker compose exec -T backend pytest -p no:warnings
```

- [ ] **Step 5: Commit** — `feat(proveedores): migración 0003 y modelos de proveedores e historial del dólar`.

---

### Task 4: Service de proveedores (listado, alta, edición, estado)

**Files:**
- Create: `backend/app/schemas/proveedores.py`, `backend/app/services/proveedores.py`
- Test: `backend/tests/test_proveedores_service.py`

**Interfaces:**
- Consumes: modelos de la Task 3, `registrar_auditoria`, `snapshot`, `filtro_texto`, `normalizar_texto`, `redondear`, `sin_tildes`, `sin_tildes_sql`, errores.
- Produces (schemas): `ProveedorCrear` (`nombre` 1-200, `pais` ≤200, `provincia` ≤255, `telefono` ≤50, `email` EmailStr|None, `notas` ≤2000, `moneda` default ARS, `dolar_actual` Decimal|None >0 con 2 decimales), `ProveedorEditar` (mismos campos; `moneda` obligatoria), `ProveedorEstado` (`estado`, `confirmar_con_productos=False`), `ProveedorResponse` (todos los campos + `activo`, `en_dolares`).
- Produces (service): `obtener_proveedor(db, id)`, `listar_proveedores(db, *, nombre=None, email=None, telefono=None, provincia=None, pais=None, estado=None, moneda=None, dolar_desde=None, dolar_hasta=None) -> list[Proveedor]`, `hay_proveedores_en_dolares(db) -> bool`, `contar_productos(db, proveedor_id, solo_activos=False) -> int` (0 si la tabla `productos` todavía no existe), `crear_proveedor(db, autor, datos, ip)`, `editar_proveedor(db, autor, proveedor, datos, ip)`, `cambiar_estado(db, autor, proveedor, nuevo_estado, confirmar_con_productos, ip)`; `validar_dolar(valor) -> Decimal` (DatoInvalido "El valor del dólar debe ser mayor a cero." si no es > 0; redondea a 2 decimales).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_proveedores_service.py`:
```python
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.errores import DatoInvalido, ReglaDeNegocio, SinPermiso
from app.models import Auditoria, EstadoProveedor, Moneda
from app.schemas.proveedores import ProveedorCrear, ProveedorEditar
from app.services import proveedores as servicio


def _crear(db, autor, **datos):
    base = {"nombre": "Proveedor de prueba", "moneda": "ars"}
    base.update(datos)
    return servicio.crear_proveedor(db, autor, ProveedorCrear(**base), None)


def _editar(db, autor, proveedor, **cambios):
    datos = {"nombre": proveedor.nombre, "moneda": proveedor.moneda.value}
    datos.update(cambios)
    return servicio.editar_proveedor(db, autor, proveedor, ProveedorEditar(**datos), None)


def test_alta_en_pesos_ignora_el_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="  Textil   Norte ", dolar_actual="100", email="Ventas@Textil.com")
    assert p.nombre == "Textil Norte" and p.moneda is Moneda.ARS and p.dolar_actual is None
    assert p.email == "ventas@textil.com"
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "proveedor.crear", Auditoria.entidad_id == p.id))


def test_alta_en_dolares_exige_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="Importadora", moneda="usd")
    p = _crear(db, admin, nombre="Importadora", moneda="usd", dolar_actual="1250.456")
    assert p.dolar_actual == Decimal("1250.46")


def test_nombre_repetido_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    _crear(db, admin, nombre="Córdoba Textil")
    with pytest.raises(ReglaDeNegocio) as error:
        _crear(db, admin, nombre="cordoba textil")
    assert "Córdoba Textil" in error.value.mensaje


def test_edicion_no_toca_el_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Importadora", moneda="usd", dolar_actual="1000")
    _editar(db, admin, p, provincia="Córdoba", dolar_actual="2000")
    assert p.provincia == "Córdoba" and p.dolar_actual == Decimal("1000")


def test_cambio_de_moneda_sin_productos(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Cambiante")
    with pytest.raises(DatoInvalido):
        _editar(db, admin, p, moneda="usd")
    _editar(db, admin, p, moneda="usd", dolar_actual="900")
    assert p.moneda is Moneda.USD and p.dolar_actual == Decimal("900")
    _editar(db, admin, p, moneda="ars")
    assert p.moneda is Moneda.ARS and p.dolar_actual is None


def test_cambio_de_moneda_con_productos_da_409(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Con productos")
    monkeypatch.setattr(servicio, "contar_productos", lambda db, proveedor_id, solo_activos=False: 3)
    with pytest.raises(ReglaDeNegocio) as error:
        _editar(db, admin, p, moneda="usd", dolar_actual="900")
    assert error.value.mensaje == "No se puede cambiar la moneda de un proveedor con productos cargados."


def test_contar_productos_sin_tabla_da_cero(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Sin tabla")
    existe = db.execute(text("SELECT to_regclass('public.productos') IS NOT NULL")).scalar_one()
    if not existe:
        assert servicio.contar_productos(db, p.id) == 0


def test_estados(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    supervisor = crear_usuario("supervisor")
    p = _crear(db, admin, nombre="Estados")
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert p.estado is EstadoProveedor.DESACTIVADO
    servicio.cambiar_estado(db, supervisor, p, EstadoProveedor.ACTIVO, False, None)  # desactivado: libre
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.INHABILITADO, False, None)
    with pytest.raises(SinPermiso) as error:
        servicio.cambiar_estado(db, supervisor, p, EstadoProveedor.ACTIVO, False, None)
    assert error.value.mensaje == "Reactivar un proveedor inhabilitado requiere Admin"
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.ACTIVO, False, None)
    acciones = db.scalars(select(Auditoria.accion).where(Auditoria.entidad == "proveedor", Auditoria.entidad_id == p.id)).all()
    assert {"proveedor.desactivar", "proveedor.reactivar", "proveedor.inhabilitar"} <= set(acciones)


def test_baja_con_productos_activos_exige_confirmacion(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Con activos")
    monkeypatch.setattr(servicio, "contar_productos", lambda db, proveedor_id, solo_activos=False: 2)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert "2 producto(s) activo(s)" in error.value.mensaje
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, True, None)
    assert p.estado is EstadoProveedor.DESACTIVADO


def test_listado_y_filtros(db, crear_usuario):
    admin = crear_usuario("admin")
    _crear(db, admin, nombre="Zeta Textil", provincia="Córdoba", pais="Argentina")
    _crear(db, admin, nombre="Alfa Import", moneda="usd", dolar_actual="1500", pais="China")
    _crear(db, admin, nombre="Beta Import", moneda="usd", dolar_actual="1100", pais="China")
    nombres = [p.nombre for p in servicio.listar_proveedores(db)]
    assert nombres[:3] == ["Alfa Import", "Beta Import", "Zeta Textil"]
    assert [p.nombre for p in servicio.listar_proveedores(db, provincia="cordoba")] == ["Zeta Textil"]
    assert [p.nombre for p in servicio.listar_proveedores(db, dolar_desde=Decimal("1200"))] == ["Alfa Import"]
    assert [p.nombre for p in servicio.listar_proveedores(db, moneda=Moneda.ARS, pais="argentina")] == ["Zeta Textil"]


def test_hay_proveedores_en_dolares_solo_activos(db, crear_usuario):
    admin = crear_usuario("admin")
    assert servicio.hay_proveedores_en_dolares(db) is False
    p = _crear(db, admin, nombre="Único en dólares", moneda="usd", dolar_actual="1000")
    assert servicio.hay_proveedores_en_dolares(db) is True
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert servicio.hay_proveedores_en_dolares(db) is False
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Schemas**

`backend/app/schemas/proveedores.py`:
```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import EstadoProveedor, Moneda

Dolar = Decimal  # alias documental: valor del dólar en pesos, 2 decimales


class ProveedorDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    pais: str | None = Field(default=None, max_length=200)
    provincia: str | None = Field(default=None, max_length=255)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    notas: str | None = Field(default=None, max_length=2000)


class ProveedorCrear(ProveedorDatos):
    moneda: Moneda = Moneda.ARS
    dolar_actual: Dolar | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)


class ProveedorEditar(ProveedorDatos):
    moneda: Moneda
    # Solo se usa al pasar de pesos a dólares: la edición no cambia el dólar.
    dolar_actual: Dolar | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)


class ProveedorEstado(BaseModel):
    estado: EstadoProveedor
    confirmar_con_productos: bool = False


class ProveedorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    pais: str | None
    provincia: str | None
    telefono: str | None
    email: str | None
    notas: str | None
    estado: EstadoProveedor
    moneda: Moneda
    dolar_actual: Decimal | None
    activo: bool
    en_dolares: bool
    created_at: datetime
    updated_at: datetime
```
(`decimal_places=3` deja pasar un tercer decimal que el service redondea half-up; más decimales → 422.)

- [ ] **Step 4: Service**

`backend/app/services/proveedores.py`:
```python
"""Proveedores: cada uno trabaja en pesos o en dólares. Baja siempre lógica."""
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import filtro_texto, normalizar_texto, redondear, sin_tildes, sin_tildes_sql
from app.models import EstadoProveedor, Moneda, Proveedor

ACCION_DE_ESTADO = {
    EstadoProveedor.ACTIVO: "proveedor.reactivar",
    EstadoProveedor.DESACTIVADO: "proveedor.desactivar",
    EstadoProveedor.INHABILITADO: "proveedor.inhabilitar",
}


def obtener_proveedor(db, proveedor_id: int) -> Proveedor:
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise NoEncontrado("Proveedor no encontrado")
    return proveedor


def listar_proveedores(db, *, nombre=None, email=None, telefono=None, provincia=None, pais=None, estado=None,
                       moneda=None, dolar_desde: Decimal | None = None, dolar_hasta: Decimal | None = None) -> list[Proveedor]:
    """Tabla chica: sin paginación, orden alfabético."""
    condiciones = [
        filtro_texto(columna, valor)
        for columna, valor in (
            (Proveedor.nombre, nombre), (Proveedor.email, email), (Proveedor.telefono, telefono),
            (Proveedor.provincia, provincia), (Proveedor.pais, pais),
        )
        if valor
    ]
    if estado is not None:
        condiciones.append(Proveedor.estado == estado)
    if moneda is not None:
        condiciones.append(Proveedor.moneda == moneda)
    # Los filtros de dólar solo alcanzan a proveedores en dólares.
    if dolar_desde is not None:
        condiciones += [Proveedor.moneda == Moneda.USD, Proveedor.dolar_actual >= dolar_desde]
    if dolar_hasta is not None:
        condiciones += [Proveedor.moneda == Moneda.USD, Proveedor.dolar_actual <= dolar_hasta]
    return list(db.scalars(select(Proveedor).where(*condiciones).order_by(func.lower(Proveedor.nombre), Proveedor.id)).all())


def hay_proveedores_en_dolares(db) -> bool:
    """¿Hay al menos un proveedor ACTIVO en dólares? Si no, las pantallas ocultan el dólar."""
    consulta = select(Proveedor.id).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO).limit(1)
    return db.scalar(consulta) is not None


def contar_productos(db, proveedor_id: int, solo_activos: bool = False) -> int:
    """Productos del proveedor. La tabla llega en el módulo 04: hasta entonces, 0."""
    if not db.execute(text("SELECT to_regclass('public.productos') IS NOT NULL")).scalar_one():
        return 0
    sql = "SELECT count(*) FROM productos WHERE proveedor_id = :id"
    if solo_activos:
        sql += " AND activo"
    return db.execute(text(sql), {"id": proveedor_id}).scalar_one()


def validar_dolar(valor) -> Decimal:
    if valor is None or Decimal(valor) <= 0:
        raise DatoInvalido("El valor del dólar debe ser mayor a cero.")
    return redondear(valor)


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [func.lower(sin_tildes_sql(Proveedor.nombre)) == sin_tildes(limpio).lower()]
    if excepto_id is not None:
        condiciones.append(Proveedor.id != excepto_id)
    existente = db.scalar(select(Proveedor).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe un proveedor llamado '{existente.nombre}'")
    return limpio


def _asignar_datos(proveedor: Proveedor, datos) -> None:
    proveedor.pais = normalizar_texto(datos.pais)
    proveedor.provincia = normalizar_texto(datos.provincia)
    proveedor.telefono = normalizar_texto(datos.telefono)
    proveedor.email = datos.email.lower() if datos.email else None
    proveedor.notas = (datos.notas or "").strip() or None


def crear_proveedor(db, autor, datos, ip) -> Proveedor:
    proveedor = Proveedor(
        nombre=_nombre_libre(db, datos.nombre),
        moneda=datos.moneda,
        # En pesos el dólar se ignora; en dólares es obligatorio y > 0.
        dolar_actual=validar_dolar(datos.dolar_actual) if datos.moneda is Moneda.USD else None,
        estado=EstadoProveedor.ACTIVO,
    )
    _asignar_datos(proveedor, datos)
    db.add(proveedor)
    db.flush()
    db.refresh(proveedor)
    registrar_auditoria(db, accion="proveedor.crear", entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor


def editar_proveedor(db, autor, proveedor: Proveedor, datos, ip) -> Proveedor:
    """No toca el dólar (tiene su propio endpoint). Cambiar la moneda solo sin productos."""
    antes = snapshot(proveedor)
    if datos.moneda is not proveedor.moneda:
        if contar_productos(db, proveedor.id):
            raise ReglaDeNegocio("No se puede cambiar la moneda de un proveedor con productos cargados.")
        proveedor.dolar_actual = validar_dolar(datos.dolar_actual) if datos.moneda is Moneda.USD else None
        proveedor.moneda = datos.moneda
    proveedor.nombre = _nombre_libre(db, datos.nombre, excepto_id=proveedor.id)
    _asignar_datos(proveedor, datos)
    db.flush()
    db.refresh(proveedor)
    registrar_auditoria(db, accion="proveedor.editar", entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor


def cambiar_estado(db, autor, proveedor: Proveedor, nuevo: EstadoProveedor, confirmar_con_productos: bool, ip) -> Proveedor:
    if nuevo is proveedor.estado:
        return proveedor
    if proveedor.estado is EstadoProveedor.INHABILITADO and not autor.es_admin:
        raise SinPermiso("Reactivar un proveedor inhabilitado requiere Admin")
    if nuevo is not EstadoProveedor.ACTIVO and not confirmar_con_productos:
        activos = contar_productos(db, proveedor.id, solo_activos=True)
        if activos:
            raise ReglaDeNegocio(
                f"El proveedor tiene {activos} producto(s) activo(s). Reasignarlos o confirmar la baja explícitamente."
            )
    antes = snapshot(proveedor)
    proveedor.estado = nuevo
    db.flush()
    registrar_auditoria(db, accion=ACCION_DE_ESTADO[nuevo], entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor
```

- [ ] **Step 5: Correr y ver que pasa** — el archivo de tests y la suite completa.

- [ ] **Step 6: Commit** — `feat(proveedores): alta, edición, estados y listado de proveedores`.

---

### Task 5: Dólar por proveedor (individual, historial, masivo y Excel)

**Files:**
- Modify: `backend/app/services/proveedores.py`, `backend/app/schemas/proveedores.py`
- Test: `backend/tests/test_dolar_service.py`

**Interfaces:**
- Consumes: `validar_dolar`, `obtener_proveedor`, modelos, `core/excel.py`, `ahora_db`, `ahora`.
- Produces (schemas): `CambioDolar {valor_nuevo}`, `ModalidadMasiva` (`VALOR="valor"`, `PORCENTAJE="porcentaje"`), `CambioMasivo {proveedor_ids: list[int] | None, modalidad, valor: Decimal}`, `PreviewDolar {proveedor_id, nombre, valor_actual, valor_nuevo}`, `HistorialDolarResponse {id, valor_anterior, valor_nuevo, origen, timestamp, usuario_id, usuario_nombre}`, `ErrorFila {fila, error}`, `ResultadoImportacionDolar {aplicados, sin_cambios, errores}`, `DolarEnUso {hay_proveedores_en_dolares}`.
- Produces (service): `cambiar_dolar(db, autor, proveedor, valor, ip) -> Proveedor`; `historial_dolar(db, proveedor_id) -> list[dict]`; `preview_masivo(db, proveedor_ids, modalidad, valor) -> list[dict]`; `aplicar_masivo(db, autor, proveedor_ids, modalidad, valor, ip) -> list[dict]`; `COLUMNAS_PLANTILLA_DOLAR`; `generar_plantilla_dolar(db) -> bytes`; `importar_dolar(db, autor, contenido, ip) -> dict`. Núcleo privado `_aplicar_cambio_dolar(db, autor, proveedor, valor, origen, ip) -> bool` (False si el valor no cambia) y `_recalcular_precios(db, proveedor_id)` (import local de `app.services.productos.recalcular_precios_de_proveedor`; si el módulo todavía no existe, no hace nada).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_dolar_service.py`:
```python
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.models import Auditoria, EstadoProveedor, OrigenCambioDolar, ProveedorDolarHistorial
from app.schemas.proveedores import ModalidadMasiva, ProveedorCrear
from app.services import proveedores as servicio


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


def _prov(db, admin, nombre, moneda="usd", dolar="1000"):
    datos = {"nombre": nombre, "moneda": moneda}
    if moneda == "usd":
        datos["dolar_actual"] = dolar
    return servicio.crear_proveedor(db, admin, ProveedorCrear(**datos), None)


def _historial(db, proveedor):
    return db.scalars(select(ProveedorDolarHistorial).where(ProveedorDolarHistorial.proveedor_id == proveedor.id)).all()


def test_cambio_individual_registra_historial_y_auditoria(db, admin, monkeypatch):
    recalculados = []
    monkeypatch.setattr(servicio, "_recalcular_precios", lambda db, pid: recalculados.append(pid))
    p = _prov(db, admin, "Importadora")
    servicio.cambiar_dolar(db, admin, p, Decimal("1100.005"), None)
    assert p.dolar_actual == Decimal("1100.01")
    (fila,) = _historial(db, p)
    assert (fila.valor_anterior, fila.valor_nuevo, fila.origen) == (Decimal("1000"), Decimal("1100.01"), OrigenCambioDolar.MANUAL)
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "dolar.cambio", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior == {"dolar_actual": "1000.00"} and registro.estado_nuevo["origen"] == "manual"
    assert recalculados == [p.id]


def test_mismo_valor_no_genera_nada(db, admin, monkeypatch):
    recalculados = []
    monkeypatch.setattr(servicio, "_recalcular_precios", lambda db, pid: recalculados.append(pid))
    p = _prov(db, admin, "Sin cambios")
    servicio.cambiar_dolar(db, admin, p, Decimal("1000.00"), None)
    assert _historial(db, p) == [] and recalculados == []
    assert db.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.accion == "dolar.cambio", Auditoria.entidad_id == p.id)) == 0


def test_dolar_de_proveedor_en_pesos_da_409(db, admin):
    p = _prov(db, admin, "En pesos", moneda="ars")
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.cambiar_dolar(db, admin, p, Decimal("100"), None)
    assert error.value.mensaje == "El proveedor trabaja en pesos: no tiene valor de dólar."


def test_dolar_no_positivo(db, admin):
    p = _prov(db, admin, "Cero")
    with pytest.raises(DatoInvalido):
        servicio.cambiar_dolar(db, admin, p, Decimal("0"), None)


def test_historial_mas_reciente_primero(db, admin):
    p = _prov(db, admin, "Con historial")
    servicio.cambiar_dolar(db, admin, p, Decimal("1100"), None)
    servicio.cambiar_dolar(db, admin, p, Decimal("1200"), None)
    historial = servicio.historial_dolar(db, p.id)
    assert [h["valor_nuevo"] for h in historial] == [Decimal("1200.00"), Decimal("1100.00")]
    assert historial[0]["usuario_nombre"] == admin.nombre


def test_masivo_por_valor_y_porcentaje(db, admin):
    a = _prov(db, admin, "A dólares", dolar="1000")
    b = _prov(db, admin, "B dólares", dolar="1500")
    pesos = _prov(db, admin, "C pesos", moneda="ars")
    inactivo = _prov(db, admin, "D inactivo")
    servicio.cambiar_estado(db, admin, inactivo, EstadoProveedor.DESACTIVADO, False, None)

    vista = servicio.preview_masivo(db, None, ModalidadMasiva.PORCENTAJE, Decimal("10"))
    assert [(v["nombre"], v["valor_nuevo"]) for v in vista] == [("A dólares", Decimal("1100.00")), ("B dólares", Decimal("1650.00"))]
    assert a.dolar_actual == Decimal("1000")  # la vista previa no aplica nada

    servicio.aplicar_masivo(db, admin, [a.id, pesos.id, inactivo.id], ModalidadMasiva.VALOR, Decimal("1300"), None)
    assert a.dolar_actual == Decimal("1300.00") and b.dolar_actual == Decimal("1500")
    assert _historial(db, a)[0].origen is OrigenCambioDolar.MASIVO_VALOR

    with pytest.raises(ReglaDeNegocio):
        servicio.aplicar_masivo(db, admin, [pesos.id, inactivo.id], ModalidadMasiva.VALOR, Decimal("1300"), None)
    with pytest.raises(DatoInvalido):
        servicio.preview_masivo(db, None, ModalidadMasiva.PORCENTAJE, Decimal("-100"))
    with pytest.raises(DatoInvalido):
        servicio.preview_masivo(db, None, ModalidadMasiva.VALOR, Decimal("0"))


def test_plantilla_solo_activos_en_dolares(db, admin):
    a = _prov(db, admin, "Plantilla A", dolar="1000")
    _prov(db, admin, "Plantilla pesos", moneda="ars")
    libro = load_workbook(BytesIO(servicio.generar_plantilla_dolar(db)))
    hoja = libro["Dolar"]
    assert [c.value for c in hoja[1]] == ["proveedor_id", "nombre", "dolar_nuevo"]
    filas = [[c.value for c in fila] for fila in hoja.iter_rows(min_row=2)]
    assert [a.id, "Plantilla A", 1000] in [[f[0], f[1], int(f[2])] for f in filas]
    assert all(f[1] != "Plantilla pesos" for f in filas)
    assert "Instrucciones" in libro.sheetnames


def _xlsx(filas):
    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_importar_todo_o_nada(db, admin):
    a = _prov(db, admin, "Excel A", dolar="1000")
    b = _prov(db, admin, "Excel B", dolar="1000")
    pesos = _prov(db, admin, "Excel pesos", moneda="ars")
    contenido = _xlsx([
        ["proveedor_id", "dolar_nuevo"],
        [a.id, 1100],
        [b.id, "abc"],
        [a.id, 1200],
        [pesos.id, 900],
        [999999, 900],
        ["x", 900],
    ])
    resultado = servicio.importar_dolar(db, admin, contenido, None)
    assert resultado["aplicados"] == 0 and resultado["sin_cambios"] == 0
    assert [e["fila"] for e in resultado["errores"]] == [3, 4, 5, 6, 7]
    assert a.dolar_actual == Decimal("1000")  # no se aplicó nada


def test_importar_aplica_y_cuenta_sin_cambios(db, admin):
    a = _prov(db, admin, "Excel OK A", dolar="1000")
    b = _prov(db, admin, "Excel OK B", dolar="1000")
    resultado = servicio.importar_dolar(db, admin, _xlsx([["dolar_nuevo", "proveedor_id"], ["1.150,50", a.id], [1000, b.id]]), None)
    assert resultado == {"aplicados": 1, "sin_cambios": 1, "errores": []}
    assert a.dolar_actual == Decimal("1150.50")
    assert _historial(db, a)[0].origen is OrigenCambioDolar.IMPORTACION_EXCEL


def test_la_plantilla_se_puede_volver_a_subir_tal_cual(db, admin):
    _prov(db, admin, "Ida y vuelta", dolar="1000")
    resultado = servicio.importar_dolar(db, admin, servicio.generar_plantilla_dolar(db), None)
    assert resultado["errores"] == [] and resultado["aplicados"] == 0
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (funciones inexistentes).

- [ ] **Step 3: Schemas** (agregar a `backend/app/schemas/proveedores.py`; importar `from enum import Enum` y `OrigenCambioDolar`)

```python
class CambioDolar(BaseModel):
    valor_nuevo: Dolar = Field(gt=0, max_digits=10, decimal_places=3)


class ModalidadMasiva(str, Enum):
    VALOR = "valor"          # el mismo valor para todos
    PORCENTAJE = "porcentaje"  # sobre el dólar de cada uno


class CambioMasivo(BaseModel):
    proveedor_ids: list[int] | None = None  # None = todos los activos en dólares
    modalidad: ModalidadMasiva
    valor: Decimal = Field(max_digits=10, decimal_places=3)


class PreviewDolar(BaseModel):
    proveedor_id: int
    nombre: str
    valor_actual: Decimal
    valor_nuevo: Decimal


class HistorialDolarResponse(BaseModel):
    id: int
    valor_anterior: Decimal
    valor_nuevo: Decimal
    origen: OrigenCambioDolar
    timestamp: datetime
    usuario_id: int
    usuario_nombre: str


class ErrorFila(BaseModel):
    fila: int
    error: str


class ResultadoImportacionDolar(BaseModel):
    aplicados: int
    sin_cambios: int
    errores: list[ErrorFila]


class DolarEnUso(BaseModel):
    hay_proveedores_en_dolares: bool
```

- [ ] **Step 4: Service** (agregar a `backend/app/services/proveedores.py`; imports: `from app.core.excel import celda_decimal, celda_entero, generar_plantilla, leer_tabla`, `from app.core.utils import ahora_db`, `from app.models import OrigenCambioDolar, ProveedorDolarHistorial, Usuario`, `from app.schemas.proveedores import ModalidadMasiva`)

```python
ORIGEN_MASIVO = {ModalidadMasiva.VALOR: OrigenCambioDolar.MASIVO_VALOR, ModalidadMasiva.PORCENTAJE: OrigenCambioDolar.MASIVO_PORCENTAJE}
COLUMNAS_PLANTILLA_DOLAR = ["proveedor_id", "nombre", "dolar_nuevo"]
INSTRUCCIONES_DOLAR = [
    ["Instrucciones"],
    ["1. Cambiá solo la columna dolar_nuevo. Las filas que no modifiques se saltean."],
    ["2. No cambies los encabezados ni los proveedor_id."],
    ["3. Todo o nada: si una fila tiene un error, no se aplica ningún cambio y se informan todos los errores."],
    ["4. Solo figuran los proveedores activos que trabajan en dólares."],
]


def _recalcular_precios(db, proveedor_id: int) -> None:
    """Recalcula el precio de venta de los productos del proveedor (módulo 04).
    Import local para no acoplar módulos; sin el módulo de productos, no hace nada."""
    try:
        from app.services.productos import recalcular_precios_de_proveedor
    except ImportError:
        return
    recalcular_precios_de_proveedor(db, proveedor_id)


def _aplicar_cambio_dolar(db, autor, proveedor: Proveedor, valor, origen: OrigenCambioDolar, ip) -> bool:
    """Núcleo ÚNICO de todo cambio de dólar (individual, masivo y Excel).
    Devuelve False si el valor no cambia (no genera historial, auditoría ni recálculo)."""
    if proveedor.moneda is not Moneda.USD:
        raise ReglaDeNegocio("El proveedor trabaja en pesos: no tiene valor de dólar.")
    nuevo = validar_dolar(valor)
    if nuevo == proveedor.dolar_actual:
        return False
    antes = snapshot(proveedor, campos=["dolar_actual"])
    db.add(ProveedorDolarHistorial(
        proveedor_id=proveedor.id, valor_anterior=proveedor.dolar_actual, valor_nuevo=nuevo,
        usuario_id=autor.id, origen=origen, timestamp=ahora_db(),
    ))
    proveedor.dolar_actual = nuevo
    db.flush()
    registrar_auditoria(db, accion="dolar.cambio", entidad="proveedor", entidad_id=proveedor.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo={"dolar_actual": nuevo, "origen": origen.value}, ip_origen=ip)
    _recalcular_precios(db, proveedor.id)
    return True


def cambiar_dolar(db, autor, proveedor: Proveedor, valor, ip) -> Proveedor:
    _aplicar_cambio_dolar(db, autor, proveedor, valor, OrigenCambioDolar.MANUAL, ip)
    return proveedor


def historial_dolar(db, proveedor_id: int) -> list[dict]:
    filas = db.execute(
        select(ProveedorDolarHistorial, Usuario.nombre)
        .join(Usuario, Usuario.id == ProveedorDolarHistorial.usuario_id)
        .where(ProveedorDolarHistorial.proveedor_id == proveedor_id)
        .order_by(ProveedorDolarHistorial.timestamp.desc(), ProveedorDolarHistorial.id.desc())
    ).all()
    return [
        {"id": h.id, "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo, "origen": h.origen,
         "timestamp": h.timestamp, "usuario_id": h.usuario_id, "usuario_nombre": nombre}
        for h, nombre in filas
    ]


def _proveedores_para_masivo(db, proveedor_ids) -> list[Proveedor]:
    """Solo activos en dólares; los ids en pesos o inactivos se ignoran."""
    consulta = select(Proveedor).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO)
    if proveedor_ids is not None:
        consulta = consulta.where(Proveedor.id.in_(proveedor_ids))
    proveedores = list(db.scalars(consulta.order_by(func.lower(Proveedor.nombre), Proveedor.id)).all())
    if not proveedores:
        raise ReglaDeNegocio("No hay proveedores activos en dólares para actualizar.")
    return proveedores


def _valor_masivo(proveedor: Proveedor, modalidad: ModalidadMasiva, valor: Decimal) -> Decimal:
    if modalidad is ModalidadMasiva.VALOR:
        return validar_dolar(valor)
    if valor <= Decimal("-100"):
        raise DatoInvalido("El porcentaje debe ser mayor a -100.")
    return validar_dolar(proveedor.dolar_actual * (1 + Decimal(valor) / 100))


def preview_masivo(db, proveedor_ids, modalidad: ModalidadMasiva, valor: Decimal) -> list[dict]:
    return [
        {"proveedor_id": p.id, "nombre": p.nombre, "valor_actual": p.dolar_actual,
         "valor_nuevo": _valor_masivo(p, modalidad, valor)}
        for p in _proveedores_para_masivo(db, proveedor_ids)
    ]


def aplicar_masivo(db, autor, proveedor_ids, modalidad: ModalidadMasiva, valor: Decimal, ip) -> list[dict]:
    vista = preview_masivo(db, proveedor_ids, modalidad, valor)  # valida todo antes de escribir
    for fila in vista:
        _aplicar_cambio_dolar(db, autor, db.get(Proveedor, fila["proveedor_id"]), fila["valor_nuevo"],
                              ORIGEN_MASIVO[modalidad], ip)
    return vista


def generar_plantilla_dolar(db) -> bytes:
    proveedores = db.scalars(
        select(Proveedor).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO)
        .order_by(func.lower(Proveedor.nombre), Proveedor.id)
    ).all()
    filas = [[p.id, p.nombre, p.dolar_actual] for p in proveedores]
    return generar_plantilla("Dolar", COLUMNAS_PLANTILLA_DOLAR, INSTRUCCIONES_DOLAR, filas)


def _validar_fila_dolar(db, fila: dict, vistos: set) -> tuple[Proveedor, Decimal] | str:
    """(proveedor, valor) si la fila es válida; si no, el mensaje de error."""
    try:
        proveedor_id = celda_entero(fila["proveedor_id"])
    except ValueError:
        proveedor_id = None
    if proveedor_id is None:
        return "proveedor_id vacío o inválido"
    if proveedor_id in vistos:
        return "proveedor_id repetido en el archivo"
    vistos.add(proveedor_id)
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        return "El proveedor no existe"
    if proveedor.estado is not EstadoProveedor.ACTIVO:
        return "El proveedor no está activo"
    if proveedor.moneda is not Moneda.USD:
        return "El proveedor trabaja en pesos"
    try:
        valor = celda_decimal(fila["dolar_nuevo"])
    except ValueError:
        valor = None
    if valor is None or valor <= 0:
        return "dolar_nuevo vacío, inválido o menor o igual a cero"
    return proveedor, valor


def importar_dolar(db, autor, contenido: bytes, ip) -> dict:
    """Todo o nada: primero valida TODAS las filas; si alguna falla, no aplica
    ninguna y devuelve la lista de errores."""
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    errores, validas, vistos = [], [], set()
    for numero, fila in filas:
        resultado = _validar_fila_dolar(db, fila, vistos)
        if isinstance(resultado, str):
            errores.append({"fila": numero, "error": resultado})
        else:
            validas.append(resultado)
    if errores:
        return {"aplicados": 0, "sin_cambios": 0, "errores": errores}
    aplicados = sum(
        1 for proveedor, valor in validas
        if _aplicar_cambio_dolar(db, autor, proveedor, valor, OrigenCambioDolar.IMPORTACION_EXCEL, ip)
    )
    return {"aplicados": aplicados, "sin_cambios": len(validas) - aplicados, "errores": []}
```
Mover `COLUMNAS_PLANTILLA_DOLAR` e `INSTRUCCIONES_DOLAR` al principio del módulo junto a `ACCION_DE_ESTADO`.

- [ ] **Step 5: Correr y ver que pasa** — `test_dolar_service.py`, `test_proveedores_service.py` y la suite completa.

- [ ] **Step 6: Commit** — `feat(proveedores): dólar por proveedor con historial, cambio masivo y Excel`.

---

### Task 6: Endpoints `/api/v1/proveedores`

**Files:**
- Create: `backend/app/api/v1/proveedores.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_proveedores_api.py`

**Interfaces:**
- Consumes: service de proveedores, schemas, `requiere_permiso`, `Modulo`, `Recurso`, `ip_de_request`, `TIPO_XLSX`, `TAMANO_MAXIMO_BYTES`, `ahora`.
- Produces: endpoints del spec, con las rutas `/dolar/...` declaradas antes de `/{proveedor_id}`. Permisos: ver → `PROVEEDORES ver`; alta → `crear`; edición, estado y dólar individual → `editar`; masivo, plantilla e importación → `editar` + recurso `dolar.cambio_masivo`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_proveedores_api.py`:
```python
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.core.excel import TIPO_XLSX

URL = "/api/v1/proveedores"


def _alta(client, h, **datos):
    base = {"nombre": "Proveedor API", "moneda": "ars"}
    base.update(datos)
    return client.post(URL, json=base, headers=h)


def test_permisos(client, crear_usuario, headers_de):
    supervisor = headers_de(crear_usuario("supervisor"))
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=supervisor).status_code == 200      # supervisor: solo ver
    assert _alta(client, supervisor).status_code == 403
    assert client.get(URL, headers=vendedor).status_code == 403
    assert client.get(f"{URL}/dolar/plantilla", headers=supervisor).status_code == 403


def test_alta_edicion_y_ficha(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = _alta(client, h, nombre="Importadora Sur", moneda="usd", dolar_actual="1250.50", pais="China")
    assert r.status_code == 201
    p = r.json()
    assert p["en_dolares"] and p["activo"] and p["dolar_actual"] == "1250.50"
    assert _alta(client, h, nombre="importadora sur").status_code == 409
    assert _alta(client, h, nombre="Sin dólar", moneda="usd").status_code == 400
    r = client.put(f"{URL}/{p['id']}", json={"nombre": "Importadora Sur", "moneda": "usd", "provincia": "Córdoba"}, headers=h)
    assert r.status_code == 200 and r.json()["provincia"] == "Córdoba"
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["nombre"] == "Importadora Sur"
    assert client.get(f"{URL}/999999", headers=h).status_code == 404


def test_listado_con_filtros(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    _alta(client, h, nombre="Córdoba Hilados", provincia="Córdoba")
    _alta(client, h, nombre="Otro", provincia="Salta")
    nombres = [p["nombre"] for p in client.get(URL, params={"provincia": "cordoba"}, headers=h).json()]
    assert nombres == ["Córdoba Hilados"]


def test_estado_y_dolar(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    p = _alta(client, h, nombre="Dólar API", moneda="usd", dolar_actual="1000").json()
    r = client.patch(f"{URL}/{p['id']}/dolar", json={"valor_nuevo": "1100"}, headers=h)
    assert r.status_code == 200 and r.json()["dolar_actual"] == "1100.00"
    historial = client.get(f"{URL}/{p['id']}/dolar/historial", headers=h).json()
    assert historial[0]["valor_nuevo"] == "1100.00" and historial[0]["origen"] == "manual"
    assert client.get(f"{URL}/dolar/en-uso", headers=h).json() == {"hay_proveedores_en_dolares": True}
    r = client.patch(f"{URL}/{p['id']}/estado", json={"estado": "inhabilitado"}, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "inhabilitado"
    assert client.get(f"{URL}/dolar/en-uso", headers=h).json() == {"hay_proveedores_en_dolares": False}


def test_masivo(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    p = _alta(client, h, nombre="Masivo API", moneda="usd", dolar_actual="1000").json()
    cuerpo = {"proveedor_ids": None, "modalidad": "porcentaje", "valor": "10"}
    vista = client.post(f"{URL}/dolar/masivo/preview", json=cuerpo, headers=h).json()
    assert {"proveedor_id": p["id"], "nombre": "Masivo API", "valor_actual": "1000.00", "valor_nuevo": "1100.00"} in vista
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["dolar_actual"] == "1000.00"
    assert client.post(f"{URL}/dolar/masivo", json=cuerpo, headers=h).status_code == 200
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["dolar_actual"] == "1100.00"


def test_plantilla_e_importacion(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    p = _alta(client, h, nombre="Excel API", moneda="usd", dolar_actual="1000").json()
    r = client.get(f"{URL}/dolar/plantilla", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == TIPO_XLSX
    assert "attachment" in r.headers["content-disposition"] and "dolar-proveedores-" in r.headers["content-disposition"]
    libro = load_workbook(BytesIO(r.content))
    hoja = libro["Dolar"]
    fila = next(f for f in hoja.iter_rows(min_row=2) if f[0].value == p["id"])
    fila[2].value = 1234.5
    salida = BytesIO()
    libro.save(salida)
    r = client.post(f"{URL}/dolar/importar", files={"archivo": ("dolar.xlsx", salida.getvalue(), TIPO_XLSX)}, headers=h)
    assert r.status_code == 200 and r.json()["aplicados"] == 1 and r.json()["errores"] == []
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["dolar_actual"] == "1234.50"


def test_importacion_con_errores_no_aplica_nada(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    p = _alta(client, h, nombre="Excel errores", moneda="usd", dolar_actual="1000").json()
    libro = Workbook()
    for fila in (["proveedor_id", "dolar_nuevo"], [p["id"], 1500], [999999, 10]):
        libro.active.append(fila)
    salida = BytesIO()
    libro.save(salida)
    r = client.post(f"{URL}/dolar/importar", files={"archivo": ("dolar.xlsx", salida.getvalue(), TIPO_XLSX)}, headers=h)
    assert r.status_code == 200 and r.json()["aplicados"] == 0
    assert r.json()["errores"] == [{"fila": 3, "error": "El proveedor no existe"}]
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["dolar_actual"] == "1000.00"
    r = client.post(f"{URL}/dolar/importar", files={"archivo": ("x.xlsx", b"basura", TIPO_XLSX)}, headers=h)
    assert r.status_code == 409


def test_no_hay_delete(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    p = _alta(client, h, nombre="Sin delete").json()
    assert client.delete(f"{URL}/{p['id']}", headers=h).status_code == 405
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404).

- [ ] **Step 3: Router**

`backend/app/api/v1/proveedores.py`:
```python
"""Proveedores y valor del dólar. Las rutas /dolar/... van antes de /{proveedor_id}."""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TAMANO_MAXIMO_BYTES, TIPO_XLSX
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_permiso
from app.core.utils import ahora, ip_de_request
from app.models import EstadoProveedor, Moneda, Usuario
from app.schemas.proveedores import (
    CambioDolar,
    CambioMasivo,
    DolarEnUso,
    HistorialDolarResponse,
    PreviewDolar,
    ProveedorCrear,
    ProveedorEditar,
    ProveedorEstado,
    ProveedorResponse,
    ResultadoImportacionDolar,
)
from app.services import proveedores as servicio

router = APIRouter(prefix="/proveedores", tags=["proveedores"])

puede_ver = requiere_permiso(Modulo.PROVEEDORES, "ver")
puede_crear = requiere_permiso(Modulo.PROVEEDORES, "crear")
puede_editar = requiere_permiso(Modulo.PROVEEDORES, "editar")
puede_masivo = requiere_permiso(Modulo.PROVEEDORES, "editar", Recurso.DOLAR_CAMBIO_MASIVO)


@router.get("/dolar/en-uso", response_model=DolarEnUso)
def dolar_en_uso(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return DolarEnUso(hay_proveedores_en_dolares=servicio.hay_proveedores_en_dolares(db))


@router.post("/dolar/masivo/preview", response_model=list[PreviewDolar])
def preview_masivo(datos: CambioMasivo, db: Session = Depends(get_db), _: Usuario = Depends(puede_masivo)):
    return servicio.preview_masivo(db, datos.proveedor_ids, datos.modalidad, datos.valor)


@router.post("/dolar/masivo", response_model=list[PreviewDolar])
def aplicar_masivo(datos: CambioMasivo, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_masivo)):
    aplicados = servicio.aplicar_masivo(db, autor, datos.proveedor_ids, datos.modalidad, datos.valor, ip_de_request(request))
    db.commit()
    return aplicados


@router.get("/dolar/plantilla")
def plantilla(db: Session = Depends(get_db), _: Usuario = Depends(puede_masivo)):
    nombre = f"dolar-proveedores-{ahora().date().isoformat()}.xlsx"
    return Response(
        content=servicio.generar_plantilla_dolar(db), media_type=TIPO_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/dolar/importar", response_model=ResultadoImportacionDolar)
def importar(request: Request, archivo: UploadFile = File(...), db: Session = Depends(get_db),
             autor: Usuario = Depends(puede_masivo)):
    contenido = archivo.file.read(TAMANO_MAXIMO_BYTES + 1)  # el service rechaza lo que pase de 5 MB
    resultado = servicio.importar_dolar(db, autor, contenido, ip_de_request(request))
    if resultado["errores"]:
        db.rollback()
    else:
        db.commit()
    return resultado


@router.get("", response_model=list[ProveedorResponse])
def listar(nombre: str | None = None, email: str | None = None, telefono: str | None = None,
           provincia: str | None = None, pais: str | None = None, estado: EstadoProveedor | None = None,
           moneda: Moneda | None = None, dolar_desde: Decimal | None = None, dolar_hasta: Decimal | None = None,
           db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.listar_proveedores(db, nombre=nombre, email=email, telefono=telefono, provincia=provincia,
                                       pais=pais, estado=estado, moneda=moneda, dolar_desde=dolar_desde,
                                       dolar_hasta=dolar_hasta)


@router.get("/{proveedor_id}", response_model=ProveedorResponse)
def ficha(proveedor_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.obtener_proveedor(db, proveedor_id)


@router.post("", response_model=ProveedorResponse, status_code=201)
def crear(datos: ProveedorCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    proveedor = servicio.crear_proveedor(db, autor, datos, ip_de_request(request))
    db.commit()
    return proveedor


@router.put("/{proveedor_id}", response_model=ProveedorResponse)
def editar(proveedor_id: int, datos: ProveedorEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.editar_proveedor(db, autor, servicio.obtener_proveedor(db, proveedor_id), datos, ip_de_request(request))
    db.commit()
    return proveedor


@router.patch("/{proveedor_id}/estado", response_model=ProveedorResponse)
def cambiar_estado(proveedor_id: int, datos: ProveedorEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.cambiar_estado(db, autor, servicio.obtener_proveedor(db, proveedor_id), datos.estado,
                                        datos.confirmar_con_productos, ip_de_request(request))
    db.commit()
    return proveedor


@router.patch("/{proveedor_id}/dolar", response_model=ProveedorResponse)
def cambiar_dolar(proveedor_id: int, datos: CambioDolar, request: Request, db: Session = Depends(get_db),
                  autor: Usuario = Depends(puede_editar)):
    proveedor = servicio.cambiar_dolar(db, autor, servicio.obtener_proveedor(db, proveedor_id), datos.valor_nuevo,
                                       ip_de_request(request))
    db.commit()
    return proveedor


@router.get("/{proveedor_id}/dolar/historial", response_model=list[HistorialDolarResponse])
def historial(proveedor_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    servicio.obtener_proveedor(db, proveedor_id)
    return servicio.historial_dolar(db, proveedor_id)
```
Incluir `proveedores.router` en `backend/app/api/v1/__init__.py`.

- [ ] **Step 4: Correr y ver que pasa** — el archivo de tests y la suite completa. Curl: `curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/v1/proveedores` → 401.

- [ ] **Step 5: Commit** — `feat(proveedores): API de proveedores y del dólar`.

---

### Task 7: Pantalla de proveedores

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/proveedores/listado.html`, `_modal_ficha.html`, `_modal_form.html`, `_modal_baja.html`, `backend/app/static/js/proveedores.js`
- Test: `backend/tests/test_paginas_proveedores.py`

**Interfaces:**
- Consumes: `requiere_pagina`, `contexto_base`, `_pagina`, `_visible`, `resolver_permiso`, `servicio_proveedores.hay_proveedores_en_dolares`; macros y globales de JS (incluido `formatearDolar`).
- Produces: `SECCION_PROVEEDORES` (primera tarjeta del hub Configuraciones), `PAGINA_DOLAR_MASIVO` (ítem de página, no aparece en el hub: `modulo` PROVEEDORES, `accion` "editar", `recurso` `Recurso.DOLAR_CAMBIO_MASIVO`); ruta `GET /proveedores` (contexto: `usa_dolar`, `puede_crear`, `puede_editar`, `puede_masivo`); componente `proveedoresListado({usaDolar, puedeEditar, esAdmin})`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_paginas_proveedores.py`:
```python
from app.schemas.proveedores import ProveedorCrear
from app.services import proveedores as servicio


def test_hub_muestra_proveedores(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/configuracion").text
    assert 'href="/proveedores"' in html and "Datos de proveedores nacionales e internacionales" in html


def test_admin_sin_proveedores_en_dolares(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/proveedores").text
    assert "proveedoresListado(" in html and "/static/js/proveedores.js?v=" in html
    assert "Crear nuevo" in html and "usaDolar: false" in html
    assert "Cambio masivo del dólar" not in html and "Dólar desde" not in html


def test_admin_con_proveedores_en_dolares(crear_usuario, iniciar_sesion, db):
    admin = crear_usuario("admin")
    servicio.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora", moneda="usd", dolar_actual="1000"), None)
    html = iniciar_sesion(admin).get("/proveedores").text
    assert "usaDolar: true" in html and 'href="/proveedores/dolar-masivo"' in html and "Dólar desde" in html


def test_supervisor_solo_consulta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/proveedores").text
    assert "Crear nuevo" not in html and "puedeEditar: false" in html


def test_vendedor_no_entra(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("vendedor")).get("/proveedores").status_code == 403
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404 / sin tarjeta).

- [ ] **Step 3: Rutas** (en `pages.py`; importar `Recurso` y `from app.services import proveedores as servicio_proveedores`)

```python
SECCION_PROVEEDORES = {
    "nombre": "Proveedores", "descripcion": "Datos de proveedores nacionales e internacionales",
    "url": "/proveedores", "modulo": Modulo.PROVEEDORES,
}
# Página propia sin tarjeta en el hub: se entra desde el listado de proveedores.
PAGINA_DOLAR_MASIVO = {
    "nombre": "Cambio masivo del dólar", "url": "/proveedores/dolar-masivo",
    "modulo": Modulo.PROVEEDORES, "accion": "editar", "recurso": Recurso.DOLAR_CAMBIO_MASIVO,
}
```
y `CONFIGURACION_SECCIONES = [SECCION_PROVEEDORES, SECCION_USUARIOS, SECCION_ROLES]`.

```python
@router.get("/proveedores")
def proveedores(request: Request, db: Session = Depends(get_db),
                usuario: Usuario = Depends(requiere_pagina(SECCION_PROVEEDORES))):
    return _pagina(request, "pages/proveedores/listado.html", contexto_base(
        request, db, "/configuracion", usuario,
        usa_dolar=servicio_proveedores.hay_proveedores_en_dolares(db),
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PROVEEDORES, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PROVEEDORES, "editar"),
        puede_masivo=_visible(PAGINA_DOLAR_MASIVO, usuario, db),
    ))
```

- [ ] **Step 4: Plantillas**

`backend/app/templates/pages/proveedores/listado.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/table.html" import barra_filtros, tabla %}
{% from "components/botones.html" import accion, acciones %}
{% from "components/icons.html" import icono %}
{% block titulo %}Proveedores · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<div x-data="proveedoresListado({ usaDolar: {{ usa_dolar|js }}, puedeEditar: {{ puede_editar|js }}, esAdmin: {{ es_admin|js }} })">
  {% call encabezado("Proveedores", "/configuracion", "Configuraciones") %}
    {% if usa_dolar and puede_masivo %}
    <a href="/proveedores/dolar-masivo" class="boton boton-secundario">Cambio masivo del dólar</a>
    {% endif %}
    {% if puede_crear %}
    <button type="button" class="boton boton-acento" @click="nuevo()">{{ icono("mas", "w-4 h-4") }}<span>Crear nuevo</span></button>
    {% endif %}
  {% endcall %}

  {% call barra_filtros(etiqueta="proveedores encontrados") %}
    <input type="search" class="campo" placeholder="Nombre" aria-label="Filtrar por nombre" x-model="filtros.nombre" @input="filtrar()">
    <input type="search" class="campo" placeholder="País" aria-label="Filtrar por país" x-model="filtros.pais" @input="filtrar()">
    <input type="search" class="campo" placeholder="Provincia" aria-label="Filtrar por provincia" x-model="filtros.provincia" @input="filtrar()">
    <select class="campo" aria-label="Estado" x-model="filtros.estado" @change="cargar()">
      <option value="">Estado (todos)</option>
      <option value="activo">Activo</option>
      <option value="desactivado">Desactivado</option>
      <option value="inhabilitado">Inhabilitado</option>
    </select>
    <select class="campo" aria-label="Moneda" x-model="filtros.moneda" @change="cargar()">
      <option value="">Moneda (todas)</option>
      <option value="ars">Pesos</option>
      <option value="usd">Dólares</option>
    </select>
    {% if usa_dolar %}
    <input type="number" min="0" step="0.01" inputmode="decimal" class="campo" placeholder="Dólar desde" aria-label="Dólar desde" x-model="filtros.dolar_desde" @input="filtrar()">
    <input type="number" min="0" step="0.01" inputmode="decimal" class="campo" placeholder="Dólar hasta" aria-label="Dólar hasta" x-model="filtros.dolar_hasta" @input="filtrar()">
    {% endif %}
  {% endcall %}

  {% set columnas = [
    {"titulo": "Nombre", "expr": "fila.nombre"},
    {"titulo": "Contacto", "expr": "celdaContacto(fila)", "html": True},
    {"titulo": "Provincia", "expr": "fila.provincia || '—'"},
    {"titulo": "País", "expr": "fila.pais || '—'"},
    {"titulo": "Moneda", "expr": "monedaTexto(fila)"},
  ] %}
  {% if usa_dolar %}
    {% set columnas = columnas + [{"titulo": "Dólar", "expr": "dolarTexto(fila)", "clase": "text-right whitespace-nowrap"}] %}
  {% endif %}
  {% set columnas = columnas + [{"titulo": "Estado", "expr": "celdaEstado(fila)", "html": True}] %}
  {% call tabla(columnas, cargando="cargando", vacio="No hay proveedores con esos filtros.") %}
    {% call acciones() %}
      {{ accion("ver", atributos='@click="ver(fila)"') }}
      {{ accion("editar", atributos='x-show="puedeEditar" @click="editar(fila)"') }}
      {{ accion("borrar", texto="Dar de baja", atributos='x-show="puedeEditar && fila.estado === \'activo\'" @click="abrirBaja(fila)"') }}
      {{ accion("activar", texto="Reactivar", atributos='x-show="puedeReactivar(fila)" @click="reactivar(fila)"') }}
    {% endcall %}
  {% endcall %}

  {% include "pages/proveedores/_modal_ficha.html" %}
  {% include "pages/proveedores/_modal_form.html" %}
  {% include "pages/proveedores/_modal_baja.html" %}
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/proveedores.js') }}"></script>{% endblock %}
```
Nota: dentro de `atributos='...'` las comillas simples de `'activo'` van escapadas (`\'activo\'`) porque el string Jinja está delimitado con comillas simples.

`backend/app/templates/pages/proveedores/_modal_ficha.html`:
```jinja
{% from "components/modal.html" import modal %}
{% call modal("Proveedor", "modal-proveedor-ficha", abierto="fichaAbierta", titulo_expr="ficha ? ficha.nombre : ''") %}
<template x-if="ficha">
  <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    <div><dt class="text-sm text-texto-muted">País</dt><dd class="text-texto" x-text="ficha.pais || '—'"></dd></div>
    <div><dt class="text-sm text-texto-muted">Provincia</dt><dd class="text-texto" x-text="ficha.provincia || '—'"></dd></div>
    <div><dt class="text-sm text-texto-muted">Teléfono</dt><dd class="text-texto" x-text="ficha.telefono || '—'"></dd></div>
    <div><dt class="text-sm text-texto-muted">Email</dt><dd class="break-all text-texto" x-text="ficha.email || '—'"></dd></div>
    <div><dt class="text-sm text-texto-muted">Moneda</dt><dd class="text-texto" x-text="monedaTexto(ficha)"></dd></div>
    <div x-show="ficha.en_dolares"><dt class="text-sm text-texto-muted">Valor actual del dólar</dt><dd class="text-texto" x-text="dolarTexto(ficha)"></dd></div>
    <div><dt class="text-sm text-texto-muted">Estado</dt><dd x-html="celdaEstado(ficha)"></dd></div>
    <div class="sm:col-span-2"><dt class="text-sm text-texto-muted">Notas</dt><dd class="whitespace-pre-line text-texto" x-text="ficha.notas || '—'"></dd></div>
  </dl>
</template>
{% endcall %}
```

`backend/app/templates/pages/proveedores/_modal_form.html`:
```jinja
{% from "components/modal.html" import modal %}
{% from "components/form_field.html" import campo %}
{% call modal("Proveedor", "modal-proveedor-form", abierto="formAbierto", titulo_expr="form.id ? 'Editar proveedor' : 'Nuevo proveedor'") %}
<form @submit.prevent="guardar()" class="flex flex-col gap-6" novalidate>
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    {{ campo("p-nombre", "Nombre", modelo="form.nombre", requerido=True, error="errores.nombre") }}
    {{ campo("p-pais", "País", modelo="form.pais", error="errores.pais") }}
    {{ campo("p-provincia", "Provincia", modelo="form.provincia", error="errores.provincia") }}
    {{ campo("p-telefono", "Teléfono", tipo="tel", modelo="form.telefono", error="errores.telefono") }}
    {{ campo("p-email", "Email", tipo="email", modelo="form.email", error="errores.email") }}
    <div class="flex flex-col gap-1 sm:col-span-2">
      <label for="p-notas" class="text-lg font-medium text-texto">Notas</label>
      <textarea id="p-notas" rows="3" class="campo" x-model="form.notas"></textarea>
    </div>
  </div>

  <fieldset class="flex flex-col gap-2">
    <legend class="text-lg font-medium text-texto">Moneda <span class="text-danger">*</span></legend>
    <div class="flex flex-wrap gap-4">
      <label class="inline-flex min-h-toque cursor-pointer items-center gap-2"><input type="radio" class="acceso-check" value="ars" x-model="form.moneda"><span>Pesos</span></label>
      <label class="inline-flex min-h-toque cursor-pointer items-center gap-2"><input type="radio" class="acceso-check" value="usd" x-model="form.moneda"><span>Dólares</span></label>
    </div>
    <p class="text-sm text-texto-muted" x-show="form.id">La moneda solo se puede cambiar si el proveedor no tiene productos cargados.</p>
  </fieldset>

  <div x-show="pideDolarInicial()" x-cloak>
    {{ campo("p-dolar", "Valor actual del dólar", tipo="number", modelo="form.dolar_actual", requerido=True, error="errores.dolar_actual", ayuda="Debe ser mayor a cero.", atributos='min="0.01" step="0.01" inputmode="decimal"') }}
  </div>

  <template x-if="form.id && form.monedaOriginal === 'usd'">
    <section class="flex flex-col gap-3 rounded-input border border-borde p-4">
      <h3 class="font-semibold text-texto-header">Dólar de este proveedor</h3>
      <p class="text-texto">Actual: <span class="font-semibold" x-text="'US$ ' + formatearDolar(form.dolar_actual)"></span></p>
      <div class="flex flex-wrap items-end gap-2">
        <label class="flex flex-col gap-1 text-sm text-texto-muted">Nuevo
          <input type="number" min="0.01" step="0.01" inputmode="decimal" class="campo w-40" x-model="dolarNuevo"></label>
        <button type="button" class="boton boton-secundario" :disabled="!dolarNuevo || aplicandoDolar" @click="aplicarDolar()"
                x-text="aplicandoDolar ? 'Aplicando…' : 'Aplicar'"></button>
      </div>
      <h4 class="text-sm font-semibold text-texto-muted">Historial del dólar</h4>
      <div class="overflow-x-auto">
        <table class="tabla">
          <thead><tr><th scope="col">Fecha</th><th scope="col" class="text-right">Anterior</th><th scope="col" class="text-right">Nuevo</th><th scope="col">Origen</th></tr></thead>
          <tbody>
            <template x-for="h in historial" :key="h.id">
              <tr>
                <td x-text="fechaHora(h.timestamp)"></td>
                <td class="text-right" x-text="'US$ ' + formatearDolar(h.valor_anterior)"></td>
                <td class="text-right" x-text="'US$ ' + formatearDolar(h.valor_nuevo)"></td>
                <td x-text="origenTexto(h.origen)"></td>
              </tr>
            </template>
            <tr x-show="!historial.length"><td colspan="4" class="py-4 text-center text-texto-muted">Sin cambios registrados.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <div class="flex justify-end">
    <button type="submit" class="boton boton-primario" :disabled="guardando"
            x-text="guardando ? 'Guardando…' : (form.id ? 'Finalizar' : 'Crear')"></button>
  </div>
</form>
{% endcall %}
```

`backend/app/templates/pages/proveedores/_modal_baja.html`:
```jinja
{% from "components/modal.html" import modal %}
{% call modal("Dar de baja", "modal-proveedor-baja", abierto="bajaAbierta", ancho="max-w-lg", titulo_expr="baja ? 'Dar de baja a ' + baja.proveedor.nombre : ''") %}
<template x-if="baja">
  <div class="flex flex-col gap-4">
    <label class="flex cursor-pointer items-start gap-3">
      <input type="radio" class="acceso-check mt-1" value="desactivado" x-model="baja.estado" @change="baja.advertencia = ''">
      <span><span class="font-semibold text-texto">Desactivar</span><br><span class="text-sm text-texto-muted">Se puede reactivar libremente.</span></span>
    </label>
    <label class="flex cursor-pointer items-start gap-3">
      <input type="radio" class="acceso-check mt-1" value="inhabilitado" x-model="baja.estado" @change="baja.advertencia = ''">
      <span><span class="font-semibold text-texto">Inhabilitar</span><br><span class="text-sm text-texto-muted">Solo Admin puede reactivarlo.</span></span>
    </label>
    <p class="rounded-input bg-danger/10 p-3 text-sm text-danger" x-show="baja.advertencia" x-text="baja.advertencia"></p>
    <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <button type="button" class="boton boton-secundario" @click="bajaAbierta = false">Cancelar</button>
      <button type="button" class="boton boton-peligro" x-show="!baja.advertencia" :disabled="dandoDeBaja" @click="confirmarBaja(false)"
              x-text="dandoDeBaja ? 'Guardando…' : 'Confirmar baja'"></button>
      <button type="button" class="boton boton-peligro" x-show="baja.advertencia" x-cloak :disabled="dandoDeBaja" @click="confirmarBaja(true)">Dar de baja igual</button>
    </div>
  </div>
</template>
{% endcall %}
```

- [ ] **Step 5: `static/js/proveedores.js`**

```js
/* Proveedores: listado con filtros, ficha, alta/edición (moneda y dólar
   propio con historial) y baja lógica. Todos los datos salen de la API. */
(function () {
  'use strict';

  const API = '/api/v1/proveedores';
  const ESTADOS = {
    activo: ['Activo', 'exito'],
    desactivado: ['Desactivado', 'neutro'],
    inhabilitado: ['Inhabilitado', 'peligro'],
  };
  const ORIGENES = {
    manual: 'Manual',
    masivo_valor: 'Masivo (valor)',
    masivo_porcentaje: 'Masivo (%)',
    importacion_excel: 'Excel',
  };
  const filtrosVacios = () => ({ nombre: '', pais: '', provincia: '', estado: '', moneda: '', dolar_desde: '', dolar_hasta: '' });
  const formVacio = () => ({
    id: null, nombre: '', pais: '', provincia: '', telefono: '', email: '', notas: '',
    moneda: 'ars', monedaOriginal: null, dolar_actual: '',
  });
  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.proveedoresListado = function ({ usaDolar, puedeEditar, esAdmin }) {
    return {
      usaDolar,
      puedeEditar,
      filtros: filtrosVacios(),
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,
      ficha: null,
      fichaAbierta: false,
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,
      historial: [],
      dolarNuevo: '',
      aplicandoDolar: false,
      baja: null,
      bajaAbierta: false,
      dandoDeBaja: false,

      get total() {
        return this.filas.length;
      },

      init() {
        this.cargar();
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargar(), 400);
      },

      limpiarFiltros() {
        this.filtros = filtrosVacios();
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        for (const [clave, valor] of Object.entries(this.filtros)) {
          const limpio = String(valor ?? '').trim();
          if (limpio) params.set(clave, limpio);
        }
        try {
          const filas = await this._ultima(window.pedir(`${API}?${params}`));
          if (filas === undefined) return;  // llegó una respuesta más nueva
          this.filas = filas;
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      celdaContacto(p) {
        const partes = [p.email, p.telefono].filter(Boolean).map((v) => window.escaparHtml(v));
        return partes.length ? partes.join('<br>') : '—';
      },

      celdaEstado(p) {
        const [texto, variante] = ESTADOS[p.estado] || [p.estado, 'neutro'];
        return window.estadoHtml(texto, variante);
      },

      monedaTexto(p) {
        return p.moneda === 'usd' ? 'Dólares' : 'Pesos';
      },

      dolarTexto(p) {
        return p.moneda === 'usd' ? `US$ ${window.formatearDolar(p.dolar_actual)}` : '—';
      },

      origenTexto(origen) {
        return ORIGENES[origen] || origen;
      },

      // Solo oculta botones: la API vuelve a validar todo.
      puedeReactivar(p) {
        return puedeEditar && p.estado !== 'activo' && (esAdmin || p.estado === 'desactivado');
      },

      ver(p) {
        this.ficha = p;
        this.fichaAbierta = true;
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.historial = [];
        this.dolarNuevo = '';
        this.formAbierto = true;
      },

      async editar(p) {
        this.form = {
          id: p.id, nombre: p.nombre, pais: p.pais || '', provincia: p.provincia || '', telefono: p.telefono || '',
          email: p.email || '', notas: p.notas || '', moneda: p.moneda, monedaOriginal: p.moneda,
          dolar_actual: p.dolar_actual || '',
        };
        this.errores = {};
        this.historial = [];
        this.dolarNuevo = '';
        this.formAbierto = true;
        if (p.moneda === 'usd') await this.cargarHistorial();
      },

      async cargarHistorial() {
        try {
          this.historial = await window.pedir(`${API}/${this.form.id}/dolar/historial`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // El dólar se pide en el alta en dólares o al pasar un proveedor de pesos a dólares.
      pideDolarInicial() {
        return this.form.moneda === 'usd' && this.form.monedaOriginal !== 'usd';
      },

      _cuerpo() {
        const cuerpo = {
          nombre: this.form.nombre,
          pais: textoONull(this.form.pais),
          provincia: textoONull(this.form.provincia),
          telefono: textoONull(this.form.telefono),
          email: textoONull(this.form.email),
          notas: textoONull(this.form.notas),
          moneda: this.form.moneda,
        };
        if (this.pideDolarInicial()) cuerpo.dolar_actual = textoONull(this.form.dolar_actual);
        return cuerpo;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const proveedor = await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this._cuerpo(),
          });
          window.toast(esAlta ? 'Proveedor creado.' : 'Cambios guardados.');
          this.formAbierto = false;
          // El primer proveedor en dólares hace aparecer los controles del dólar.
          if (proveedor.en_dolares && !this.usaDolar) {
            window.location.reload();
            return;
          }
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async aplicarDolar() {
        this.aplicandoDolar = true;
        try {
          const proveedor = await window.pedir(`${API}/${this.form.id}/dolar`, {
            method: 'PATCH',
            body: { valor_nuevo: this.dolarNuevo },
          });
          this.form.dolar_actual = proveedor.dolar_actual;
          this.dolarNuevo = '';
          window.toast('Dólar actualizado. Los precios de sus productos se recalculan con el valor nuevo.');
          await this.cargarHistorial();
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.aplicandoDolar = false;
        }
      },

      abrirBaja(p) {
        this.baja = { proveedor: p, estado: 'desactivado', advertencia: '' };
        this.bajaAbierta = true;
      },

      async confirmarBaja(confirmarConProductos) {
        this.dandoDeBaja = true;
        try {
          await window.pedir(`${API}/${this.baja.proveedor.id}/estado`, {
            method: 'PATCH',
            body: { estado: this.baja.estado, confirmar_con_productos: confirmarConProductos },
          });
          window.toast(this.baja.estado === 'inhabilitado' ? 'Proveedor inhabilitado.' : 'Proveedor desactivado.');
          this.bajaAbierta = false;
          this.cargar();
        } catch (e) {
          // 409 por productos activos: se muestra y se ofrece dar de baja igual.
          if (e.status === 409 && !confirmarConProductos) this.baja.advertencia = e.message;
          else window.toast(e.message, 'error');
        } finally {
          this.dandoDeBaja = false;
        }
      },

      async reactivar(p) {
        const ok = await window.confirmar({
          titulo: `¿Reactivar a ${p.nombre}?`,
          mensaje: 'Va a volver a estar disponible para cargar productos.',
          textoConfirmar: 'Reactivar',
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${p.id}/estado`, {
            method: 'PATCH',
            body: { estado: 'activo', confirmar_con_productos: false },
          });
          window.toast('Proveedor reactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
```

- [ ] **Step 6: Correr y ver que pasa** — `docker compose exec -T backend pytest tests/test_paginas_proveedores.py -v`, `node --check backend/app/static/js/proveedores.js`, suite completa.

- [ ] **Step 7: Commit** — `feat(proveedores): pantalla de proveedores`.

---

### Task 8: Pantalla de cambio masivo del dólar

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/proveedores/dolar_masivo.html`, `backend/app/static/js/dolar_masivo.js`
- Test: `backend/tests/test_paginas_proveedores.py` (agregar)

**Interfaces:**
- Consumes: `PAGINA_DOLAR_MASIVO`, `requiere_pagina`, `servicio_proveedores.hay_proveedores_en_dolares`; API `GET /api/v1/proveedores?moneda=usd&estado=activo`, `POST /dolar/masivo/preview`, `POST /dolar/masivo`, `GET /dolar/plantilla`, `POST /dolar/importar` (multipart `archivo`).
- Produces: ruta `GET /proveedores/dolar-masivo` (contexto `usa_dolar`); componente `dolarMasivo()`.

- [ ] **Step 1: Tests que fallan** (agregar a `backend/tests/test_paginas_proveedores.py`)

```python
def test_dolar_masivo_sin_proveedores_en_dolares(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/proveedores/dolar-masivo").text
    assert "No hay proveedores que trabajen en dólares." in html and "dolarMasivo()" not in html


def test_dolar_masivo_con_proveedores(crear_usuario, iniciar_sesion, db):
    admin = crear_usuario("admin")
    servicio.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora", moneda="usd", dolar_actual="1000"), None)
    html = iniciar_sesion(admin).get("/proveedores/dolar-masivo").text
    assert 'x-data="dolarMasivo()"' in html and "/static/js/dolar_masivo.js?v=" in html
    assert 'href="/api/v1/proveedores/dolar/plantilla"' in html and "Vista previa" in html
    assert 'href="/proveedores"' in html  # volver


def test_supervisor_no_entra_al_masivo(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("supervisor")).get("/proveedores/dolar-masivo").status_code == 403
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404).

- [ ] **Step 3: Ruta**

```python
@router.get("/proveedores/dolar-masivo")
def dolar_masivo(request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_pagina(PAGINA_DOLAR_MASIVO))):
    return _pagina(request, "pages/proveedores/dolar_masivo.html", contexto_base(
        request, db, "/configuracion", usuario, usa_dolar=servicio_proveedores.hay_proveedores_en_dolares(db),
    ))
```

- [ ] **Step 4: Plantilla**

`backend/app/templates/pages/proveedores/dolar_masivo.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% block titulo %}Cambio masivo del dólar · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Cambio masivo del dólar", "/proveedores", "Proveedores") }}
{% if not usa_dolar %}
<div class="tarjeta flex flex-col items-start gap-4">
  <p class="text-texto">No hay proveedores que trabajen en dólares.</p>
  <a href="/proveedores" class="boton boton-secundario">Volver a Proveedores</a>
</div>
{% else %}
<div x-data="dolarMasivo()" class="grid grid-cols-1 gap-6 xl:grid-cols-2">
  <section class="tarjeta flex flex-col gap-4">
    <h2 class="text-xl font-bold text-texto-header">Por valor o porcentaje</h2>
    <fieldset class="flex flex-col gap-2">
      <legend class="font-semibold text-texto">Proveedores en dólares</legend>
      <label class="inline-flex min-h-toque cursor-pointer items-center gap-2">
        <input type="checkbox" class="acceso-check" :checked="todos" @change="alternarTodos()">
        <span>Todos</span>
      </label>
      <ul class="flex max-h-64 flex-col gap-1 overflow-y-auto pl-2">
        <template x-for="p in proveedores" :key="p.id">
          <li>
            <label class="inline-flex min-h-toque cursor-pointer items-center gap-2">
              <input type="checkbox" class="acceso-check" :value="p.id" x-model.number="seleccion" @change="vista = []">
              <span x-text="p.nombre"></span>
              <span class="text-sm text-texto-muted" x-text="'US$ ' + formatearDolar(p.dolar_actual)"></span>
            </label>
          </li>
        </template>
      </ul>
      <p class="text-sm text-texto-muted" x-show="cargando">Cargando…</p>
    </fieldset>
    <fieldset class="flex flex-wrap gap-4">
      <legend class="sr-only">Modalidad</legend>
      <label class="inline-flex min-h-toque cursor-pointer items-center gap-2"><input type="radio" class="acceso-check" value="valor" x-model="modalidad" @change="vista = []"><span>Valor fijo</span></label>
      <label class="inline-flex min-h-toque cursor-pointer items-center gap-2"><input type="radio" class="acceso-check" value="porcentaje" x-model="modalidad" @change="vista = []"><span>Porcentaje</span></label>
    </fieldset>
    <label class="flex flex-col gap-1 text-lg font-medium text-texto">
      <span x-text="modalidad === 'valor' ? 'Nuevo valor del dólar' : 'Porcentaje (+/−)'"></span>
      <input type="number" step="0.01" inputmode="decimal" class="campo max-w-xs" x-model="valor" @input="vista = []"
             :placeholder="modalidad === 'valor' ? '1300' : '5 o -3'">
    </label>
    <div class="flex flex-wrap gap-2">
      <button type="button" class="boton boton-secundario" :disabled="calculando || !valor" @click="previsualizar()"
              x-text="calculando ? 'Calculando…' : 'Vista previa'">Vista previa</button>
      <button type="button" class="boton boton-primario" x-show="vista.length" x-cloak :disabled="aplicando" @click="aplicar()"
              x-text="aplicando ? 'Aplicando…' : 'Aplicar cambio'"></button>
    </div>
    <div class="overflow-x-auto" x-show="vista.length" x-cloak>
      <table class="tabla">
        <thead><tr><th scope="col">Proveedor</th><th scope="col" class="text-right">Actual</th><th scope="col" class="text-right">Nuevo</th></tr></thead>
        <tbody>
          <template x-for="fila in vista" :key="fila.proveedor_id">
            <tr>
              <td x-text="fila.nombre"></td>
              <td class="text-right" x-text="'US$ ' + formatearDolar(fila.valor_actual)"></td>
              <td class="text-right font-semibold" x-text="'US$ ' + formatearDolar(fila.valor_nuevo)"></td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta flex flex-col gap-4">
    <h2 class="text-xl font-bold text-texto-header">Importar desde Excel</h2>
    <ol class="list-decimal pl-5 text-sm text-texto-muted">
      <li>Descargá el Excel con los proveedores en dólares.</li>
      <li>Cambiá la columna <code>dolar_nuevo</code> (no toques <code>proveedor_id</code> ni los encabezados).</li>
      <li>Subilo. Si alguna fila tiene un error, no se aplica nada y te mostramos cuáles corregir.</li>
    </ol>
    <a href="/api/v1/proveedores/dolar/plantilla" class="boton boton-secundario self-start" download>Descargar Excel</a>
    <label class="flex flex-col gap-1 text-lg font-medium text-texto">Archivo (.xlsx)
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" class="campo py-2" @change="elegirArchivo($event)">
    </label>
    <button type="button" class="boton boton-primario self-start" :disabled="!archivo || subiendo" @click="subir()"
            x-text="subiendo ? 'Subiendo…' : 'Subir y aplicar'">Subir y aplicar</button>
    <template x-if="resultado">
      <div class="flex flex-col gap-3">
        <p class="text-texto" x-show="!resultado.errores.length">
          Aplicados: <span class="font-semibold" x-text="resultado.aplicados"></span> ·
          Sin cambios: <span class="font-semibold" x-text="resultado.sin_cambios"></span>
        </p>
        <div x-show="resultado.errores.length">
          <p class="mb-2 font-semibold text-danger">Errores encontrados (no se aplicó nada):</p>
          <div class="overflow-x-auto">
            <table class="tabla">
              <thead><tr><th scope="col" class="text-right">Fila</th><th scope="col">Error</th></tr></thead>
              <tbody>
                <template x-for="e in resultado.errores" :key="e.fila">
                  <tr><td class="text-right" x-text="e.fila"></td><td x-text="e.error"></td></tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </section>
</div>
{% endif %}
{% endblock %}
{% block scripts %}{% if usa_dolar %}<script src="{{ estatico('/js/dolar_masivo.js') }}"></script>{% endif %}{% endblock %}
```

- [ ] **Step 5: `static/js/dolar_masivo.js`**

```js
/* Cambio masivo del dólar: por valor o porcentaje (con vista previa y
   confirmación) o importando el Excel de proveedores en dólares. */
(function () {
  'use strict';

  const API = '/api/v1/proveedores';

  window.dolarMasivo = function () {
    return {
      proveedores: [],
      seleccion: [],
      modalidad: 'valor',
      valor: '',
      vista: [],
      cargando: true,
      calculando: false,
      aplicando: false,
      archivo: null,
      subiendo: false,
      resultado: null,

      init() {
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        try {
          this.proveedores = await window.pedir(`${API}?moneda=usd&estado=activo`);
          this.seleccion = this.proveedores.map((p) => p.id);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      get todos() {
        return this.proveedores.length > 0 && this.seleccion.length === this.proveedores.length;
      },

      alternarTodos() {
        this.seleccion = this.todos ? [] : this.proveedores.map((p) => p.id);
        this.vista = [];
      },

      _cuerpo() {
        return { proveedor_ids: this.todos ? null : this.seleccion, modalidad: this.modalidad, valor: this.valor };
      },

      async previsualizar() {
        if (!this.seleccion.length) return window.toast('Elegí al menos un proveedor.', 'error');
        this.calculando = true;
        try {
          this.vista = await window.pedir(`${API}/dolar/masivo/preview`, { method: 'POST', body: this._cuerpo() });
        } catch (e) {
          this.vista = [];
          window.toast(e.message, 'error');
        } finally {
          this.calculando = false;
        }
      },

      async aplicar() {
        const ok = await window.confirmar({
          titulo: '¿Aplicar el cambio del dólar?',
          mensaje: `Se actualiza el dólar de ${this.vista.length} proveedor(es) y se recalculan los precios de sus productos.`,
          textoConfirmar: 'Aplicar',
        });
        if (!ok) return;
        this.aplicando = true;
        try {
          await window.pedir(`${API}/dolar/masivo`, { method: 'POST', body: this._cuerpo() });
          window.toast('Dólar actualizado.');
          this.vista = [];
          this.valor = '';
          await this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.aplicando = false;
        }
      },

      elegirArchivo(evento) {
        this.archivo = evento.target.files[0] || null;
        this.resultado = null;
      },

      async subir() {
        if (!this.archivo) return window.toast('Elegí un archivo .xlsx.', 'error');
        const datos = new FormData();
        datos.append('archivo', this.archivo);
        this.subiendo = true;
        try {
          this.resultado = await window.pedir(`${API}/dolar/importar`, { method: 'POST', body: datos });
          if (!this.resultado.errores.length) {
            window.toast(`Listo: ${this.resultado.aplicados} actualizado(s), ${this.resultado.sin_cambios} sin cambios.`);
            await this.cargar();
          }
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.subiendo = false;
        }
      },
    };
  };
})();
```

- [ ] **Step 6: Verificación final**

```bash
docker compose exec -T backend pytest -p no:warnings
for f in app usuarios proveedores dolar_masivo; do node --check backend/app/static/js/$f.js; done
node --test backend/tests_js/
```
Checklist manual (navegador, pendiente para el usuario): crear un proveedor en pesos y uno en dólares (aparecen los controles del dólar), cambiar el dólar desde la edición y ver el historial, dar de baja con "Desactivar" e "Inhabilitar", cambio masivo por porcentaje con vista previa, descargar el Excel, modificarlo y subirlo, subir un Excel con un error y ver la tabla de errores.

- [ ] **Step 7: Commit** — `feat(proveedores): pantalla de cambio masivo del dólar`.
