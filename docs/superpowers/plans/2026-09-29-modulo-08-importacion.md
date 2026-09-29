# Módulo 08 — Importación desde Excel: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carga inicial de proveedores, clientes y productos desde Excel: plantilla descargable, validación (vista previa sin tocar la base) e importación todo-o-nada, pasando cada alta por el service dueño.

**Architecture:** Un único motor en `services/importacion.py` (`_procesar`) parametrizado por una `Definicion` por tipo (columnas + parser por columna + función de alta + claves de duplicado). Todo corre dentro de un SAVEPOINT exterior con un SAVEPOINT por fila; validar y aplicar usan el mismo camino y solo difieren en si al final se confirma o se revierte el savepoint exterior. API en `/api/v1/importacion/{tipo}/…`; pantalla Jinja + un componente Alpine.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL 15, openpyxl, Pydantic 2, Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/08_importacion.md` + `CLAUDE.md` + `docs/pendientes.md` (nota del zip bomb en "Módulo 03: pendientes"). Donde este plan y el spec difieran, manda la sección "Decisiones y desvíos" de este plan.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `modulo-08-importacion` (creada desde `dev` en la Task 1). UN commit por tarea: `feat(importacion): …` + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout de otra rama. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo:** verificar con tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest -p no:warnings`, suite completa antes de cada commit). JS: `node --check` y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores `DatoInvalido` 400 / `SinPermiso` 403 / `NoEncontrado` 404 / `ReglaDeNegocio` 409; auditoría con `registrar_auditoria`. Routers hacen `db.commit()` / `db.rollback()`.
- Dinero: siempre `Decimal`, nunca `float`. Nunca un 500 por datos del usuario (un valor enorme o mal formado es un error de fila, no una excepción de la base).
- La API devuelve datos crudos (Principio 1). Excepción: `errores[].error` es un mensaje para leer (como el `detail` de cualquier error).
- **La importación no tiene reglas de negocio propias duplicadas:** toda regla del alta (unicidad, dígito del CUIT, dólar > 0, descuento máximo, niveles de categoría, precio) la aplica el service dueño. El motor solo parsea celdas, detecta repetidos dentro del archivo y resuelve nombres → ids.
- Pantallas: `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; sin `x-html` con datos de la API; escrituras con `pedir()`; `confirmar()` antes de importar; reusar macros de `templates/components/`; mobile-first, `min-h-toque`, tablas en `overflow-x-auto`.

## Decisiones y desvíos

Decisiones de producto tomadas con el usuario al inicio del módulo:

1. **Permisos: alcanza con `IMPORTACION crear`.** Quien puede importar puede dar de alta proveedores, clientes, productos y categorías y cargar stock inicial por esta vía, aunque no tenga el `crear` de esos módulos (es la herramienta de puesta en marcha; por defecto solo Admin). Por eso el motor NO le pasa `stock_inicial` a `crear_producto` (que exige `STOCK crear`): crea el producto con stock 0 y después llama a `services.stock.registrar_ingreso(..., "Importación inicial", ...)`. `registrar_ingreso`, `definir_minimo` y `crear_categoria` no chequean permisos adentro (lo hace el router de cada módulo), así que no hay que duplicar ni saltear ninguna regla.
2. **Código del sistema anterior → `sku_proveedor`.** Sin cambios de modelo: el SKU propio se genera como en el alta manual; la instrucción de la columna `sku_proveedor` en la plantilla lo aclara.

Desvíos técnicos:

3. **Firmas con `db`, `autor` e `ip`:** `validar(db, autor, tipo, contenido, archivo)` e `importar(db, autor, tipo, contenido, archivo, ip)`. `validar` también necesita `autor` porque los services auditan con `autor.id` (esos registros se revierten con el savepoint).
4. **Único rastro de `validar`: las secuencias.** `nextval` (ids y `productos_sku_seq`) no se revierte con el rollback, así que validar puede dejar huecos en los SKU. Es inofensivo y queda comentado en el código. No quedan filas, ni auditoría, ni categorías.
5. **Errores por fila:** en la etapa de parseo se informan TODAS las columnas con error de la fila; los errores del schema Pydantic también (todos los que junte Pydantic); en la etapa de alta, el primero que levante el service. `columna` es `null` cuando el service no permite ubicar la columna (ej. "Ya existe un producto con esa descripción…").
6. **Mensajes de Pydantic en español:** el motor traduce los `type` de error más comunes (`string_too_long`, `greater_than`, `decimal_max_places`, …) con `_mensaje_pydantic`; el resto sale como "Dato inválido" (el API no los traduce en ningún otro lado y la importación los muestra al usuario).
7. **Etiquetas de enums en un solo lugar:** `TEMPORADAS` y `CONDICIONES_IVA` se mudan de `app/api/pages.py` a `app/core/etiquetas.py` (junto con la nueva `MONEDAS`); `pages.py` las importa de ahí. Las usan la pantalla (selects) y la importación (valores por etiqueta legible).
8. **Búsqueda por nombre sin tildes, una sola definición:** `core/utils.py::buscar_por_nombre(db, modelo, nombre, *condiciones)` (lo usa `nombre_libre` y el motor para ubicar el proveedor) y `services/categorias.py::buscar_hija(db, nombre, parent_id)` (lo usa `_nombre_libre` de categorías y el motor para recorrer el camino).
9. **Categoría con subcategorías:** el motor chequea `es_hoja` antes de `crear_producto` solo para dar el mensaje del spec ("La categoría '…' tiene subcategorías: indicá el camino hasta el último nivel."); la garantía sigue siendo el chequeo de `crear_producto`.
10. **Zip bomb** (pendiente del módulo 03): `leer_tabla` suma `file_size` de `ZipFile.infolist()` y rechaza más de 50 MB descomprimidos (409 "El archivo es demasiado grande una vez descomprimido.").
11. `stock_inicial` y `stock_minimo`: entero entre 0 y 1.000.000 (mismo tope que `ProductoCrear.stock_inicial` y `StockMinimo`), validado en el parser: sin ese tope un negativo se ignoraría en silencio y un número enorme rompería la base.
12. Auditoría de la importación: `accion="importacion.<tipo>"`, `entidad="importacion"`, `entidad_id=None`, `estado_nuevo={"archivo", "filas", "creados"}` (como `dolar.importar`).

---

## File Structure

```
backend/app/core/excel.py                     (mod) Task 1  límite de tamaño descomprimido
backend/app/core/etiquetas.py                 (new) Task 1  MONEDAS, CONDICIONES_IVA, TEMPORADAS
backend/app/core/utils.py                     (mod) Task 1  buscar_por_nombre (nombre_libre lo usa)
backend/app/api/pages.py                      (mod) Task 1  importa etiquetas de core/etiquetas.py
                                              (mod) Task 3  SECCION_IMPORTACION + ruta /importacion
backend/app/schemas/importacion.py            (new) Task 1  TipoImportacion, ErrorImportacion, ResultadoImportacion
backend/app/services/importacion.py           (new) Task 1  motor + definiciones de proveedores y clientes
                                              (mod) Task 2  definición de productos
backend/app/services/categorias.py            (mod) Task 2  buscar_hija (_nombre_libre la usa)
backend/app/api/v1/importacion.py             (new) Task 1
backend/app/api/v1/__init__.py                (mod) Task 1
backend/tests/test_excel.py                   (mod) Task 1  zip bomb
backend/tests/test_importacion.py             (new) Task 1, Task 2
backend/app/templates/pages/importacion/index.html  (new) Task 3
backend/app/static/js/importacion.js          (new) Task 3
backend/tests/test_paginas_importacion.py     (new) Task 3
backend/tests_js/importacion.test.mjs         (new) Task 3
```

Revisión por tarea: **Task 1 y Task 2 llevan revisor** (savepoints/todo-o-nada, permisos, auditoría, stock y precios). **Task 3 no** (pantalla; la cubre la revisión final con Opus).

---

### Task 1: Motor de importación + proveedores y clientes + endpoints

**Files:**
- Modify: `backend/app/core/excel.py`
- Create: `backend/app/core/etiquetas.py`
- Modify: `backend/app/core/utils.py` (`nombre_libre`, líneas ~117-135)
- Modify: `backend/app/api/pages.py` (constantes `TEMPORADAS` y `CONDICIONES_IVA`, líneas ~73-107)
- Create: `backend/app/schemas/importacion.py`
- Create: `backend/app/services/importacion.py`
- Create: `backend/app/api/v1/importacion.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_excel.py`, `backend/tests/test_importacion.py`

**Interfaces:**
- Consumes: `core.excel.leer_tabla(contenido, requeridas, opcionales) -> list[tuple[int, dict]]`, `core.excel.generar_plantilla(hoja, columnas, instrucciones, filas=None) -> bytes`, `core.excel.celda_decimal`, `core.excel.celda_entero`, `core.excel.clave_columna`, `services.proveedores.crear_proveedor(db, autor, ProveedorCrear, ip)`, `services.proveedores.validar_dolar(valor) -> Decimal`, `services.clientes.crear_cliente(db, autor, ClienteCrear, ip)`, `services.clientes.solo_digitos`, `core.auditoria.registrar_auditoria`.
- Produces (Task 2 y 3 dependen de esto):
  - `app.schemas.importacion.TipoImportacion` (`PROVEEDORES="proveedores"`, `CLIENTES="clientes"`, `PRODUCTOS="productos"`), `ErrorImportacion`, `ResultadoImportacion`.
  - `app.services.importacion`: `Columna`, `Definicion`, `ErrorDeFila(mensaje, columna=None)`, `DEFINICIONES: dict[TipoImportacion, Definicion]`, parsers `_texto`, `_decimal`, `_entero_no_negativo`, `_opcion(opciones)`, helpers `_sin_vacios(valores, *excluir)`, `_en_columna(columna)` (context manager), y las funciones públicas `generar_plantilla(tipo) -> bytes`, `validar(db, autor, tipo, contenido, archivo) -> dict`, `importar(db, autor, tipo, contenido, archivo, ip) -> dict`.
  - `Definicion.alta` tiene la firma `alta(db, autor, valores: dict, ip, nuevas: list[str]) -> None` (`nuevas` = caminos de categorías creadas por esa fila; solo lo usa productos).
  - `app.core.etiquetas.MONEDAS`, `CONDICIONES_IVA`, `TEMPORADAS`: `list[tuple[valor, etiqueta]]`.
  - `app.core.utils.buscar_por_nombre(db, modelo, nombre, *condiciones)`.
  - Endpoints: `GET /api/v1/importacion/{tipo}/plantilla`, `POST /api/v1/importacion/{tipo}/validar`, `POST /api/v1/importacion/{tipo}/importar` (multipart `archivo`).

- [ ] **Step 1: Crear la rama**

```bash
cd /Users/agustin/Documents/Stork-Gestion
git status            # debe estar limpio y en dev
git checkout -b modulo-08-importacion
```

- [ ] **Step 2: Test del zip bomb (falla)**

Agregar al final de `backend/tests/test_excel.py` (sumar `import zipfile` e `from io import BytesIO` a los imports si no están):

```python
def test_leer_tabla_rechaza_archivo_que_descomprimido_es_enorme():
    # 60 MB de ceros comprimen a unos pocos KB: pasa el límite de 5 MB del
    # archivo, pero no el de lo descomprimido (zip bomb).
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"\0" * (60 * 1024 * 1024))
    with pytest.raises(ReglaDeNegocio, match="descomprimido"):
        leer_tabla(salida.getvalue(), ["nombre"])
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_excel.py -k descomprimido -v`
Expected: FAIL (hoy da "El archivo no es un Excel (.xlsx) válido.").

- [ ] **Step 3: Límite de lo descomprimido en `leer_tabla`**

En `backend/app/core/excel.py`: sumar `from zipfile import BadZipFile, ZipFile` a los imports, la constante debajo de `TAMANO_MAXIMO_BYTES`:

```python
# Un .xlsx es un zip: 5 MB comprimidos pueden ser gigas descomprimidos (zip
# bomb). Se suma el tamaño declarado de cada entrada antes de abrirlo; zipfile
# nunca entrega más bytes que los declarados, así que el límite es efectivo.
TAMANO_DESCOMPRIMIDO_MAXIMO = 50 * 1024 * 1024
```

y en `leer_tabla`, justo después del chequeo de `TAMANO_MAXIMO_BYTES` y antes de `load_workbook`:

```python
    try:
        with ZipFile(BytesIO(contenido)) as comprimido:
            descomprimido = sum(entrada.file_size for entrada in comprimido.infolist())
    except BadZipFile as exc:
        raise ReglaDeNegocio("El archivo no es un Excel (.xlsx) válido.") from exc
    if descomprimido > TAMANO_DESCOMPRIMIDO_MAXIMO:
        raise ReglaDeNegocio("El archivo es demasiado grande una vez descomprimido.")
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_excel.py -v`
Expected: PASS (todos, incluidos los de archivos inválidos: "basura" sigue dando "no es un Excel").

- [ ] **Step 4: Etiquetas de enums en `core/etiquetas.py`**

Crear `backend/app/core/etiquetas.py`:

```python
"""Textos legibles de los enums: ÚNICA definición. Los usan las pantallas
(selects y filtros, vía app/api/pages.py) y la importación desde Excel (que
acepta la etiqueta o el valor)."""
from app.models import CondicionIva, Moneda, TemporadaProducto

MONEDAS = [
    (Moneda.ARS.value, "Pesos"),
    (Moneda.USD.value, "Dólares"),
]
CONDICIONES_IVA = [
    (CondicionIva.CONSUMIDOR_FINAL.value, "Consumidor final"),
    (CondicionIva.RESPONSABLE_INSCRIPTO.value, "Responsable inscripto"),
    (CondicionIva.MONOTRIBUTISTA.value, "Monotributista"),
    (CondicionIva.EXENTO.value, "Exento"),
]
TEMPORADAS = [
    (TemporadaProducto.ATEMPORAL.value, "Atemporal"),
    (TemporadaProducto.OTONO_INVIERNO.value, "Otoño-Invierno"),
    (TemporadaProducto.PRIMAVERA_VERANO.value, "Primavera-Verano"),
]
```

En `backend/app/api/pages.py`: borrar las definiciones de `TEMPORADAS` y `CONDICIONES_IVA` (con sus comentarios) y agregar `from app.core.etiquetas import CONDICIONES_IVA, TEMPORADAS` junto a los otros imports de `app.core`. Si después de esto `CondicionIva` o `TemporadaProducto` quedan sin uso en `pages.py`, quitarlos del import. Verificar con `grep -rn "TEMPORADAS\|CONDICIONES_IVA" backend/app backend/tests` que nadie más las importe de `pages` (si algún test lo hace, pasarlo a `app.core.etiquetas`).

- [ ] **Step 5: `buscar_por_nombre` en `core/utils.py`**

En `backend/app/core/utils.py`, antes de `nombre_libre`, agregar:

```python
def buscar_por_nombre(db, modelo, nombre: str | None, *condiciones):
    """Fila de `modelo` cuyo `nombre` coincide sin importar mayúsculas, tildes
    ni espacios de más (None si no hay). `condiciones` suma filtros (ej. el
    padre de una categoría). Única definición de esta búsqueda."""
    limpio = normalizar_texto(nombre)
    if not limpio:
        return None
    return db.scalar(select(modelo).where(
        func.lower(sin_tildes_sql(modelo.nombre)) == sin_tildes(limpio).lower(), *condiciones))
```

y reescribir el cuerpo de `nombre_libre` para usarla (misma firma y mismo comportamiento):

```python
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [modelo.id != excepto_id] if excepto_id is not None else []
    existente = buscar_por_nombre(db, modelo, limpio, *condiciones)
    if existente is not None:
        raise ReglaDeNegocio(mensaje_duplicado(existente))
    return limpio
```

(Mantener el docstring existente de `nombre_libre` y respetar lo que hoy hace después del `if existente` — si hoy levanta otra cosa, conservarlo.)

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_utils.py tests/test_proveedores_service.py tests/test_medios_pago.py -q`
Expected: PASS.

- [ ] **Step 6: Schemas**

Crear `backend/app/schemas/importacion.py`:

```python
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
```

- [ ] **Step 7: Tests del motor con proveedores y clientes (fallan)**

Crear `backend/tests/test_importacion.py`:

```python
"""Importación inicial desde Excel (sesión 08): motor, proveedores y clientes.
Los productos se prueban en la segunda mitad del archivo (Task 2)."""
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.excel import TIPO_XLSX
from app.models import Auditoria, Cliente, Proveedor

URL = "/api/v1/importacion"
ENCABEZADO_PROVEEDORES = ["nombre", "moneda", "dolar_actual", "pais", "provincia", "telefono", "email", "notas"]
ENCABEZADO_CLIENTES = ["nombre", "dni", "cuit", "condicion_iva", "domicilio", "codigo_postal", "localidad",
                       "telefono", "email"]
CUIT_VALIDO = "20-39059158-7"


def _xlsx(filas) -> bytes:
    libro = Workbook()
    for fila in filas:
        libro.active.append(list(fila))
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _subir(client, h, tipo, accion, filas, nombre="datos.xlsx"):
    return client.post(f"{URL}/{tipo}/{accion}", files={"archivo": (nombre, _xlsx(filas), TIPO_XLSX)}, headers=h)


def _contar(db, modelo):
    return db.scalar(select(func.count()).select_from(modelo))


def _admin(crear_usuario, headers_de):
    return headers_de(crear_usuario("admin"))


def test_plantilla_vacia_da_409_y_con_filas_importa(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = client.get(f"{URL}/proveedores/plantilla", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == TIPO_XLSX
    assert 'filename="importar-proveedores-' in r.headers["content-disposition"]
    libro = load_workbook(BytesIO(r.content))
    assert [c.value for c in libro.worksheets[0][1]] == ENCABEZADO_PROVEEDORES
    assert libro.sheetnames == ["Proveedores", "Instrucciones"]

    r = client.post(f"{URL}/proveedores/importar", files={"archivo": ("p.xlsx", r.content, TIPO_XLSX)}, headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "El archivo no tiene filas para importar."

    libro.worksheets[0].append(["Textil Norte", "Pesos"])
    salida = BytesIO()
    libro.save(salida)
    r = client.post(f"{URL}/proveedores/importar", files={"archivo": ("p.xlsx", salida.getvalue(), TIPO_XLSX)},
                    headers=h)
    assert r.status_code == 200
    assert r.json() == {"tipo": "proveedores", "filas_leidas": 1, "filas_validas": 1, "creados": 1,
                        "categorias_nuevas": [], "errores": [], "aplicado": True}


def test_columnas_en_otro_orden_y_extra(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["Columna Extra", "MONEDA", "Nombre", "Dólar Actual"],
             ["x", "Dólares", "Importadora Sur", "1050,5"]]
    r = _subir(client, h, "proveedores", "importar", filas)
    assert r.status_code == 200 and r.json()["creados"] == 1
    proveedor = db.scalar(select(Proveedor).where(Proveedor.nombre == "Importadora Sur"))
    assert proveedor.moneda.value == "usd" and str(proveedor.dolar_actual) == "1050.50"


def test_proveedor_en_dolares_sin_dolar_es_error_de_la_columna(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["Sin dolar", "usd"]])
    assert r.status_code == 200
    assert r.json()["errores"] == [
        {"fila": 2, "columna": "dolar_actual", "error": "El valor del dólar debe ser mayor a cero."}]


def test_proveedor_en_pesos_ignora_el_dolar(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "proveedores", "importar", [["nombre", "moneda", "dolar_actual"], ["En pesos", "ars", "-3"]])
    assert r.json()["aplicado"] is True
    assert db.scalar(select(Proveedor).where(Proveedor.nombre == "En pesos")).dolar_actual is None


def test_proveedor_duplicado_en_base_y_en_archivo(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    assert _subir(client, h, "proveedores", "importar", [["nombre", "moneda"], ["Lanas Río", "Pesos"]]).status_code == 200
    filas = [["nombre", "moneda"], ["lanas rio", "Pesos"], ["Nuevo", "Pesos"], ["NUEVO", "Pesos"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert errores[0]["fila"] == 2 and errores[0]["columna"] is None and "Ya existe un proveedor" in errores[0]["error"]
    assert errores[1] == {"fila": 4, "columna": "nombre", "error": "Repetido en el archivo (fila 3)."}


def test_moneda_invalida_y_varios_errores_de_una_fila(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["nombre", "moneda", "email"], ["x" * 201, "Euros", "no-es-mail"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert {"fila": 2, "columna": "moneda", "error": "Valor no válido: usá Pesos / Dólares."} in errores
    # moneda falla en el parseo: el alta de esa fila no se intenta, así que no hay error de schema todavía.
    assert len(errores) == 1
    filas = [["nombre", "moneda", "email"], ["x" * 201, "Pesos", "no-es-mail"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert {"fila": 2, "columna": "nombre", "error": "Admite hasta 200 caracteres."} in errores
    assert {"fila": 2, "columna": "email", "error": "El email no es válido."} in errores


def test_obligatoria_vacia(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    errores = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["", "Pesos"], ["Ok", None]]).json()["errores"]
    assert errores == [{"fila": 2, "columna": "nombre", "error": "Es obligatoria."},
                       {"fila": 3, "columna": "moneda", "error": "Es obligatoria."}]


def test_cliente_cuit_invalido_y_dni_repetido(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    assert _subir(client, h, "clientes", "importar", [["nombre", "dni"], ["Ana", 30123456]]).json()["aplicado"]
    filas = [["nombre", "dni", "cuit", "condicion_iva"],
             ["Beto", "30.123.456", None, None],                 # DNI ya en la base
             ["Caro", None, "20-39059158-2", None],                # dígito verificador mal
             ["Dani", 40111222, None, None],
             ["Eli", "40111222", None, None],                    # DNI repetido en el archivo
             ["Fede", None, None, "Responsable inscripto"]]      # sin CUIT y no es consumidor final
    errores = _subir(client, h, "clientes", "validar", filas).json()["errores"]
    assert [(e["fila"], e["columna"]) for e in errores] == [(2, None), (3, None), (5, "dni"), (6, None)]
    assert "ya está cargado" in errores[0]["error"]
    assert "dígito verificador" in errores[1]["error"]
    assert errores[2]["error"] == "Repetido en el archivo (fila 4)."
    assert "CUIT es obligatorio" in errores[3]["error"]


def test_cliente_condicion_por_etiqueta_valor_o_default(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["nombre", "cuit", "condicion_iva"],
             ["Uno SA", CUIT_VALIDO, "responsable_inscripto"],
             ["Dos", None, None],
             ["Tres", "27-28033514-8", "monotributista"]]
    r = _subir(client, h, "clientes", "importar", filas)
    assert r.json()["errores"] == [] and r.json()["creados"] == 3
    condiciones = {c.nombre: c.condicion_iva.value for c in db.scalars(select(Cliente)).all()}
    assert condiciones["Uno SA"] == "responsable_inscripto" and condiciones["Dos"] == "consumidor_final"


def test_todo_o_nada(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    antes = _contar(db, Proveedor)
    filas = [["nombre", "moneda"], ["Bueno 1", "Pesos"], ["Malo", "usd"], ["Bueno 2", "Pesos"]]
    r = _subir(client, h, "proveedores", "importar", filas)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["aplicado"] is False and cuerpo["creados"] == 0
    assert cuerpo["filas_leidas"] == 3 and cuerpo["filas_validas"] == 2 and len(cuerpo["errores"]) == 1
    assert _contar(db, Proveedor) == antes


def test_validar_no_deja_rastros(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedores, auditoria = _contar(db, Proveedor), _contar(db, Auditoria)
    r = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["Solo vista previa", "Pesos"]])
    assert r.json() == {"tipo": "proveedores", "filas_leidas": 1, "filas_validas": 1, "creados": 0,
                        "categorias_nuevas": [], "errores": [], "aplicado": False}
    assert _contar(db, Proveedor) == proveedores
    assert _contar(db, Auditoria) == auditoria


def test_importar_audita_la_importacion_y_cada_alta(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "clientes", "importar", [["nombre"], ["Uno"], ["Dos"]], nombre="clientes-viejos.xlsx")
    assert r.json()["creados"] == 2
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "importacion.clientes"))
    assert registro.estado_nuevo == {"archivo": "clientes-viejos.xlsx", "filas": 2, "creados": 2}
    assert registro.entidad == "importacion" and registro.entidad_id is None
    assert db.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.accion == "cliente.crear")) >= 2


def test_sin_permiso_403_y_tipo_invalido_422(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("vendedor"))
    assert client.get(f"{URL}/clientes/plantilla", headers=h).status_code == 403
    assert _subir(client, h, "clientes", "validar", [["nombre"], ["x"]]).status_code == 403
    assert _subir(client, h, "clientes", "importar", [["nombre"], ["x"]]).status_code == 403
    h = _admin(crear_usuario, headers_de)
    assert client.get(f"{URL}/ventas/plantilla", headers=h).status_code == 422


def test_archivo_invalido_409(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = client.post(f"{URL}/clientes/validar", files={"archivo": ("x.xlsx", b"basura", TIPO_XLSX)}, headers=h)
    assert r.status_code == 409
    r = _subir(client, h, "clientes", "validar", [["dni"], ["1"]])
    assert r.status_code == 409 and r.json()["detail"] == "Faltan columnas: nombre"
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_importacion.py -q`
Expected: FAIL (404: no existe el router).

- [ ] **Step 8: El motor + definiciones de proveedores y clientes**

Crear `backend/app/services/importacion.py`:

```python
"""Importación inicial desde Excel (sesión 08): proveedores, clientes y productos.

Un único motor (`_procesar`) parametrizado por una `Definicion` por tipo. Cada
alta pasa por el service del módulo dueño, así que se aplican exactamente las
mismas validaciones y la misma auditoría que el alta manual (Principio 2): acá
solo se parsean celdas, se detectan repetidos dentro del archivo y se resuelven
nombres a ids. Solo altas: nunca modifica registros existentes.

Validar e importar recorren el mismo camino (un SAVEPOINT exterior con uno por
fila) y solo difieren al final: validar siempre revierte; importar confirma si
no hubo ningún error. Así la vista previa nunca promete algo que la
importación después rechaza. Lo único que el rollback no deshace son las
secuencias (ids y SKU): validar puede dejar huecos en la numeración."""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.auditoria import registrar_auditoria
from app.core.errores import MENSAJE_INTEGRIDAD, ErrorDeNegocio, ReglaDeNegocio
from app.core.etiquetas import CONDICIONES_IVA, MONEDAS
from app.core.excel import celda_decimal, celda_entero, clave_columna, generar_plantilla as _plantilla, leer_tabla
from app.models import Moneda
from app.schemas.clientes import ClienteCrear
from app.schemas.importacion import TipoImportacion
from app.schemas.proveedores import ProveedorCrear
from app.services import clientes as servicio_clientes
from app.services import proveedores as servicio_proveedores

# Mismo tope que ProductoCrear.stock_inicial y StockMinimo.stock_minimo.
ENTERO_MAXIMO = 1_000_000
ENCABEZADO_INSTRUCCIONES = ["Columna", "Obligatoria", "Formato", "Valores posibles", "Ejemplo"]


class ErrorDeFila(Exception):
    """Error de una fila ubicado en una columna (None = la fila en general)."""

    def __init__(self, mensaje: str, columna: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.columna = columna


@contextmanager
def _en_columna(columna: str):
    """Ubica en `columna` el error de negocio que levante el bloque."""
    try:
        yield
    except ErrorDeNegocio as exc:
        raise ErrorDeFila(exc.mensaje, columna) from exc


# ---------- Parsers de celdas: valor crudo → valor Python (ValueError = mensaje para el usuario) ----------

def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)          # un DNI tipeado como número llega como 30123456.0
    return str(valor).strip() or None   # la normalización fina la hace el service dueño


def _decimal(valor):
    try:
        return celda_decimal(valor)
    except ValueError:
        raise ValueError("Tiene que ser un número.") from None


def _entero_no_negativo(valor):
    try:
        numero = celda_entero(valor)
    except ValueError:
        raise ValueError("Tiene que ser un número entero.") from None
    if numero is not None and not 0 <= numero <= ENTERO_MAXIMO:
        raise ValueError("Tiene que ser un número entero entre 0 y 1.000.000.")
    return numero


def _opcion(opciones):
    """Parser de un enum: acepta la etiqueta legible o el valor, sin importar
    mayúsculas ni tildes. Devuelve el valor."""
    por_clave = {}
    for valor, etiqueta in opciones:
        por_clave[clave_columna(valor)] = valor
        por_clave[clave_columna(etiqueta)] = valor
    posibles = " / ".join(etiqueta for _, etiqueta in opciones)

    def parsear(celda):
        texto = _texto(celda)
        if texto is None:
            return None
        try:
            return por_clave[clave_columna(texto)]
        except KeyError:
            raise ValueError(f"Valor no válido: usá {posibles}.") from None

    parsear.posibles = posibles
    return parsear


# ---------- Definiciones ----------

@dataclass(frozen=True)
class Columna:
    nombre: str                     # encabezado (ya en la forma de clave_columna)
    formato: str
    ejemplo: str
    obligatoria: bool = False
    valores: str = ""
    parser: Callable = _texto


@dataclass(frozen=True)
class Definicion:
    hoja: str
    columnas: tuple[Columna, ...]
    # alta(db, autor, valores, ip, nuevas): crea el registro con el service
    # dueño; `nuevas` recibe los caminos de categorías que creó esa fila.
    alta: Callable
    # claves(valores) → [(columna, clave)]: dos filas con la misma clave en la
    # misma columna son un error ("Repetido en el archivo"). Clave None = no se compara.
    claves: Callable

    @property
    def requeridas(self) -> list[str]:
        return [c.nombre for c in self.columnas if c.obligatoria]

    @property
    def opcionales(self) -> list[str]:
        return [c.nombre for c in self.columnas if not c.obligatoria]


def _sin_vacios(valores: dict, *excluir: str) -> dict:
    """Campos con valor, para que el schema aplique sus defaults a los vacíos."""
    return {k: v for k, v in valores.items() if v is not None and k not in excluir}


def _alta_proveedor(db, autor, valores, ip, nuevas):
    campos = _sin_vacios(valores)
    if campos.get("moneda") == Moneda.USD.value:
        # La regla (obligatorio y > 0) es la del service; acá solo se ubica el error en su columna.
        with _en_columna("dolar_actual"):
            campos["dolar_actual"] = servicio_proveedores.validar_dolar(campos.get("dolar_actual"))
    else:
        campos.pop("dolar_actual", None)        # en pesos el dólar se ignora
    servicio_proveedores.crear_proveedor(db, autor, ProveedorCrear(**campos), ip)


def _alta_cliente(db, autor, valores, ip, nuevas):
    servicio_clientes.crear_cliente(db, autor, ClienteCrear(**_sin_vacios(valores)), ip)


_MONEDA = _opcion(MONEDAS)
_CONDICION_IVA = _opcion(CONDICIONES_IVA)

DEFINICIONES: dict[TipoImportacion, Definicion] = {
    TipoImportacion.PROVEEDORES: Definicion(
        hoja="Proveedores",
        columnas=(
            Columna("nombre", "Texto (único, hasta 200 caracteres)", "Textil Norte", obligatoria=True),
            Columna("moneda", "Texto", "Pesos", obligatoria=True, valores=_MONEDA.posibles, parser=_MONEDA),
            Columna("dolar_actual", "Número mayor a 0 (obligatorio si es en dólares; se ignora si es en pesos)",
                    "1050,50", parser=_decimal),
            Columna("pais", "Texto", "Argentina"),
            Columna("provincia", "Texto", "Buenos Aires"),
            Columna("telefono", "Texto", "11 4444-5555"),
            Columna("email", "Email", "ventas@textilnorte.com"),
            Columna("notas", "Texto libre", "Entrega los martes"),
        ),
        alta=_alta_proveedor,
        claves=lambda v: [("nombre", clave_columna(v["nombre"]))],
    ),
    TipoImportacion.CLIENTES: Definicion(
        hoja="Clientes",
        columnas=(
            Columna("nombre", "Texto (nombre o razón social)", "María López", obligatoria=True),
            Columna("dni", "7 u 8 dígitos (único)", "30123456"),
            Columna("cuit", "11 dígitos, con o sin guiones (único; obligatorio si no es consumidor final)",
                    "20-39059158-7"),
            Columna("condicion_iva", "Texto (vacío = Consumidor final)", "Consumidor final",
                    valores=_CONDICION_IVA.posibles, parser=_CONDICION_IVA),
            Columna("domicilio", "Texto", "Av. Siempreviva 742"),
            Columna("codigo_postal", "Texto", "1414"),
            Columna("localidad", "Texto", "CABA"),
            Columna("telefono", "Texto", "11 5555-6666"),
            Columna("email", "Email", "maria@mail.com"),
        ),
        alta=_alta_cliente,
        claves=lambda v: [("dni", servicio_clientes.solo_digitos(v["dni"])),
                          ("cuit", servicio_clientes.solo_digitos(v["cuit"]))],
    ),
}


# ---------- Motor ----------

_MENSAJES_PYDANTIC = {
    "missing": lambda ctx: "Es obligatoria.",
    "string_too_short": lambda ctx: "Es obligatoria.",
    "string_too_long": lambda ctx: f"Admite hasta {ctx['max_length']} caracteres.",
    "greater_than": lambda ctx: f"Tiene que ser mayor a {ctx['gt']}.",
    "greater_than_equal": lambda ctx: f"Tiene que ser mayor o igual a {ctx['ge']}.",
    "less_than": lambda ctx: f"Tiene que ser menor a {ctx['lt']}.",
    "less_than_equal": lambda ctx: f"Tiene que ser menor o igual a {ctx['le']}.",
    "decimal_max_places": lambda ctx: f"Admite hasta {ctx['decimal_places']} decimales.",
    "decimal_max_digits": lambda ctx: "El número es demasiado grande.",
}


def _mensaje_pydantic(error: dict) -> str:
    armar = _MENSAJES_PYDANTIC.get(error["type"])
    if armar is not None:
        return armar(error.get("ctx") or {})
    if error["loc"] and error["loc"][0] == "email":
        return "El email no es válido."
    return "Dato inválido."


def _parsear(definicion: Definicion, celdas: dict) -> tuple[dict, list[tuple[str, str]]]:
    """Valores parseados y la lista de (columna, error) de TODAS las columnas con error."""
    valores, errores = {}, []
    for columna in definicion.columnas:
        try:
            valor = columna.parser(celdas.get(columna.nombre))
        except ValueError as exc:
            errores.append((columna.nombre, str(exc)))
            continue
        if valor is None and columna.obligatoria:
            errores.append((columna.nombre, "Es obligatoria."))
            continue
        valores[columna.nombre] = valor
    return valores, errores


def _procesar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None, ip, aplicar: bool) -> dict:
    definicion = DEFINICIONES[tipo]
    filas = leer_tabla(contenido, definicion.requeridas, definicion.opcionales)
    if not filas:
        raise ReglaDeNegocio("El archivo no tiene filas para importar.")
    errores, categorias_nuevas, vistas = [], [], {}
    validas = 0

    def error(fila, columna, mensaje):
        errores.append({"fila": fila, "columna": columna, "error": mensaje})

    exterior = db.begin_nested()
    try:
        for numero, celdas in filas:
            valores, errores_de_parseo = _parsear(definicion, celdas)
            for columna, mensaje in errores_de_parseo:
                error(numero, columna, mensaje)
            if errores_de_parseo:
                continue
            repetida = False
            for columna, clave in definicion.claves(valores):
                if clave is None:
                    continue
                anterior = vistas.setdefault((columna, clave), numero)
                if anterior != numero:
                    error(numero, columna, f"Repetido en el archivo (fila {anterior}).")
                    repetida = True
            if repetida:
                continue
            nuevas: list[str] = []
            try:
                # Savepoint por fila: un error (incluso de la base) deshace solo
                # esta fila y la sesión sigue usable para las siguientes.
                with db.begin_nested():
                    definicion.alta(db, autor, valores, ip, nuevas)
            except ErrorDeFila as exc:
                error(numero, exc.columna, exc.mensaje)
            except ValidationError as exc:
                for detalle in exc.errors():
                    campo = detalle["loc"][0] if detalle["loc"] else None
                    error(numero, campo if campo in valores else None, _mensaje_pydantic(detalle))
            except ErrorDeNegocio as exc:
                error(numero, None, exc.mensaje)
            except IntegrityError:
                error(numero, None, MENSAJE_INTEGRIDAD)
            else:
                validas += 1
                categorias_nuevas.extend(nuevas)
        aplicado = aplicar and not errores
        if aplicado:
            registrar_auditoria(db, accion=f"importacion.{tipo.value}", entidad="importacion", entidad_id=None,
                                usuario_id=autor.id,
                                estado_nuevo={"archivo": archivo, "filas": len(filas), "creados": validas},
                                ip_origen=ip)
            exterior.commit()
        else:
            exterior.rollback()
    except BaseException:
        if exterior.is_active:
            exterior.rollback()
        raise
    return {"tipo": tipo, "filas_leidas": len(filas), "filas_validas": validas,
            "creados": validas if aplicado else 0, "categorias_nuevas": categorias_nuevas,
            "errores": errores, "aplicado": aplicado}


def validar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None) -> dict:
    """Vista previa: todos los errores de una vez, sin dejar nada en la base."""
    return _procesar(db, autor, tipo, contenido, archivo, None, aplicar=False)


def importar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None, ip) -> dict:
    """Todo o nada: vuelve a validar desde cero y aplica solo si no hay ningún error."""
    return _procesar(db, autor, tipo, contenido, archivo, ip, aplicar=True)


def generar_plantilla(tipo: TipoImportacion) -> bytes:
    definicion = DEFINICIONES[tipo]
    instrucciones = [ENCABEZADO_INSTRUCCIONES] + [
        [c.nombre, "Sí" if c.obligatoria else "No", c.formato, c.valores, c.ejemplo] for c in definicion.columnas
    ]
    return _plantilla(definicion.hoja, [c.nombre for c in definicion.columnas], instrucciones)
```

Notas para el implementador:
- `vistas.setdefault(...)` registra la primera aparición aunque esa fila después falle en el alta: una segunda fila con el mismo nombre se reporta igual como repetida (es lo que se quiere: hay que corregir el archivo).
- `campo if campo in valores` ubica el error de Pydantic en la columna del Excel cuando el campo del schema se llama igual; si no (ej. `categoria_id` en productos), queda `None`.
- `registrar_auditoria` con `estado_nuevo` dict: ver cómo lo llama `importar_dolar` en `services/proveedores.py` (mismo patrón).

- [ ] **Step 9: Router**

Crear `backend/app/api/v1/importacion.py`:

```python
"""Importación inicial desde Excel (sesión 08). Todas las rutas piden
IMPORTACION crear (decisión de producto: alcanza con ese permiso)."""
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.excel import TAMANO_MAXIMO_BYTES, TIPO_XLSX
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ahora, ip_de_request
from app.models import Usuario
from app.schemas.importacion import ResultadoImportacion, TipoImportacion
from app.services import importacion as servicio

router = APIRouter(prefix="/importacion", tags=["importacion"])

puede_importar = requiere_permiso(Modulo.IMPORTACION, "crear")


def _leer(archivo: UploadFile) -> bytes:
    return archivo.file.read(TAMANO_MAXIMO_BYTES + 1)   # leer_tabla rechaza lo que pase de 5 MB


@router.get(
    "/{tipo}/plantilla",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {"schema": {"type": "string", "format": "binary"}}},
                     "description": "Plantilla .xlsx con la hoja de datos y la hoja Instrucciones"}},
)
def plantilla(tipo: TipoImportacion, _: Usuario = Depends(puede_importar)):
    nombre = f"importar-{tipo.value}-{ahora().date().isoformat()}.xlsx"
    return Response(content=servicio.generar_plantilla(tipo), media_type=TIPO_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/{tipo}/validar", response_model=ResultadoImportacion)
def validar(tipo: TipoImportacion, archivo: UploadFile = File(...), db: Session = Depends(get_db),
            autor: Usuario = Depends(puede_importar)):
    resultado = servicio.validar(db, autor, tipo, _leer(archivo), archivo.filename)
    db.rollback()       # el service ya revirtió su savepoint; esto libera los locks tomados
    return resultado


@router.post("/{tipo}/importar", response_model=ResultadoImportacion)
def importar(tipo: TipoImportacion, request: Request, archivo: UploadFile = File(...),
             db: Session = Depends(get_db), autor: Usuario = Depends(puede_importar)):
    resultado = servicio.importar(db, autor, tipo, _leer(archivo), archivo.filename, ip_de_request(request))
    if resultado["aplicado"]:
        db.commit()
    else:
        db.rollback()
    return resultado
```

En `backend/app/api/v1/__init__.py`: importar `importacion` junto a los otros módulos y agregar `api_router.include_router(importacion.router)` al final de la lista.

Ojo con el `db.rollback()` en tests: el fixture `db` usa `join_transaction_mode="create_savepoint"`, así que el rollback del router revierte solo el savepoint de la sesión (igual que hace `importar_dolar` con errores); los datos creados antes en el test (usuarios) no se pierden. Si algún test pierde datos por esto, revisar cómo lo resuelve `tests/test_proveedores_api.py::test_importacion_con_errores_no_aplica_nada` y seguir el mismo patrón.

- [ ] **Step 10: Correr los tests**

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_importacion.py tests/test_excel.py -v`
Expected: PASS. Si falla algún mensaje exacto de un service (ej. el texto del CUIT), ajustar el test al texto real del service — NUNCA cambiar el mensaje del service para que coincida.

- [ ] **Step 11: Suite completa y commit**

Run: `docker compose exec -T backend pytest -p no:warnings -q`
Expected: todo PASS.

```bash
git add backend/app/core/excel.py backend/app/core/etiquetas.py backend/app/core/utils.py backend/app/api/pages.py \
        backend/app/schemas/importacion.py backend/app/services/importacion.py backend/app/api/v1/importacion.py \
        backend/app/api/v1/__init__.py backend/tests/test_excel.py backend/tests/test_importacion.py
git commit -m "$(cat <<'EOF'
feat(importacion): motor de importación, proveedores y clientes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Importación de productos (categorías por camino, stock inicial y mínimo)

**Files:**
- Modify: `backend/app/services/categorias.py` (`_nombre_libre`, líneas ~120-133)
- Modify: `backend/app/services/importacion.py`
- Test: `backend/tests/test_importacion.py`

**Interfaces:**
- Consumes (de Task 1): `Columna`, `Definicion`, `ErrorDeFila`, `_en_columna`, `_texto`, `_decimal`, `_entero_no_negativo`, `_opcion`, `_sin_vacios`, `DEFINICIONES`, `core.etiquetas.TEMPORADAS`, `core.utils.buscar_por_nombre`. Firma del alta: `alta(db, autor, valores, ip, nuevas)`.
- Consumes (services existentes): `services.categorias.crear_categoria(db, autor, CategoriaCrear, ip)`, `services.categorias.es_hoja(db, categoria_id)`, `services.productos.crear_producto(db, autor, ProductoCrear, ip)`, `services.stock.registrar_ingreso(db, autor, producto_id, cantidad, notas, ip)`, `services.stock.definir_minimo(db, autor, producto_id, stock_minimo, ip)`.
- Produces: `services.categorias.buscar_hija(db, nombre, parent_id) -> Categoria | None`; `DEFINICIONES[TipoImportacion.PRODUCTOS]`; constante `NOTA_STOCK_INICIAL = "Importación inicial"`.

- [ ] **Step 1: Tests de productos (fallan)**

Agregar al final de `backend/tests/test_importacion.py` (sumar a los imports `from decimal import Decimal`, `from app.models import Categoria, MovimientoStock, Producto` y `from tests.fabricas import catalogo`, y `from app.services.productos import calcular_precio_venta`):

```python
# ---------- Productos ----------

ENCABEZADO_PRODUCTOS = ["descripcion", "categoria", "proveedor", "costo", "margen", "sku_proveedor",
                        "descuento_producto", "peso_gramos", "temporada", "ubicacion_deposito",
                        "stock_inicial", "stock_minimo"]


def _proveedor(client, h, nombre="Prov Import", moneda="Pesos", dolar=None):
    r = _subir(client, h, "proveedores", "importar", [["nombre", "moneda", "dolar_actual"], [nombre, moneda, dolar]])
    assert r.json()["aplicado"], r.json()
    return nombre


def _categoria(db, camino):
    """Categoría final del camino (None si no existe)."""
    parent = None
    for nombre in camino.split(" > "):
        condicion = Categoria.parent_id.is_(None) if parent is None else Categoria.parent_id == parent.id
        parent = db.scalar(select(Categoria).where(Categoria.nombre == nombre, condicion))
        if parent is None:
            return None
    return parent


def test_producto_crea_categorias_del_camino_y_calcula_precio(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h, "Dolarizado", "Dólares", "1000")
    filas = [["descripcion", "categoria", "proveedor", "costo", "margen", "temporada", "sku_proveedor"],
             ["Remera lisa", "Ropa Imp > Remeras > Lisas", "dolarizado", "10,5", "50", "Otoño-Invierno", "ABC-1"],
             ["Remera rayada", "ropa imp > REMERAS > Rayadas", proveedor, 12, None, "primavera_verano", None]]
    r = _subir(client, h, "productos", "validar", filas)
    assert r.json()["errores"] == []
    # Los caminos se informan con los nombres guardados, no con el texto de la celda.
    assert r.json()["categorias_nuevas"] == ["Ropa Imp", "Ropa Imp > Remeras", "Ropa Imp > Remeras > Lisas",
                                             "Ropa Imp > Remeras > Rayadas"]
    assert _categoria(db, "Ropa Imp") is None                    # validar no deja categorías

    r = _subir(client, h, "productos", "importar", filas)
    assert r.json()["aplicado"] is True and r.json()["creados"] == 2
    lisa = db.scalar(select(Producto).where(Producto.descripcion == "Remera lisa"))
    assert lisa.categoria_id == _categoria(db, "Ropa Imp > Remeras > Lisas").id
    assert lisa.sku_proveedor == "ABC-1" and lisa.temporada.value == "otoño_invierno"
    # Mismo precio que el alta manual: lo calcula el service de productos.
    assert lisa.precio_venta == calcular_precio_venta(db, Decimal("10.5"), Decimal("50"), lisa.proveedor)
    rayada = db.scalar(select(Producto).where(Producto.descripcion == "Remera rayada"))
    assert rayada.categoria_id == _categoria(db, "Ropa Imp > Remeras > Rayadas").id   # reusó "Ropa Imp > Remeras"


def test_categorias_nuevas_informa_cada_nivel_una_vez(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h)
    filas = [["descripcion", "categoria", "proveedor", "costo"],
             ["A", "Hogar Imp > Mantas", proveedor, 100],
             ["B", "Hogar Imp > Mantas", proveedor, 100],
             ["C", "Hogar Imp > Almohadas", proveedor, 100]]
    assert _subir(client, h, "productos", "validar", filas).json()["categorias_nuevas"] == [
        "Hogar Imp", "Hogar Imp > Mantas", "Hogar Imp > Almohadas"]


def test_categoria_con_subcategorias_o_con_productos(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    admin = crear_usuario("admin")
    datos = catalogo(db, admin)             # "Ropa fab N" > "Remeras fab N", con proveedor "Prov fab N"
    datos["alta"]("Existente")               # la subcategoría ya tiene productos
    madre, hija = datos["categoria"].nombre, datos["subcategoria"].nombre
    filas = [["descripcion", "categoria", "proveedor", "costo"],
             ["X", madre, datos["proveedor"].nombre, 100],
             ["Y", f"{madre} > {hija} > Nueva", datos["proveedor"].nombre, 100]]
    errores = _subir(client, h, "productos", "validar", filas).json()["errores"]
    assert errores[0] == {"fila": 2, "columna": "categoria",
                          "error": f"La categoría '{madre}' tiene subcategorías: indicá el camino hasta el último nivel."}
    assert errores[1]["fila"] == 3 and errores[1]["columna"] == "categoria"   # padre con productos (crear_categoria)


def test_proveedor_inexistente_o_inactivo(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    admin = crear_usuario("admin")
    datos = catalogo(db, admin)
    inactivo = datos["proveedor"]
    from app.models import EstadoProveedor
    inactivo.estado = EstadoProveedor.DESACTIVADO
    db.flush()
    camino = f"{datos['categoria'].nombre} > {datos['subcategoria'].nombre}"
    filas = [["descripcion", "categoria", "proveedor", "costo"],
             ["X", camino, "No existe SA", 100],
             ["Y", camino, inactivo.nombre, 100]]
    errores = _subir(client, h, "productos", "validar", filas).json()["errores"]
    assert errores[0] == {"fila": 2, "columna": "proveedor", "error": "No existe el proveedor 'No existe SA'."}
    assert errores[1]["fila"] == 3 and "no está activo" in errores[1]["error"]


def test_stock_inicial_genera_ingreso_y_minimo(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h)
    filas = [["descripcion", "categoria", "proveedor", "costo", "stock_inicial", "stock_minimo"],
             ["Con stock", "Stock Imp", proveedor, 100, 12, 3],
             ["Sin stock", "Stock Imp", proveedor, 100, 0, None]]
    assert _subir(client, h, "productos", "importar", filas).json()["aplicado"] is True
    con = db.scalar(select(Producto).where(Producto.descripcion == "Con stock"))
    assert con.stock == 12 and con.stock_minimo == 3
    movimiento = db.scalar(select(MovimientoStock).where(MovimientoStock.producto_id == con.id))
    assert movimiento.tipo.value == "ingreso_proveedor" and movimiento.cantidad == 12
    assert movimiento.notas == "Importación inicial"
    sin = db.scalar(select(Producto).where(Producto.descripcion == "Sin stock"))
    assert sin.stock == 0 and db.scalar(select(MovimientoStock).where(MovimientoStock.producto_id == sin.id)) is None


def test_stock_invalido_es_error_de_columna(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h)
    filas = [["descripcion", "categoria", "proveedor", "costo", "stock_inicial", "stock_minimo"],
             ["A", "Stock Mal", proveedor, 100, -1, "2,5"]]
    errores = _subir(client, h, "productos", "validar", filas).json()["errores"]
    assert errores == [
        {"fila": 2, "columna": "stock_inicial", "error": "Tiene que ser un número entero entre 0 y 1.000.000."},
        {"fila": 2, "columna": "stock_minimo", "error": "Tiene que ser un número entero."}]


def test_producto_reglas_del_alta_manual(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h)
    filas = [["descripcion", "categoria", "proveedor", "costo", "descuento_producto"],
             ["Taza", "Bazar Imp", proveedor, 0, None],             # costo > 0 (schema)
             ["Plato", "Bazar Imp", proveedor, 100, 99],            # descuento > descuento_maximo (service)
             ["Vaso", "Bazar Imp", proveedor, 100, None],
             ["vaso", "bazar imp", proveedor.upper(), 100, None]]   # repetido en el archivo
    errores = _subir(client, h, "productos", "validar", filas).json()["errores"]
    assert errores[0] == {"fila": 2, "columna": "costo", "error": "Tiene que ser mayor a 0."}
    assert errores[1]["fila"] == 3 and "descuento" in errores[1]["error"]
    assert errores[2] == {"fila": 5, "columna": "descripcion", "error": "Repetido en el archivo (fila 4)."}


def test_producto_todo_o_nada_ni_categorias(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h)
    productos = _contar(db, Producto)
    filas = [["descripcion", "categoria", "proveedor", "costo", "stock_inicial"],
             ["Bien", "Todo O Nada > Sub", proveedor, 100, 5],
             ["Mal", "Todo O Nada > Sub", "Inexistente", 100, 5]]
    r = _subir(client, h, "productos", "importar", filas)
    assert r.json()["aplicado"] is False and r.json()["creados"] == 0
    assert _contar(db, Producto) == productos
    assert _categoria(db, "Todo O Nada") is None
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "importacion.productos")) is None


def test_importar_productos_sin_permiso_de_stock_ni_productos(client, db, crear_usuario, headers_de):
    """Decisión de producto: alcanza con IMPORTACION crear (rol a medida sin stock ni productos)."""
    from app.models import Rol, UsuarioPermiso
    h_admin = _admin(crear_usuario, headers_de)
    proveedor = _proveedor(client, h_admin)
    rol = Rol(nombre="solo importa", es_sistema=False)
    db.add(rol)
    db.flush()
    usuario = crear_usuario(rol)
    # Mismo patrón que tests/test_paginas_stock.py (permiso puntual por usuario).
    db.add(UsuarioPermiso(usuario_id=usuario.id, modulo="importacion", puede_crear=True))
    db.flush()
    h = headers_de(usuario)
    filas = [["descripcion", "categoria", "proveedor", "costo", "stock_inicial"],
             ["Solo import", "Perm Imp", proveedor, 100, 4]]
    r = _subir(client, h, "productos", "importar", filas)
    assert r.json()["aplicado"] is True, r.json()
    assert db.scalar(select(Producto).where(Producto.descripcion == "Solo import")).stock == 4
```

Notas para el implementador:
- `UsuarioPermiso`: confirmar en `app/models/` el nombre del flag de crear (`puede_crear`) y si `recurso` es opcional; ajustar la línea si difiere.
- `test_producto_reglas_del_alta_manual` supone que `descuento_maximo` por defecto es menor a 99; si no, usar un valor mayor al configurado (y ≤ 100).

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_importacion.py -q`
Expected: FAIL (`TipoImportacion.PRODUCTOS` existe pero no está en `DEFINICIONES`: `KeyError`).

- [ ] **Step 2: `buscar_hija` en categorías**

En `backend/app/services/categorias.py`, antes de `_nombre_libre`:

```python
def buscar_hija(db, nombre: str | None, parent_id: int | None) -> Categoria | None:
    """Categoría con ese nombre (sin mayúsculas ni tildes) entre las hijas de
    `parent_id` (None = primer nivel)."""
    padre = Categoria.parent_id.is_(None) if parent_id is None else Categoria.parent_id == parent_id
    return buscar_por_nombre(db, Categoria, nombre, padre)
```

y reescribir `_nombre_libre` usándola (misma firma, mismos mensajes):

```python
def _nombre_libre(db, nombre: str, parent_id: int | None, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    padre = Categoria.parent_id.is_(None) if parent_id is None else Categoria.parent_id == parent_id
    condiciones = [padre] + ([Categoria.id != excepto_id] if excepto_id is not None else [])
    existente = buscar_por_nombre(db, Categoria, limpio, *condiciones)
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe la categoría '{existente.nombre}' en ese nivel.")
    return limpio
```

(Importar `buscar_por_nombre` de `app.core.utils`; quitar imports que queden sin uso.)

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_categorias.py tests/test_categorias_api.py -q`
Expected: PASS.

- [ ] **Step 3: Definición de productos**

En `backend/app/services/importacion.py`, reemplazar las líneas de import correspondientes por (y sumar las nuevas):

```python
from app.core.etiquetas import CONDICIONES_IVA, MONEDAS, TEMPORADAS
from app.core.utils import buscar_por_nombre
from app.models import Moneda, Proveedor
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import stock as servicio_stock
```

(Si importar `services.stock` a nivel de módulo genera un ciclo — `stock` importa `productos` — hacerlo local dentro de `_alta_producto`, como hace `crear_producto`.)

Agregar, después de `_alta_cliente`:

```python
NOTA_STOCK_INICIAL = "Importación inicial"
SEPARADOR_CAMINO = ">"


def _niveles(camino: str) -> list[str]:
    return [nivel.strip() for nivel in camino.split(SEPARADOR_CAMINO)]


def _proveedor_por_nombre(db, nombre: str) -> Proveedor:
    """Proveedor existente (sin tildes ni mayúsculas). Que esté activo lo
    valida crear_producto (no se duplica la regla)."""
    proveedor = buscar_por_nombre(db, Proveedor, nombre)
    if proveedor is None:
        raise ErrorDeFila(f"No existe el proveedor '{nombre}'.", "proveedor")
    return proveedor


def _categoria_por_camino(db, autor, camino: str, ip, nuevas: list[str]) -> int:
    """Id de la última categoría del camino "Ropa > Remeras > Lisas". Cada
    nivel se busca entre los hermanos y, si no existe, se crea con
    crear_categoria (que valida los 5 niveles y el padre con productos). Los
    caminos creados se agregan a `nuevas` con los nombres guardados."""
    parent_id, recorrido = None, []
    for nombre in _niveles(camino):
        if not nombre:
            raise ErrorDeFila("El camino tiene un nivel vacío: separá los niveles con '>'.", "categoria")
        categoria = servicio_categorias.buscar_hija(db, nombre, parent_id)
        if categoria is None:
            try:
                with _en_columna("categoria"):
                    categoria = servicio_categorias.crear_categoria(
                        db, autor, CategoriaCrear(nombre=nombre, parent_id=parent_id), ip)
            except ValidationError:
                raise ErrorDeFila(f"El nombre de categoría '{nombre}' no es válido (demasiado largo).",
                                  "categoria") from None
            nuevas.append(" > ".join([*recorrido, categoria.nombre]))
        recorrido.append(categoria.nombre)
        parent_id = categoria.id
    if not servicio_categorias.es_hoja(db, parent_id):
        # Chequeo previo solo por el mensaje del spec; la garantía es la de crear_producto.
        raise ErrorDeFila(f"La categoría '{' > '.join(recorrido)}' tiene subcategorías: "
                          "indicá el camino hasta el último nivel.", "categoria")
    return parent_id


def _alta_producto(db, autor, valores, ip, nuevas):
    # Primero el schema (con ids provisorios): así una fila con datos inválidos
    # informa todos sus errores y no llega a crear categorías.
    campos = _sin_vacios(valores, "categoria", "proveedor", "stock_inicial", "stock_minimo")
    datos = ProductoCrear(**campos, categoria_id=0, proveedor_id=0)
    proveedor = _proveedor_por_nombre(db, valores["proveedor"])
    categoria_id = _categoria_por_camino(db, autor, valores["categoria"], ip, nuevas)
    # stock_inicial NO va a crear_producto (exigiría STOCK crear): decisión de
    # producto, alcanza con IMPORTACION crear. El ingreso se registra aparte.
    producto = servicio_productos.crear_producto(
        db, autor, datos.model_copy(update={"categoria_id": categoria_id, "proveedor_id": proveedor.id}), ip)
    if valores["stock_inicial"]:
        with _en_columna("stock_inicial"):
            servicio_stock.registrar_ingreso(db, autor, producto.id, valores["stock_inicial"], NOTA_STOCK_INICIAL, ip)
    if valores["stock_minimo"] is not None:
        with _en_columna("stock_minimo"):
            servicio_stock.definir_minimo(db, autor, producto.id, valores["stock_minimo"], ip)


def _clave_producto(valores):
    """Misma descripción, categoría y proveedor = el mismo producto."""
    camino = tuple(clave_columna(nivel) for nivel in _niveles(valores["categoria"]))
    return [("descripcion", (clave_columna(valores["descripcion"]), camino, clave_columna(valores["proveedor"])))]


_TEMPORADA = _opcion(TEMPORADAS)
```

y la entrada en `DEFINICIONES`:

```python
    TipoImportacion.PRODUCTOS: Definicion(
        hoja="Productos",
        columnas=(
            Columna("descripcion", "Texto (hasta 500 caracteres)", "Remera lisa algodón", obligatoria=True),
            Columna("categoria", "Camino separado por '>' hasta el último nivel (hasta 5). "
                    "Los niveles que no existan se crean.", "Ropa > Remeras > Lisas", obligatoria=True),
            Columna("proveedor", "Nombre de un proveedor ya cargado y activo", "Textil Norte", obligatoria=True),
            Columna("costo", "Número mayor a 0, en la moneda del proveedor", "1500,50", obligatoria=True,
                    parser=_decimal),
            Columna("margen", "Porcentaje (vacío = margen por defecto)", "80", parser=_decimal),
            Columna("sku_proveedor", "Texto. Si venís de otro sistema, poné acá el código que usabas.", "RL-001"),
            Columna("descuento_producto", "Porcentaje (hasta el descuento máximo)", "10", parser=_decimal),
            Columna("peso_gramos", "Número mayor a 0", "250", parser=_decimal),
            Columna("temporada", "Texto (vacío = Atemporal)", "Atemporal", valores=_TEMPORADA.posibles,
                    parser=_TEMPORADA),
            Columna("ubicacion_deposito", "Texto", "Estante A3"),
            Columna("stock_inicial", "Entero de 0 a 1.000.000 (genera un ingreso de stock)", "10",
                    parser=_entero_no_negativo),
            Columna("stock_minimo", "Entero de 0 a 1.000.000", "2", parser=_entero_no_negativo),
        ),
        alta=_alta_producto,
        claves=_clave_producto,
    ),
```

- [ ] **Step 4: Correr los tests**

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_importacion.py -v`
Expected: PASS (con los ajustes de las notas del Step 1).

Chequear a mano también: que `test_importar_productos_sin_permiso_de_stock_ni_productos` pasa sin tocar `crear_producto`; y que `validar` sobre productos con categorías nuevas no deja categorías (lo cubre el primer test).

- [ ] **Step 5: Suite completa y commit**

Run: `docker compose exec -T backend pytest -p no:warnings -q`
Expected: todo PASS.

```bash
git add backend/app/services/categorias.py backend/app/services/importacion.py backend/tests/test_importacion.py
git commit -m "$(cat <<'EOF'
feat(importacion): importación de productos con categorías, stock inicial y mínimo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Pantalla "Importar desde Excel"

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/importacion/index.html`
- Create: `backend/app/static/js/importacion.js`
- Test: `backend/tests/test_paginas_importacion.py`, `backend/tests_js/importacion.test.mjs`

**Interfaces:**
- Consumes: endpoints de Task 1 (`GET /api/v1/importacion/{tipo}/plantilla`, `POST …/validar`, `POST …/importar`) y la forma de `ResultadoImportacion`. Helpers de `app.js`: `window.pedir`, `window.toast`, `window.confirmar`. Macros: `encabezado`, `paginacion`, `icono`.
- Produces: `SECCION_IMPORTACION` en `pages.py`; componente Alpine `window.importacion(tipos)` con funciones puras exportadas en `window.importacionTextos = { resumen, confirmacion, exito }`.

- [ ] **Step 1: Test de página (falla)**

Crear `backend/tests/test_paginas_importacion.py` (mirar `tests/test_paginas_caja.py` para el patrón exacto de `iniciar_sesion` y de chequear 403/tarjeta del hub, y ajustarlo si difiere):

```python
"""Pantalla /importacion (sesión 08)."""


def test_admin_ve_la_pantalla_y_la_tarjeta(iniciar_sesion, crear_usuario):
    cliente = iniciar_sesion(crear_usuario("admin"))
    r = cliente.get("/importacion")
    assert r.status_code == 200
    assert "Importar desde Excel" in r.text and "/static/js/importacion.js" in r.text
    assert 'href="/importacion"' in cliente.get("/configuracion").text


def test_sin_permiso_no_ve_la_pantalla_ni_la_tarjeta(iniciar_sesion, crear_usuario):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert cliente.get("/importacion").status_code == 403
    assert 'href="/importacion"' not in cliente.get("/configuracion").text
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_paginas_importacion.py -v`
Expected: FAIL (404).

- [ ] **Step 2: Sección y ruta**

En `backend/app/api/pages.py`, junto a las otras tarjetas del hub (después de `_registrar_catalogo`/`_CATALOGOS_VENTAS` para que quede al final del hub):

```python
# Tarjeta del hub Configuraciones (sesión 08).
SECCION_IMPORTACION = {
    "nombre": "Importar desde Excel", "descripcion": "Carga inicial de proveedores, clientes y productos",
    "url": "/importacion", "modulo": Modulo.IMPORTACION, "accion": "crear",
}
CONFIGURACION_SECCIONES.append(SECCION_IMPORTACION)
# Pestañas de la pantalla: valor del tipo en la API, texto y listado al que lleva el toast de éxito.
TIPOS_IMPORTACION = [
    {"valor": "proveedores", "etiqueta": "Proveedores", "listado": "/proveedores"},
    {"valor": "clientes", "etiqueta": "Clientes", "listado": "/clientes"},
    {"valor": "productos", "etiqueta": "Productos", "listado": "/productos"},
]
```

y la ruta (cerca de las demás de `/configuracion`):

```python
@router.get("/importacion")
def importacion(request: Request, db: Session = Depends(get_db),
                usuario: Usuario = Depends(requiere_pagina(SECCION_IMPORTACION))):
    return _pagina(request, "pages/importacion/index.html",
                   contexto_base(request, db, "/configuracion", usuario, tipos=TIPOS_IMPORTACION))
```

- [ ] **Step 3: Componente Alpine**

Crear `backend/app/static/js/importacion.js`:

```javascript
// Pantalla "Importar desde Excel" (sesión 08). El frontend no lee el Excel:
// sube el archivo y muestra lo que devuelve la API (validar / importar).
(function () {
  const API = '/api/v1/importacion';
  const TAMANO_PAGINA = 10;

  const textos = {
    resumen(r) {
      return `${r.filas_leidas} filas leídas · ${r.filas_validas} listas para importar`;
    },
    confirmacion(r, etiqueta) {
      return `Se van a crear ${r.filas_validas} ${etiqueta.toLowerCase()}. Esta acción no se deshace desde el sistema.`;
    },
    exito(r, etiqueta) {
      return `Listo: se crearon ${r.creados} ${etiqueta.toLowerCase()}.`;
    },
  };
  window.importacionTextos = textos;

  window.importacion = function (tipos) {
    return {
      tipos,
      tipo: tipos[0],
      archivo: null,
      arrastrando: false,
      resultado: null,        // último ResultadoImportacion de /validar
      validado: null,         // archivo sobre el que se hizo esa validación
      importado: null,        // ResultadoImportacion de /importar (éxito)
      ocupado: false,
      pagina: 1,
      tamano: TAMANO_PAGINA,

      get urlPlantilla() { return `${API}/${this.tipo.valor}/plantilla`; },
      get errores() { return this.resultado ? this.resultado.errores : []; },
      get erroresPagina() {
        const desde = (this.pagina - 1) * this.tamano;
        return this.errores.slice(desde, desde + this.tamano);
      },
      // Importar solo si la validación dio 0 errores y el archivo no cambió.
      get puedeImportar() {
        return !this.ocupado && !!this.resultado && !this.errores.length &&
          this.resultado.filas_validas > 0 && this.validado === this.archivo;
      },
      resumen() { return this.resultado ? textos.resumen(this.resultado) : ''; },

      limpiar() {
        this.resultado = null;
        this.validado = null;
        this.importado = null;
        this.pagina = 1;
      },
      elegirTipo(tipo) {
        if (tipo === this.tipo) return;
        this.tipo = tipo;
        this.archivo = null;
        if (this.$refs && this.$refs.archivo) this.$refs.archivo.value = '';
        this.limpiar();
      },
      elegirArchivo(archivo) {
        this.archivo = archivo || null;
        this.limpiar();
      },
      soltar(evento) {
        this.arrastrando = false;
        this.elegirArchivo(evento.dataTransfer.files[0]);
      },

      async enviar(accion) {
        const datos = new FormData();
        datos.append('archivo', this.archivo);
        return window.pedir(`${API}/${this.tipo.valor}/${accion}`, { method: 'POST', body: datos });
      },

      async validar() {
        if (!this.archivo) return window.toast('Elegí un archivo .xlsx.', 'error');
        const archivo = this.archivo;
        this.ocupado = true;
        try {
          const resultado = await this.enviar('validar');
          if (archivo !== this.archivo) return;   // cambiaron el archivo mientras tanto
          this.limpiar();
          this.resultado = resultado;
          this.validado = archivo;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.ocupado = false;
        }
      },

      async importar() {
        if (!this.puedeImportar) return;
        const confirmado = await window.confirmar({
          titulo: `Importar ${this.tipo.etiqueta.toLowerCase()}`,
          mensaje: textos.confirmacion(this.resultado, this.tipo.etiqueta),
          textoConfirmar: 'Importar',
        });
        if (!confirmado) return;
        this.ocupado = true;
        try {
          const resultado = await this.enviar('importar');
          if (resultado.aplicado) {
            this.limpiar();
            this.importado = resultado;
            this.archivo = null;
            if (this.$refs && this.$refs.archivo) this.$refs.archivo.value = '';
            window.toast(textos.exito(resultado, this.tipo.etiqueta));
          } else {
            // Algo cambió en la base desde que se validó: mostrar los errores nuevos.
            this.resultado = resultado;
            window.toast('No se importó nada: revisá los errores.', 'error');
          }
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.ocupado = false;
        }
      },
    };
  };
})();
```

- [ ] **Step 4: Template**

Crear `backend/app/templates/pages/importacion/index.html` (revisar la firma real de `encabezado` y `paginacion` en `templates/components/` y el nombre de los íconos en `icons.html` antes de usarlos; si `encabezado` recibe el "volver" con otro nombre de argumento, adaptarlo):

```html
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/paginacion.html" import paginacion %}
{% block titulo %}Importar desde Excel · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Importar desde Excel", volver="/configuracion", volver_texto="Configuraciones") }}
<div x-data="importacion({{ tipos|js }})" class="flex flex-col gap-6">
  <p class="text-texto-muted">Cargá los datos iniciales en tres pasos: descargá la plantilla, completala y subila. Primero proveedores, después productos.</p>

  <div class="flex flex-wrap gap-2" role="tablist" aria-label="Qué importar">
    <template x-for="t in tipos" :key="t.valor">
      <button type="button" role="tab" class="boton min-h-toque" :aria-selected="t === tipo"
              :class="t === tipo ? 'boton-primario' : 'boton-secundario'" @click="elegirTipo(t)" x-text="t.etiqueta"></button>
    </template>
  </div>

  <section class="tarjeta flex flex-col gap-4">
    <h2 class="text-xl font-bold text-texto-header">1. Descargá la plantilla</h2>
    <p class="text-sm text-texto-muted">La hoja "Instrucciones" explica cada columna. No cambies los encabezados.</p>
    <a :href="urlPlantilla" class="boton boton-secundario self-start" download>Descargar plantilla</a>
  </section>

  <section class="tarjeta flex flex-col gap-4">
    <h2 class="text-xl font-bold text-texto-header">2. Subí el archivo completo</h2>
    <label class="flex min-h-[8rem] cursor-pointer flex-col items-center justify-center gap-2 rounded-input border-2 border-dashed p-6 text-center"
           :class="arrastrando ? 'border-accent bg-accent/5' : 'border-borde'"
           @dragover.prevent="arrastrando = true" @dragleave.prevent="arrastrando = false" @drop.prevent="soltar($event)">
      <span class="text-texto" x-text="archivo ? archivo.name : 'Arrastrá el .xlsx acá o hacé clic para elegirlo'"></span>
      <input type="file" x-ref="archivo" class="sr-only"
             accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             @change="elegirArchivo($event.target.files[0])">
    </label>
    <div class="flex flex-col gap-2 sm:flex-row sm:justify-end">
      <button type="button" class="boton boton-secundario" :disabled="!archivo || ocupado" @click="validar()">Validar</button>
      <button type="button" class="boton boton-primario" :disabled="!puedeImportar" @click="importar()">Importar</button>
    </div>

    <template x-if="resultado">
      <div class="flex flex-col gap-3">
        <p class="font-semibold text-texto" x-text="resumen()"></p>
        <template x-if="resultado.categorias_nuevas.length">
          <details class="text-sm text-texto">
            <summary class="cursor-pointer">Se van a crear <span x-text="resultado.categorias_nuevas.length"></span> categorías nuevas</summary>
            <ul class="mt-2 list-disc pl-5">
              <template x-for="camino in resultado.categorias_nuevas" :key="camino"><li x-text="camino"></li></template>
            </ul>
          </details>
        </template>
        <div x-show="errores.length">
          <p class="mb-2 font-semibold text-danger">Errores (no se va a importar nada hasta corregirlos)</p>
          <div class="overflow-x-auto">
            <table class="tabla">
              <thead><tr><th scope="col" class="text-right">Fila</th><th scope="col">Columna</th><th scope="col">Error</th></tr></thead>
              <tbody>
                <template x-for="(e, i) in erroresPagina" :key="`${e.fila}-${e.columna}-${i}`">
                  <tr><td class="text-right" x-text="e.fila"></td><td x-text="e.columna || '—'"></td><td x-text="e.error"></td></tr>
                </template>
              </tbody>
            </table>
          </div>
          {{ paginacion(total="errores.length", al_cambiar="") }}
        </div>
      </div>
    </template>

    <template x-if="importado">
      <p class="text-texto">
        Se crearon <span class="font-semibold" x-text="importado.creados"></span> registros.
        <a :href="tipo.listado" class="font-semibold text-accent underline">Ver el listado</a>
      </p>
    </template>
  </section>
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/importacion.js') }}"></script>{% endblock %}
```

Notas: el macro `paginacion` hace `{{ al_cambiar }}` después de `pagina++`; con `al_cambiar=""` solo cambia la página (la lista ya está en memoria: son los errores de ESTE archivo, no un listado filtrable). Si queda un `;` suelto que Alpine rechace, pasar `al_cambiar="null"`. El `key` de la fila incluye el índice porque una fila puede tener varios errores en la misma columna `null`.

- [ ] **Step 5: Test JS**

Crear `backend/tests_js/importacion.test.mjs` (mismo armado de contexto que `dolar_masivo.test.mjs`; copiar su `cargarComponente` cambiando la ruta a `importacion.js`):

```javascript
// Tests de la pantalla de importación (backend/app/static/js/importacion.js).
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA = new URL('../app/static/js/importacion.js', import.meta.url);

function cargar(respuestas = [], confirmar = true) {
  const document = { addEventListener: () => {}, documentElement: { classList: { contains: () => false } } };
  const toasts = [];
  const window = {
    document, addEventListener: () => {}, dispatchEvent: () => {}, localStorage: {},
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    fetch: () => Promise.resolve({ status: 204 }),
  };
  const contexto = {
    window, document, FormData: class { append() {} },
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; }, setTimeout, clearTimeout,
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA, 'utf8'), contexto);
  const pedidos = [];
  window.pedir = async (url) => { pedidos.push(url); return respuestas.shift(); };
  window.toast = (mensaje, tipo = 'exito') => toasts.push({ mensaje, tipo });
  window.confirmar = async () => confirmar;
  return { window, pedidos, toasts };
}

const TIPOS = [{ valor: 'proveedores', etiqueta: 'Proveedores', listado: '/proveedores' },
               { valor: 'clientes', etiqueta: 'Clientes', listado: '/clientes' }];
const OK = { tipo: 'proveedores', filas_leidas: 3, filas_validas: 3, creados: 0, categorias_nuevas: [], errores: [], aplicado: false };

test('textos del resumen, la confirmación y el éxito', () => {
  const { window } = cargar();
  const t = window.importacionTextos;
  assert.equal(t.resumen(OK), '3 filas leídas · 3 listas para importar');
  assert.equal(t.confirmacion(OK, 'Proveedores'), 'Se van a crear 3 proveedores. Esta acción no se deshace desde el sistema.');
  assert.equal(t.exito({ ...OK, creados: 3 }, 'Clientes'), 'Listo: se crearon 3 clientes.');
});

test('importar se habilita solo con 0 errores y el mismo archivo validado', async () => {
  const { window } = cargar([OK]);
  const c = window.importacion(TIPOS);
  const archivo = { name: 'a.xlsx' };
  c.elegirArchivo(archivo);
  assert.equal(c.puedeImportar, false);
  await c.validar();
  assert.equal(c.puedeImportar, true);
  c.elegirArchivo({ name: 'b.xlsx' });           // cambió el archivo
  assert.equal(c.puedeImportar, false);
});

test('con errores no se puede importar y la tabla pagina de a 10', async () => {
  const errores = Array.from({ length: 12 }, (_, i) => ({ fila: i + 2, columna: 'nombre', error: 'x' }));
  const { window } = cargar([{ ...OK, filas_validas: 0, errores }]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  assert.equal(c.puedeImportar, false);
  assert.equal(c.erroresPagina.length, 10);
  c.pagina = 2;
  assert.equal(c.erroresPagina.length, 2);
});

test('importar usa el tipo elegido y avisa con toast', async () => {
  const { window, pedidos, toasts } = cargar([{ ...OK, tipo: 'clientes' }, { ...OK, tipo: 'clientes', creados: 3, aplicado: true }]);
  const c = window.importacion(TIPOS);
  c.elegirTipo(TIPOS[1]);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  await c.importar();
  assert.deepEqual(pedidos, ['/api/v1/importacion/clientes/validar', '/api/v1/importacion/clientes/importar']);
  assert.equal(toasts.at(-1).mensaje, 'Listo: se crearon 3 clientes.');
  assert.equal(c.importado.creados, 3);
  assert.equal(c.puedeImportar, false);
});

test('cambiar de pestaña limpia el archivo y el resultado', async () => {
  const { window } = cargar([OK]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  c.elegirTipo(TIPOS[1]);
  assert.equal(c.archivo, null);
  assert.equal(c.resultado, null);
});
```

Run: `node --check backend/app/static/js/importacion.js && node --test backend/tests_js/`
Expected: PASS.

- [ ] **Step 6: Tests de página y verificación responsive**

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_paginas_importacion.py tests/test_pages.py -v`
Expected: PASS.

Verificación visual (solo si hay navegador disponible, con la app levantada y un Admin de desarrollo YA existente — no crear usuarios): abrir `/importacion` a 320px, 768px y 1440px; sin scroll horizontal; pestañas y botones con área de toque ≥ 44px; la tabla de errores scrollea dentro de su contenedor.

- [ ] **Step 7: Suite completa y commit**

Run: `docker compose exec -T backend pytest -p no:warnings -q && node --test backend/tests_js/`
Expected: todo PASS.

```bash
git add backend/app/api/pages.py backend/app/templates/pages/importacion/index.html \
        backend/app/static/js/importacion.js backend/tests/test_paginas_importacion.py \
        backend/tests_js/importacion.test.mjs
git commit -m "$(cat <<'EOF'
feat(importacion): pantalla Importar desde Excel y tarjeta en Configuraciones

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

## Después de las tareas

1. Revisión final completa con Opus sobre `git diff dev...modulo-08-importacion` (foco: savepoints y todo-o-nada, que `validar` no deje filas ni auditoría, permisos, stock inicial, reglas no duplicadas, mensajes al usuario, zip bomb).
2. Una sola tanda de correcciones (`fix(importacion): …`).
3. Actualizar `docs/pendientes.md`: tachar el pendiente del zip bomb del módulo 03 y sumar lo que quede del 08.
4. Merge a `dev` (lo pide el usuario; nunca push).
