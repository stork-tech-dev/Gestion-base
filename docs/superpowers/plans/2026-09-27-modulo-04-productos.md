# Módulo 04 — Productos, categorías, códigos, fotos y etiquetas: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catálogo de productos: árbol de categorías (hasta 5 niveles), productos con SKU correlativo + dígito verificador módulo 11, precio de venta en pesos derivado del costo (en la moneda del proveedor) y del margen, recálculo en cascada al cambiar el dólar del proveedor, fotos (subida o webcam), código de barras Code128 y PDF de etiquetas para la Zebra GC420t; con sus pantallas.

**Architecture:** Igual que los módulos 02 y 03: API REST (`/api/v1/categorias`, `/api/v1/productos`) con services sin commit, errores tipados y auditoría en la misma transacción; pantallas Jinja + un componente Alpine por pantalla. Funciones puras de códigos en `core/codigos.py`; PDF por `app/reports/pdf.py::imprimir` (única vía de WeasyPrint). El service de proveedores ya llama a `app.services.productos.recalcular_precios_de_proveedor(db, proveedor_id)` en cada cambio real de dólar (import local): este módulo solo tiene que definirla.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (SQL a mano), PostgreSQL 15, python-barcode 0.15.1 (ya instalado), WeasyPrint 63.1 (ya instalado, con sus librerías en el Dockerfile), Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/04_productos.md` + `CLAUDE.md` + `docs/pendientes.md` ("Patrones que 03-09 deben copiar").

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `modulo-04-productos`. UN commit por tarea: `feat(productos): …` (o `fix(…): …`) + línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (EXACTAMENTE esa línea, no el nombre del modelo que implementa). NUNCA push, amend, reset, rebase, merge ni checkout de otra rama. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo** para verificar: alcanza con los tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest -p no:warnings`, suite completa antes de cada commit). JS: `node --check` de cada archivo tocado y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores con `DatoInvalido` (400) / `SinPermiso` (403) / `NoEncontrado` (404) / `ReglaDeNegocio` (409); auditoría con `registrar_auditoria` y `estado_anterior = snapshot(obj)` tomado ANTES del cambio. **Validar todo antes de modificar cualquier objeto** (si una validación falla, el objeto de la sesión queda intacto). Routers hacen `db.commit()`.
- Filtros de texto con `filtro_texto` (sin mayúsculas ni tildes). Montos `Decimal`: `redondear` (half-up) y `redondear_hacia_arriba` (CEIL al múltiplo) de `core/utils.py`.
- Límites numéricos contra las columnas NUMERIC (nunca dejar que un valor enorme llegue a la base: 400, no 500).
- Pantallas: `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; `x-html` solo con datos pasados por `escaparHtml`/`estadoHtml`; escrituras con `pedir()`; listados con `ultimaRespuesta()`; toda carga asíncrona que pueda pisar a otra (abrir un producto mientras carga otro) se secuencia con su propio `ultimaRespuesta()` **y** se descarta si el id del formulario cambió; `erroresDeCampos()` para 422; `confirmar()` antes de acciones destructivas; reusar macros de `templates/components/`; modales solo se cierran con la X; mobile-first, áreas táctiles ≥44px (`min-h-toque`), tablas dentro de `overflow-x-auto`.
- Montos en la UI: pesos con `pesos()`; dólares con `dolares()` (ya existe en app.js y agrega "US$ ").

## Desvíos deliberados respecto del spec

1. **Todo lo que depende del stock queda para el módulo 05** (la columna `stock` recién se crea ahí): `stock_inicial` en el alta, la columna Stock y `bajo_minimo` del listado, el toggle "Stock 0", sus checkboxes y "Desactivar seleccionados". Se agrega una entrada en `docs/pendientes.md` para que el plan del 05 lo incluya.
2. **Dígito verificador:** el spec dice "resto 0 → '0', 10 → 'X', si no 11 − resto", que con resto 1 daría "10" (dos caracteres). Se usa el módulo 11 estándar sobre `v = 11 − resto`: `v = 11 → '0'`, `v = 10 → 'X'`, si no `str(v)` (siempre un carácter).
3. **La categoría de un producto tiene que ser una hoja** (sin subcategorías) al crear o al cambiarle la categoría: el backend lo exige (409), no solo la UI.
4. **Nombre de categoría único entre hermanas sin mayúsculas ni tildes** (validación del service con mensaje claro); el índice único de la base es exacto `(parent_id, nombre) NULLS NOT DISTINCT`.
5. **El recálculo en cascada por cambio de dólar no audita producto por producto:** lo cubre el registro `dolar.cambio` del proveedor (misma transacción). La edición de costo o margen sí audita el producto con costo, margen y precio antes/después.
6. **Etiquetas:** tope de 1000 etiquetas por PDF (409) para que un pedido no tumbe el servidor.
7. `ProductoResponse.categoria` es `{id, nombre, camino}` (camino "Ropa > Remeras > Lisas"); el detalle (`GET /{id}`) agrega `fotos`.

---

## File Structure

```
backend/app/core/codigos.py                         (new) Task 1
backend/tests/test_codigos.py                       (new) Task 1
backend/migrations/versions/0004_productos.py       (new) Task 2
backend/app/models/productos.py, __init__.py        (new/mod) Task 2
backend/tests/test_modelo_productos.py              (new) Task 2
backend/app/schemas/categorias.py                   (new) Task 3
backend/app/services/categorias.py                  (new) Task 3
backend/tests/test_categorias.py                    (new) Task 3
backend/app/schemas/productos.py                    (new) Task 4 (+5)
backend/app/services/productos.py                   (new) Task 4 (+5)
backend/tests/test_productos.py                     (new) Task 4
backend/tests/test_productos_busqueda.py            (new) Task 5
backend/app/services/producto_fotos.py              (new) Task 6
backend/tests/test_producto_fotos.py                (new) Task 6
backend/app/reports/pdf.py, etiquetas_pdf.py        (new) Task 7
backend/app/templates/reports/etiquetas.html        (new) Task 7
backend/tests/test_etiquetas.py                     (new) Task 7
backend/app/api/v1/categorias.py, productos.py, __init__.py   (new/mod) Task 8
backend/tests/test_categorias_api.py, test_productos_api.py   (new) Task 8
backend/app/api/pages.py                            (mod) Tasks 9, 11
backend/app/templates/pages/categorias/arbol.html, static/js/categorias.js   (new) Task 9
backend/tests/test_paginas_productos.py             (new) Tasks 9-11
backend/app/templates/components/producto_form.html, static/js/producto_form.js   (new) Task 10
backend/tests_js/producto_form.test.mjs             (new) Task 10
backend/app/templates/pages/productos/listado.html, _modal_ficha.html, static/js/productos.js   (new) Task 11
docs/pendientes.md                                  (mod) Task 11
```

---

### Task 1: Funciones puras de códigos (`core/codigos.py`)

**Files:**
- Create: `backend/app/core/codigos.py`
- Test: `backend/tests/test_codigos.py`

**Interfaces:**
- Produces: `CodigoInvalido(ValueError)`, `MAXIMO_SKU = 675324`, `codificar_sku(n: int) -> str`, `decodificar_sku(sku: str) -> int`, `digito_verificador(codigo: str) -> str` (un carácter '0'-'9' o 'X'), `codigo_es_valido(codigo_con_verificador: str) -> bool`, `cuit_es_valido(cuit: str) -> bool` (acepta guiones y espacios).

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_codigos.py`:

```python
import pytest

from app.core.codigos import (
    MAXIMO_SKU,
    CodigoInvalido,
    codificar_sku,
    codigo_es_valido,
    cuit_es_valido,
    decodificar_sku,
    digito_verificador,
)


@pytest.mark.parametrize("n, sku", [(1, "AA001"), (999, "AA999"), (1000, "AB001"), (26 * 999, "AZ999"),
                                     (26 * 999 + 1, "BA001"), (MAXIMO_SKU, "ZZ999")])
def test_codificar_y_decodificar_sku(n, sku):
    assert codificar_sku(n) == sku
    assert decodificar_sku(sku) == n


@pytest.mark.parametrize("n", [0, -1, MAXIMO_SKU + 1])
def test_sku_fuera_de_rango(n):
    with pytest.raises(CodigoInvalido):
        codificar_sku(n)


@pytest.mark.parametrize("sku", ["AA000", "A0001", "AAA01", "aa001x", "", "AA1000"])
def test_decodificar_sku_invalido(sku):
    with pytest.raises(CodigoInvalido):
        decodificar_sku(sku)


def test_decodificar_acepta_minusculas():
    assert decodificar_sku("ab001") == 1000


@pytest.mark.parametrize("codigo, digito", [
    ("AB123", "1"),   # 3·2 + 2·3 + 1·4 + 11·5 + 10·6 = 131; 131 % 11 = 10; 11 − 10 = 1
    ("AA001", "9"),   # 112 % 11 = 2 → 9
    ("AA006", "X"),   # 122 % 11 = 1 → 10 → X
    ("AA000", "0"),   # 110 % 11 = 0 → 11 → 0
])
def test_digito_verificador(codigo, digito):
    assert digito_verificador(codigo) == digito


def test_verificador_siempre_un_caracter():
    for n in range(1, 3000):
        assert len(digito_verificador(codificar_sku(n))) == 1


def test_codigo_es_valido():
    assert codigo_es_valido("AB1231")
    assert codigo_es_valido("ab1231")
    assert codigo_es_valido("AA006X") and codigo_es_valido("aa006x")
    assert not codigo_es_valido("AB1232")
    assert not codigo_es_valido("AB123")      # sin verificador: el último carácter no verifica
    assert not codigo_es_valido("")
    assert not codigo_es_valido("A")
    assert not codigo_es_valido("AB-231")


@pytest.mark.parametrize("cuit, valido", [
    ("20172543597", True),     # 136 % 11 = 4 → 7
    ("20-17254359-7", True),
    ("20 17254359 7", True),
    ("20172543598", False),    # dígito incorrecto
    ("2017254359", False),     # 10 dígitos
    ("2017254359A", False),
    ("", False),
])
def test_cuit(cuit, valido):
    assert cuit_es_valido(cuit) is valido


def test_cuit_con_verificador_diez_es_invalido():
    # Buscamos un prefijo cuyo verificador daría 10: ese CUIT no existe.
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    for n in range(10**9, 10**9 + 500):
        prefijo = f"2{n:09d}"[:10]
        suma = sum(int(d) * p for d, p in zip(prefijo, pesos))
        if 11 - suma % 11 == 10:
            assert not any(cuit_es_valido(prefijo + str(d)) for d in range(10))
            return
    pytest.fail("no se encontró un prefijo con verificador 10")
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec -T backend pytest tests/test_codigos.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementación** — `backend/app/core/codigos.py`:

```python
"""Funciones puras de códigos: SKU correlativo, dígito verificador módulo 11
(código de etiqueta) y CUIT. Sin base de datos: se testean aisladas."""
import re
import string

LETRAS = string.ascii_uppercase
NUMEROS_POR_BLOQUE = 999                       # 001..999 por cada par de letras
MAXIMO_SKU = len(LETRAS) ** 2 * NUMEROS_POR_BLOQUE   # 675.324 → ZZ999
_PATRON_SKU = re.compile(r"^[A-Z]{2}\d{3}$")
_ALFABETO = string.digits + LETRAS             # base36: dígitos = su valor, letras desde 10
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


class CodigoInvalido(ValueError):
    """SKU fuera de rango o con formato inválido."""


def codificar_sku(n: int) -> str:
    """Correlativo de la SEQUENCE → 2 letras + 3 dígitos (1 → AA001, 1000 → AB001)."""
    if not 1 <= n <= MAXIMO_SKU:
        raise CodigoInvalido("Se agotaron los códigos de producto disponibles.")
    bloque, numero = divmod(n - 1, NUMEROS_POR_BLOQUE)
    return f"{LETRAS[bloque // len(LETRAS)]}{LETRAS[bloque % len(LETRAS)]}{numero + 1:03d}"


def decodificar_sku(sku: str) -> int:
    """Inverso de codificar_sku."""
    sku = (sku or "").strip().upper()
    if not _PATRON_SKU.match(sku) or sku[2:] == "000":
        raise CodigoInvalido(f"'{sku}' no es un SKU válido.")
    bloque = LETRAS.index(sku[0]) * len(LETRAS) + LETRAS.index(sku[1])
    return bloque * NUMEROS_POR_BLOQUE + int(sku[2:])


def digito_verificador(codigo: str) -> str:
    """Módulo 11 sobre el código en base36, pesos 2..7 cíclicos desde la derecha.
    v = 11 − (suma % 11): 11 → '0', 10 → 'X', si no el dígito."""
    suma = 0
    for posicion, caracter in enumerate(reversed(codigo.upper())):
        valor = _ALFABETO.index(caracter)
        suma += valor * (2 + posicion % 6)
    v = 11 - suma % 11
    if v == 11:
        return "0"
    if v == 10:
        return "X"
    return str(v)


def codigo_es_valido(codigo_con_verificador: str) -> bool:
    """¿El último carácter es el verificador del resto? (lo tipeado o escaneado)."""
    texto = (codigo_con_verificador or "").strip().upper()
    if len(texto) < 2 or any(c not in _ALFABETO for c in texto):
        return False
    return digito_verificador(texto[:-1]) == texto[-1]


def cuit_es_valido(cuit: str) -> bool:
    """11 dígitos (se ignoran guiones y espacios); verificador módulo 11 con
    pesos 5,4,3,2,7,6,5,4,3,2. v = 11 → 0; v = 10 → CUIT inválido."""
    digitos = re.sub(r"[\s-]", "", cuit or "")
    if len(digitos) != 11 or not digitos.isdigit():
        return False
    suma = sum(int(d) * p for d, p in zip(digitos[:10], _PESOS_CUIT))
    v = 11 - suma % 11
    if v == 11:
        v = 0
    if v == 10:
        return False
    return v == int(digitos[10])
```

- [ ] **Step 4: Correr y ver que pasa** — el archivo y la suite completa.

- [ ] **Step 5: Commit** — `feat(productos): funciones puras de SKU, dígito verificador y CUIT`.

---

### Task 2: Migración 0004 y modelos (categorías, productos, fotos)

**Files:**
- Create: `backend/migrations/versions/0004_productos.py`, `backend/app/models/productos.py`
- Modify: `backend/app/models/__init__.py` (exportar y sumar a `__all__`)
- Test: `backend/tests/test_modelo_productos.py`

**Interfaces:**
- Consumes: `Base`, `enum_db` (`app/models/tipos.py`), `Proveedor`, `Moneda`, `redondear`.
- Produces: `NIVEL_MAXIMO = 5`, `TemporadaProducto` (`ATEMPORAL="atemporal"`, `OTONO_INVIERNO="otoño_invierno"`, `PRIMAVERA_VERANO="primavera_verano"`), modelos `Categoria` (`id, nombre, nivel, parent_id, orden, created_at, updated_at`), `Producto` (todas las columnas del spec; relaciones `categoria`, `proveedor`, `fotos` ordenadas por `orden, id`; propiedades `codigo_con_verificador`, `moneda`, `foto_principal_url`, `costo_en_pesos`), `ProductoFoto` (`id, producto_id, url, es_principal, orden, created_at`). SEQUENCE `productos_sku_seq`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_modelo_productos.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Categoria, Moneda, Producto, ProductoFoto, Proveedor, TemporadaProducto


def _base(db):
    raiz = Categoria(nombre="Ropa", nivel=1, parent_id=None)
    db.add(raiz)
    db.flush()
    hoja = Categoria(nombre="Remeras", nivel=2, parent_id=raiz.id)
    pesos = Proveedor(nombre="Textil Pesos", moneda=Moneda.ARS)
    dolares = Proveedor(nombre="Import Dólar", moneda=Moneda.USD, dolar_actual=Decimal("1000.50"))
    db.add_all([hoja, pesos, dolares])
    db.flush()
    return hoja, pesos, dolares


def _producto(hoja, proveedor, **extra):
    datos = dict(sku="AA001", verificador="9", descripcion="Remera lisa roja", categoria_id=hoja.id,
                 proveedor_id=proveedor.id, costo=Decimal("10.00"), margen=Decimal("100"),
                 precio_venta=Decimal("20.00"))
    datos.update(extra)
    return Producto(**datos)


def test_producto_y_propiedades(db):
    hoja, _, dolares = _base(db)
    p = _producto(hoja, dolares)
    db.add(p)
    db.flush()
    db.refresh(p)
    assert p.temporada is TemporadaProducto.ATEMPORAL and p.activo and not p.stock_infinito
    assert p.descuento_producto == Decimal("0")
    assert p.codigo_con_verificador == "AA0019"
    assert p.moneda is Moneda.USD
    assert p.costo_en_pesos == Decimal("10005.00")
    assert p.foto_principal_url is None
    assert db.execute(text("SELECT temporada::text FROM productos WHERE id = :i"), {"i": p.id}).scalar_one() == "atemporal"


def test_costo_en_pesos_de_proveedor_en_pesos(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos, costo=Decimal("1234.56"))
    db.add(p)
    db.flush()
    db.refresh(p)
    assert p.moneda is Moneda.ARS and p.costo_en_pesos == Decimal("1234.56")


def test_foto_principal_url(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos)
    db.add(p)
    db.flush()
    db.add_all([ProductoFoto(producto_id=p.id, url="/uploads/productos/b.jpg", orden=2),
                ProductoFoto(producto_id=p.id, url="/uploads/productos/a.jpg", orden=1)])
    db.flush()
    db.refresh(p)
    assert p.foto_principal_url == "/uploads/productos/a.jpg"   # sin principal: la primera por orden
    p.fotos[1].es_principal = True
    db.flush()
    db.refresh(p)
    assert p.foto_principal_url == "/uploads/productos/b.jpg"


def test_una_sola_foto_principal(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos)
    db.add(p)
    db.flush()
    db.add_all([ProductoFoto(producto_id=p.id, url="/u/1.jpg", es_principal=True),
                ProductoFoto(producto_id=p.id, url="/u/2.jpg", es_principal=True)])
    with pytest.raises(IntegrityError):
        db.flush()


def test_descripcion_unica_por_categoria_y_proveedor_sin_tildes(db):
    hoja, pesos, dolares = _base(db)
    db.add(_producto(hoja, pesos, descripcion="Pantalón azul"))
    db.flush()
    db.add(_producto(hoja, dolares, sku="AA002", descripcion="pantalon AZUL"))   # otro proveedor: ok
    db.flush()
    db.add(_producto(hoja, pesos, sku="AA003", descripcion="PANTALON azul"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("campo, valor", [
    ("costo", Decimal("0")), ("margen", Decimal("-1")), ("margen", Decimal("1000.01")),
    ("precio_venta", Decimal("-1")), ("descuento_producto", Decimal("100.01")), ("peso_gramos", Decimal("0")),
])
def test_checks_de_productos(db, campo, valor):
    hoja, pesos, _ = _base(db)
    db.add(_producto(hoja, pesos, **{campo: valor}))
    with pytest.raises(IntegrityError):
        db.flush()


def test_sku_unico(db):
    hoja, pesos, _ = _base(db)
    db.add(_producto(hoja, pesos))
    db.flush()
    db.add(_producto(hoja, pesos, descripcion="Otra"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("nivel, con_padre", [(1, True), (2, False), (0, False), (6, True)])
def test_check_de_nivel_de_categoria(db, nivel, con_padre):
    raiz = Categoria(nombre="Raíz", nivel=1)
    db.add(raiz)
    db.flush()
    db.add(Categoria(nombre="Mal", nivel=nivel, parent_id=raiz.id if con_padre else None))
    with pytest.raises(IntegrityError):
        db.flush()


def test_categorias_hermanas_con_mismo_nombre(db):
    db.add(Categoria(nombre="Ropa", nivel=1))
    db.flush()
    db.add(Categoria(nombre="Ropa", nivel=1))          # NULLS NOT DISTINCT: dos raíces iguales chocan
    with pytest.raises(IntegrityError):
        db.flush()


def test_secuencia_del_sku(db):
    a = db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one()
    b = db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one()
    assert b == a + 1
```

- [ ] **Step 2: Correr y ver que falla** — `ImportError`.

- [ ] **Step 3: Migración** — `backend/migrations/versions/0004_productos.py` (revision "0004", down_revision "0003"; seguí el estilo de la 0003):

```python
"""Categorías (árbol de 5 niveles), productos y sus fotos.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE categorias (
            id         BIGSERIAL PRIMARY KEY,
            nombre     VARCHAR(150) NOT NULL,
            nivel      SMALLINT NOT NULL,           -- desnormalizado a propósito (ver modelo)
            parent_id  BIGINT REFERENCES categorias (id) ON DELETE RESTRICT,
            orden      SMALLINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_categorias_nivel CHECK (nivel BETWEEN 1 AND 5),
            CONSTRAINT ck_categorias_padre CHECK (
                (nivel = 1 AND parent_id IS NULL) OR (nivel > 1 AND parent_id IS NOT NULL)
            )
        );
        CREATE INDEX ix_categorias_nombre ON categorias (nombre);
        CREATE INDEX ix_categorias_parent_id ON categorias (parent_id);
        CREATE UNIQUE INDEX uq_categorias_hermanos ON categorias (parent_id, nombre) NULLS NOT DISTINCT;

        CREATE TYPE temporada_producto AS ENUM ('atemporal', 'otoño_invierno', 'primavera_verano');
        -- Correlativo del SKU: nunca MAX()+1 (dos altas simultáneas chocarían).
        CREATE SEQUENCE productos_sku_seq START 1;

        CREATE TABLE productos (
            id                 BIGSERIAL PRIMARY KEY,
            sku                VARCHAR(5) NOT NULL,
            verificador        VARCHAR(1) NOT NULL,
            sku_proveedor      VARCHAR(30),
            descripcion        TEXT NOT NULL,
            categoria_id       BIGINT NOT NULL REFERENCES categorias (id) ON DELETE RESTRICT,
            proveedor_id       BIGINT NOT NULL REFERENCES proveedores (id) ON DELETE RESTRICT,
            costo              NUMERIC(10,2) NOT NULL,   -- en la moneda del proveedor
            margen             NUMERIC(6,2) NOT NULL,
            precio_venta       NUMERIC(10,2) NOT NULL,   -- en pesos; desnormalizado (ver modelo)
            descuento_producto NUMERIC(5,2) NOT NULL DEFAULT 0,
            peso_gramos        NUMERIC(8,2),
            temporada          temporada_producto NOT NULL DEFAULT 'atemporal',
            ubicacion_deposito VARCHAR(100),
            stock_infinito     BOOLEAN NOT NULL DEFAULT FALSE,
            activo             BOOLEAN NOT NULL DEFAULT TRUE,
            created_at         TIMESTAMP NOT NULL DEFAULT now(),
            updated_at         TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_productos_sku UNIQUE (sku),
            CONSTRAINT ck_productos_costo CHECK (costo > 0),
            CONSTRAINT ck_productos_margen CHECK (margen BETWEEN 0 AND 1000),
            CONSTRAINT ck_productos_precio CHECK (precio_venta >= 0),
            CONSTRAINT ck_productos_descuento CHECK (descuento_producto BETWEEN 0 AND 100),
            CONSTRAINT ck_productos_peso CHECK (peso_gramos IS NULL OR peso_gramos > 0)
        );
        CREATE INDEX ix_productos_sku_proveedor ON productos (sku_proveedor);
        CREATE INDEX ix_productos_categoria_id ON productos (categoria_id);
        CREATE INDEX ix_productos_proveedor_id ON productos (proveedor_id);
        CREATE INDEX ix_productos_temporada ON productos (temporada);
        CREATE INDEX ix_productos_activo ON productos (activo);
        CREATE INDEX ix_productos_descripcion_lower ON productos (lower(descripcion));
        -- Misma normalización que core/utils.sin_tildes_sql.
        CREATE UNIQUE INDEX uq_productos_descripcion_por_categoria_y_proveedor ON productos (
            lower(translate(descripcion, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')), categoria_id, proveedor_id
        );

        CREATE TABLE producto_fotos (
            id           BIGSERIAL PRIMARY KEY,
            producto_id  BIGINT NOT NULL REFERENCES productos (id) ON DELETE CASCADE,
            url          VARCHAR(255) NOT NULL,
            es_principal BOOLEAN NOT NULL DEFAULT FALSE,
            orden        SMALLINT NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_producto_fotos_orden CHECK (orden >= 0)
        );
        CREATE INDEX ix_producto_fotos_producto_id ON producto_fotos (producto_id);
        CREATE UNIQUE INDEX uq_producto_fotos_principal ON producto_fotos (producto_id) WHERE es_principal;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE producto_fotos;
        DROP TABLE productos;
        DROP SEQUENCE productos_sku_seq;
        DROP TYPE temporada_producto;
        DROP TABLE categorias;
        """
    )
```

- [ ] **Step 4: Modelos** — `backend/app/models/productos.py`:

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.utils import redondear
from app.models.proveedores import Moneda, Proveedor
from app.models.tipos import enum_db

NIVEL_MAXIMO = 5


class TemporadaProducto(str, Enum):
    ATEMPORAL = "atemporal"
    OTONO_INVIERNO = "otoño_invierno"
    PRIMAVERA_VERANO = "primavera_verano"


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    # Desnormalizado a propósito: se deduce del padre, pero guardarlo permite
    # el CHECK 1..5 y filtrar por nivel sin recorrer el árbol. Mover una
    # categoría actualiza el nivel de toda su rama.
    nivel: Mapped[int] = mapped_column(SmallInteger)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(5))
    # Módulo 11 sobre el SKU; se calcula una sola vez al crear y nunca cambia.
    verificador: Mapped[str] = mapped_column(String(1))
    sku_proveedor: Mapped[str | None] = mapped_column(String(30))
    descripcion: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"))
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedores.id", ondelete="RESTRICT"))
    # En la moneda del proveedor (no cambia: el proveedor del producto no se edita
    # y la moneda de un proveedor con productos tampoco).
    costo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    margen: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    # Desnormalizado (en pesos): CEIL(costo × dólar (o 1) × (1 + margen/100), redondeo).
    # Se guarda para listar/filtrar/vender sin recalcular; se recalcula en cascada
    # al cambiar el dólar del proveedor y al editar costo o margen.
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    descuento_producto: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    peso_gramos: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    temporada: Mapped[TemporadaProducto] = mapped_column(
        enum_db(TemporadaProducto, "temporada_producto"), default=TemporadaProducto.ATEMPORAL
    )
    ubicacion_deposito: Mapped[str | None] = mapped_column(String(100))
    stock_infinito: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    categoria: Mapped[Categoria] = relationship(lazy="joined")
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    fotos: Mapped[list["ProductoFoto"]] = relationship(
        order_by="(ProductoFoto.orden, ProductoFoto.id)", lazy="selectin", passive_deletes=True
    )

    @property
    def codigo_con_verificador(self) -> str:
        return f"{self.sku}{self.verificador}"

    @property
    def moneda(self) -> Moneda:
        return self.proveedor.moneda

    @property
    def foto_principal_url(self) -> str | None:
        principal = next((f for f in self.fotos if f.es_principal), None)
        foto = principal or (self.fotos[0] if self.fotos else None)
        return foto.url if foto else None

    @property
    def costo_en_pesos(self) -> Decimal:
        """Sin CEIL: la venta lo congela para la rentabilidad."""
        if self.proveedor.moneda is Moneda.USD:
            return redondear(self.costo * self.proveedor.dolar_actual)
        return redondear(self.costo)


class ProductoFoto(Base):
    __tablename__ = "producto_fotos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    producto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("productos.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(255))
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```
Exportar `NIVEL_MAXIMO`, `TemporadaProducto`, `Categoria`, `Producto`, `ProductoFoto` en `app/models/__init__.py`. Si el `order_by` como string con tupla no funciona en esta versión de SQLAlchemy, usar `order_by=lambda: (ProductoFoto.orden, ProductoFoto.id)` o `[ProductoFoto.orden, ProductoFoto.id]` declarando la relación después de la clase; anotarlo en el reporte.

- [ ] **Step 5: Migrar y correr** — `docker compose restart backend`, `alembic current` → 0004 (head); test del modelo; `alembic downgrade -1 && alembic upgrade head`; suite completa.

- [ ] **Step 6: Commit** — `feat(productos): migración 0004 y modelos de categorías, productos y fotos`.

---

### Task 3: Categorías (schemas + service)

**Files:**
- Create: `backend/app/schemas/categorias.py`, `backend/app/services/categorias.py`
- Test: `backend/tests/test_categorias.py`

**Interfaces:**
- Consumes: `Categoria`, `Producto`, `NIVEL_MAXIMO`, `registrar_auditoria`, `snapshot`, `normalizar_texto`, `sin_tildes`, `sin_tildes_sql`, `filtro_texto`, errores.
- Produces (schemas): `CategoriaCrear {nombre (1-150), parent_id: int|None, orden: int = 0 (0..32767)}`, `CategoriaEditar {nombre, orden}`, `CategoriaMover {parent_id: int|None}`, `CategoriaResponse {id, nombre, nivel, parent_id, orden}` (from_attributes), `CategoriaNodo {id, nombre, nivel, parent_id, orden, hijos: list[CategoriaNodo]}`.
- Produces (service): `obtener_categoria(db, id)`, `listar_categorias(db, *, nombre=None, nivel=None, parent_id=None) -> list[Categoria]`, `arbol(db) -> list[dict]` (nodos con `hijos`), `rama_de_ids(db, categoria_id) -> list[int]`, `caminos(db) -> dict[int, str]` ("Ropa > Remeras"), `es_hoja(db, categoria_id) -> bool`, `crear_categoria(db, autor, datos, ip)`, `editar_categoria(db, autor, categoria, datos, ip)`, `mover_categoria(db, autor, categoria, nuevo_parent_id, ip)`, `eliminar_categoria(db, autor, categoria, ip)`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_categorias.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, Categoria, Moneda, Producto, Proveedor
from app.schemas.categorias import CategoriaCrear, CategoriaEditar
from app.services import categorias as servicio


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


def _crear(db, autor, nombre, parent=None, orden=0):
    return servicio.crear_categoria(
        db, autor, CategoriaCrear(nombre=nombre, parent_id=parent.id if parent else None, orden=orden), None
    )


def _cadena(db, autor, niveles):
    actual = None
    creadas = []
    for i in range(niveles):
        actual = _crear(db, autor, f"Nivel {i + 1}", actual)
        creadas.append(actual)
    return creadas


def test_niveles_y_auditoria(db, admin):
    ropa = _crear(db, admin, "  Ropa  ")
    remeras = _crear(db, admin, "Remeras", ropa)
    assert (ropa.nombre, ropa.nivel, ropa.parent_id) == ("Ropa", 1, None)
    assert (remeras.nivel, remeras.parent_id) == (2, ropa.id)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.crear", Auditoria.entidad_id == remeras.id))


def test_maximo_cinco_niveles(db, admin):
    cadena = _cadena(db, admin, 5)
    with pytest.raises(ReglaDeNegocio) as error:
        _crear(db, admin, "Sexto", cadena[-1])
    assert "5 niveles" in error.value.mensaje


def test_padre_inexistente(db, admin):
    with pytest.raises(NoEncontrado):
        servicio.crear_categoria(db, admin, CategoriaCrear(nombre="X", parent_id=999999), None)


def test_nombre_unico_entre_hermanas(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Remeras", ropa)
    with pytest.raises(ReglaDeNegocio):
        _crear(db, admin, "remeras", ropa)
    otra = _crear(db, admin, "Calzado")
    _crear(db, admin, "Remeras", otra)          # otro padre: se puede
    with pytest.raises(ReglaDeNegocio):
        _crear(db, admin, "ROPA")               # raíces también son hermanas


def test_editar(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Calzado")
    servicio.editar_categoria(db, admin, ropa, CategoriaEditar(nombre="Indumentaria", orden=3), None)
    assert (ropa.nombre, ropa.orden) == ("Indumentaria", 3)
    with pytest.raises(ReglaDeNegocio):
        servicio.editar_categoria(db, admin, ropa, CategoriaEditar(nombre="calzado", orden=0), None)
    assert ropa.nombre == "Indumentaria"        # validar antes de modificar


def test_mover_actualiza_niveles_de_la_rama(db, admin):
    a = _crear(db, admin, "A")
    b = _crear(db, admin, "B")
    b1 = _crear(db, admin, "B1", b)
    b2 = _crear(db, admin, "B2", b1)
    servicio.mover_categoria(db, admin, b, a.id, None)
    assert (b.nivel, b1.nivel, b2.nivel) == (2, 3, 4)
    servicio.mover_categoria(db, admin, b, None, None)
    assert (b.nivel, b1.nivel, b2.nivel, b.parent_id) == (1, 2, 3, None)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.mover", Auditoria.entidad_id == b.id))


def test_mover_prohibido(db, admin):
    cadena = _cadena(db, admin, 4)       # niveles 1..4
    otra = _cadena(db, admin, 1)[0]
    otra_hija = _crear(db, admin, "Hija", otra)
    with pytest.raises(ReglaDeNegocio):
        servicio.mover_categoria(db, admin, cadena[0], cadena[0].id, None)      # a sí misma
    with pytest.raises(ReglaDeNegocio):
        servicio.mover_categoria(db, admin, cadena[0], cadena[2].id, None)      # dentro de su rama
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.mover_categoria(db, admin, cadena[0], otra_hija.id, None)      # rama de 4 bajo nivel 2 → 6
    assert "5 niveles" in error.value.mensaje
    assert cadena[0].parent_id is None and cadena[0].nivel == 1


def test_eliminar(db, admin):
    ropa = _crear(db, admin, "Ropa")
    remeras = _crear(db, admin, "Remeras", ropa)
    with pytest.raises(ReglaDeNegocio):
        servicio.eliminar_categoria(db, admin, ropa, None)          # tiene subcategorías
    proveedor = Proveedor(nombre="Prov cat", moneda=Moneda.ARS)
    db.add(proveedor)
    db.flush()
    db.add(Producto(sku="ZZ001", verificador="0", descripcion="Remera", categoria_id=remeras.id,
                    proveedor_id=proveedor.id, costo=Decimal("1"), margen=Decimal("0"), precio_venta=Decimal("1")))
    db.flush()
    with pytest.raises(ReglaDeNegocio):
        servicio.eliminar_categoria(db, admin, remeras, None)       # tiene productos
    calzado = _crear(db, admin, "Calzado")
    servicio.eliminar_categoria(db, admin, calzado, None)
    assert db.get(Categoria, calzado.id) is None
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.eliminar", Auditoria.entidad_id == calzado.id))


def test_arbol_rama_caminos_y_hoja(db, admin):
    ropa = _crear(db, admin, "Ropa", orden=2)
    calzado = _crear(db, admin, "Calzado", orden=1)
    remeras = _crear(db, admin, "Remeras", ropa)
    lisas = _crear(db, admin, "Lisas", remeras)
    arbol = servicio.arbol(db)
    nombres = [n["nombre"] for n in arbol]
    assert nombres.index("Calzado") < nombres.index("Ropa")          # por orden
    nodo_ropa = next(n for n in arbol if n["id"] == ropa.id)
    assert nodo_ropa["hijos"][0]["hijos"][0]["nombre"] == "Lisas"
    assert set(servicio.rama_de_ids(db, ropa.id)) == {ropa.id, remeras.id, lisas.id}
    assert servicio.rama_de_ids(db, calzado.id) == [calzado.id]
    assert servicio.caminos(db)[lisas.id] == "Ropa > Remeras > Lisas"
    assert servicio.es_hoja(db, lisas.id) and not servicio.es_hoja(db, ropa.id)


def test_listar_con_filtros(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Remeras estampadas", ropa)
    _crear(db, admin, "Calzado")
    assert [c.nombre for c in servicio.listar_categorias(db, nombre="ESTAMPADAS")] == ["Remeras estampadas"]
    assert {c.nombre for c in servicio.listar_categorias(db, nivel=1)} >= {"Ropa", "Calzado"}
    assert [c.nombre for c in servicio.listar_categorias(db, parent_id=ropa.id)] == ["Remeras estampadas"]


def test_nombre_vacio(db, admin):
    with pytest.raises(DatoInvalido):
        _crear(db, admin, "   ")
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Schemas** — `backend/app/schemas/categorias.py`:

```python
from pydantic import BaseModel, ConfigDict, Field


class CategoriaEditar(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    orden: int = Field(default=0, ge=0, le=32767)


class CategoriaCrear(CategoriaEditar):
    parent_id: int | None = None


class CategoriaMover(BaseModel):
    parent_id: int | None = None


class CategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    nivel: int
    parent_id: int | None
    orden: int


class CategoriaNodo(CategoriaResponse):
    hijos: list["CategoriaNodo"] = []
```

- [ ] **Step 4: Service** — `backend/app/services/categorias.py`:

```python
"""Árbol de categorías (hasta NIVEL_MAXIMO niveles). La tabla es chica: el árbol
se arma en memoria con una sola query."""
from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, normalizar_texto, sin_tildes, sin_tildes_sql
from app.models import NIVEL_MAXIMO, Categoria, Producto

MENSAJE_NIVELES = f"Se permiten hasta {NIVEL_MAXIMO} niveles de categorías."


def obtener_categoria(db, categoria_id: int) -> Categoria:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise NoEncontrado("Categoría no encontrada")
    return categoria


def _todas(db) -> list[Categoria]:
    return list(db.scalars(select(Categoria).order_by(Categoria.nivel, Categoria.orden, func.lower(Categoria.nombre))).all())


def listar_categorias(db, *, nombre=None, nivel=None, parent_id=None) -> list[Categoria]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(Categoria.nombre, nombre))
    if nivel is not None:
        condiciones.append(Categoria.nivel == nivel)
    if parent_id is not None:
        condiciones.append(Categoria.parent_id == parent_id)
    consulta = select(Categoria).where(*condiciones).order_by(Categoria.nivel, Categoria.orden, func.lower(Categoria.nombre))
    return list(db.scalars(consulta).all())


def arbol(db) -> list[dict]:
    nodos = {c.id: {"id": c.id, "nombre": c.nombre, "nivel": c.nivel, "parent_id": c.parent_id,
                    "orden": c.orden, "hijos": []} for c in _todas(db)}
    raices = []
    for nodo in nodos.values():          # _todas viene ordenada: los hijos quedan en orden
        (nodos[nodo["parent_id"]]["hijos"] if nodo["parent_id"] else raices).append(nodo)
    return raices


def _hijos_por_padre(categorias) -> dict:
    hijos: dict[int | None, list[Categoria]] = {}
    for c in categorias:
        hijos.setdefault(c.parent_id, []).append(c)
    return hijos


def rama_de_ids(db, categoria_id: int) -> list[int]:
    """La categoría y todos sus descendientes (los filtros por categoría son por rama)."""
    hijos = _hijos_por_padre(_todas(db))
    ids, pendientes = [], [categoria_id]
    while pendientes:
        actual = pendientes.pop()
        ids.append(actual)
        pendientes.extend(h.id for h in hijos.get(actual, []))
    return ids


def caminos(db) -> dict[int, str]:
    """{id: "Ropa > Remeras > Lisas"} de todas las categorías."""
    por_id = {c.id: c for c in _todas(db)}
    resultado = {}
    for c in por_id.values():
        nombres, actual = [], c
        while actual is not None:
            nombres.append(actual.nombre)
            actual = por_id.get(actual.parent_id)
        resultado[c.id] = " > ".join(reversed(nombres))
    return resultado


def es_hoja(db, categoria_id: int) -> bool:
    return db.scalar(select(Categoria.id).where(Categoria.parent_id == categoria_id).limit(1)) is None


def _nombre_libre(db, nombre: str, parent_id: int | None, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [
        func.lower(sin_tildes_sql(Categoria.nombre)) == sin_tildes(limpio).lower(),
        Categoria.parent_id.is_(None) if parent_id is None else Categoria.parent_id == parent_id,
    ]
    if excepto_id is not None:
        condiciones.append(Categoria.id != excepto_id)
    existente = db.scalar(select(Categoria).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe la categoría '{existente.nombre}' en ese nivel.")
    return limpio


def _profundidad_de_rama(db, categoria: Categoria) -> int:
    """Niveles que ocupa la rama contando la propia categoría (1 si es hoja)."""
    maximo = db.scalar(select(func.max(Categoria.nivel)).where(Categoria.id.in_(rama_de_ids(db, categoria.id))))
    return maximo - categoria.nivel + 1


def crear_categoria(db, autor, datos, ip) -> Categoria:
    nivel = 1
    if datos.parent_id is not None:
        padre = obtener_categoria(db, datos.parent_id)
        nivel = padre.nivel + 1
        if nivel > NIVEL_MAXIMO:
            raise ReglaDeNegocio(MENSAJE_NIVELES)
    categoria = Categoria(nombre=_nombre_libre(db, datos.nombre, datos.parent_id), nivel=nivel,
                          parent_id=datos.parent_id, orden=datos.orden)
    db.add(categoria)
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.crear", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def editar_categoria(db, autor, categoria: Categoria, datos, ip) -> Categoria:
    antes = snapshot(categoria)
    nombre = _nombre_libre(db, datos.nombre, categoria.parent_id, excepto_id=categoria.id)
    categoria.nombre = nombre
    categoria.orden = datos.orden
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.editar", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def mover_categoria(db, autor, categoria: Categoria, nuevo_parent_id: int | None, ip) -> Categoria:
    rama = rama_de_ids(db, categoria.id)
    nuevo_nivel = 1
    if nuevo_parent_id is not None:
        if nuevo_parent_id in rama:
            raise ReglaDeNegocio("Una categoría no puede moverse dentro de sí misma ni de su rama.")
        nuevo_nivel = obtener_categoria(db, nuevo_parent_id).nivel + 1
    if nuevo_nivel + _profundidad_de_rama(db, categoria) - 1 > NIVEL_MAXIMO:
        raise ReglaDeNegocio(MENSAJE_NIVELES)
    _nombre_libre(db, categoria.nombre, nuevo_parent_id, excepto_id=categoria.id)
    antes = snapshot(categoria)
    delta = nuevo_nivel - categoria.nivel
    categoria.parent_id = nuevo_parent_id
    for descendiente in db.scalars(select(Categoria).where(Categoria.id.in_(rama))).all():
        descendiente.nivel += delta
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.mover", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def eliminar_categoria(db, autor, categoria: Categoria, ip) -> None:
    if not es_hoja(db, categoria.id):
        raise ReglaDeNegocio("No se puede eliminar una categoría con subcategorías.")
    if db.scalar(select(Producto.id).where(Producto.categoria_id == categoria.id).limit(1)) is not None:
        raise ReglaDeNegocio("No se puede eliminar una categoría con productos (incluidos los inactivos).")
    antes = snapshot(categoria)
    categoria_id = categoria.id
    db.delete(categoria)
    db.flush()
    registrar_auditoria(db, accion="categoria.eliminar", entidad="categoria", entidad_id=categoria_id,
                        usuario_id=autor.id, estado_anterior=antes, ip_origen=ip)
```
Nota: el CHECK `(nivel = 1 AND parent_id IS NULL) OR …` se evalúa por fila al flush; al mover a raíz se cambian `parent_id` y `nivel` de la misma fila antes del flush, así que no se viola. Si el flush intermedio de la rama chocara con el CHECK, asignar primero los niveles y después `parent_id` (ambos antes del único `flush`).

- [ ] **Step 5: Correr y ver que pasa** — archivo + suite completa.

- [ ] **Step 6: Commit** — `feat(productos): árbol de categorías`.

---

### Task 4: Productos — alta, edición, estado, precio y recálculo

**Files:**
- Create: `backend/app/schemas/productos.py`, `backend/app/services/productos.py`
- Test: `backend/tests/test_productos.py`

**Interfaces:**
- Consumes: modelos, `codificar_sku`, `digito_verificador`, `obtener_configuracion(db)` (`redondeo`, `margen_default`, `descuento_maximo`), `obtener_proveedor` (services.proveedores), `servicio_categorias.obtener_categoria/es_hoja/caminos`, `capitalizar_inicial`, `redondear`, `redondear_hacia_arriba`, `sin_tildes`, `sin_tildes_sql`, `normalizar_texto`, auditoría, errores.
- Produces (schemas): `ProductoDatos`, `ProductoCrear`, `ProductoEditar`, `ProductoEstado {activo: bool}`, `CategoriaResumen {id, nombre, camino}`, `ProveedorResumen {id, nombre, moneda}`, `FotoResponse {id, url, es_principal, orden}`, `ProductoResponse` (+ `ProductoResponse.desde(producto, camino)`), `ProductoDetalle` (+ `fotos`; `ProductoDetalle.desde(producto, camino)`), `PrecioPreview {moneda, dolar_proveedor: Decimal|None, precio_venta}`.
- Produces (service): `obtener_producto(db, id)`, `calcular_precio_venta(db, costo, margen, proveedor) -> Decimal`, `precio_preview(db, proveedor_id, costo, margen) -> dict`, `crear_producto(db, autor, datos, ip)`, `editar_producto(db, autor, producto, datos, ip)`, `cambiar_estado_producto(db, autor, producto, activo, ip)`, `recalcular_precios_de_proveedor(db, proveedor_id) -> int` (cantidad actualizada), `a_respuesta(db, productos) -> list[ProductoResponse]` (una sola llamada a `caminos`), `a_detalle(db, producto) -> ProductoDetalle`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_productos.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.codigos import digito_verificador
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.models import Auditoria, ConfiguracionSistema, EstadoProveedor, Producto
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear, ProductoEditar
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


@pytest.fixture
def config(db):
    """redondeo 100, margen_default 50, descuento_maximo 30 (valores fijos para los tests)."""
    fila = db.scalar(select(ConfiguracionSistema))
    fila.redondeo, fila.margen_default, fila.descuento_maximo = Decimal("100"), Decimal("50"), Decimal("30")
    db.flush()
    return fila


@pytest.fixture
def base(db, admin, config):
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa"), None)
    remeras = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras", parent_id=ropa.id), None)
    pesos = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov pesos", moneda="ars"), None)
    dolares = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre="Prov dólares", moneda="usd", dolar_actual="1000"), None)
    return {"ropa": ropa, "hoja": remeras, "pesos": pesos, "dolares": dolares}


def _alta(db, autor, base, **extra):
    datos = {"categoria_id": base["hoja"].id, "proveedor_id": base["pesos"].id, "costo": "1000",
             "descripcion": "remera lisa roja"}
    datos.update(extra)
    return servicio.crear_producto(db, autor, ProductoCrear(**datos), None)


def _editar(db, autor, producto, **cambios):
    datos = {"categoria_id": producto.categoria_id, "costo": str(producto.costo), "margen": str(producto.margen),
             "descripcion": producto.descripcion}
    datos.update(cambios)
    return servicio.editar_producto(db, autor, producto, ProductoEditar(**datos), None)


def test_alta_genera_codigo_y_precio_en_pesos(db, admin, base):
    p = _alta(db, admin, base)
    assert len(p.sku) == 5 and p.verificador == digito_verificador(p.sku)
    assert p.descripcion == "Remera lisa roja"
    assert p.margen == Decimal("50.00")                      # margen_default
    assert p.precio_venta == Decimal("1500.00")              # 1000 × 1.5, ya múltiplo de 100
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.crear", Auditoria.entidad_id == p.id))


def test_skus_correlativos(db, admin, base):
    a = _alta(db, admin, base, descripcion="Uno")
    b = _alta(db, admin, base, descripcion="Dos")
    from app.core.codigos import decodificar_sku
    assert decodificar_sku(b.sku) == decodificar_sku(a.sku) + 1


def test_precio_en_dolares_con_ceil(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10.01", margen="10")
    # 10.01 × 1000 × 1.10 = 11011 → CEIL a 100 = 11100
    assert p.precio_venta == Decimal("11100.00")


def test_precio_preview(db, base):
    vista = servicio.precio_preview(db, base["dolares"].id, Decimal("10.01"), Decimal("10"))
    assert vista == {"moneda": "usd", "dolar_proveedor": Decimal("1000.00"), "precio_venta": Decimal("11100.00")}
    vista = servicio.precio_preview(db, base["pesos"].id, Decimal("1001"), Decimal("0"))
    assert vista == {"moneda": "ars", "dolar_proveedor": None, "precio_venta": Decimal("1100.00")}


def test_recalculo_por_cambio_de_dolar(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10", margen="0")
    otro = _alta(db, admin, base, descripcion="En pesos", costo="1000", margen="0")
    assert p.precio_venta == Decimal("10000.00")
    servicio_proveedores.cambiar_dolar(db, admin, base["dolares"], Decimal("1234"), None)
    db.refresh(p)
    assert p.precio_venta == Decimal("12400.00")             # 12340 → CEIL 100
    assert otro.precio_venta == Decimal("1000.00")
    assert servicio.recalcular_precios_de_proveedor(db, base["pesos"].id) == 0


def test_edicion_recalcula_y_audita(db, admin, base):
    p = _alta(db, admin, base, costo="1000", margen="0")
    _editar(db, admin, p, costo="2000", margen="10")
    assert p.precio_venta == Decimal("2200.00")
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "producto.editar", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior["precio_venta"] == "1000.00" and registro.estado_nuevo["precio_venta"] == "2200.00"
    assert registro.estado_anterior["costo"] == "1000.00" and registro.estado_nuevo["margen"] == "10.00"


def test_sku_y_proveedor_no_se_editan(db, admin, base):
    p = _alta(db, admin, base)
    sku, verificador, proveedor_id = p.sku, p.verificador, p.proveedor_id
    _editar(db, admin, p, descripcion="Remera lisa bordó")
    assert (p.sku, p.verificador, p.proveedor_id) == (sku, verificador, proveedor_id)
    assert "proveedor_id" not in ProductoEditar.model_fields


def test_descripcion_duplicada(db, admin, base):
    p = _alta(db, admin, base, descripcion="Remera lisa roja")
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, descripcion="REMERA LISA ROJA")
    assert p.sku in error.value.mensaje and "otro color o talle" in error.value.mensaje
    servicio.cambiar_estado_producto(db, admin, p, False, None)
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, descripcion="remera lisa roja")
    assert "está inactivo y se puede volver a activar" in error.value.mensaje
    _alta(db, admin, base, descripcion="Remera lisa roja", proveedor_id=base["dolares"].id)   # otro proveedor: ok


def test_validaciones_del_alta(db, admin, base):
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, categoria_id=base["ropa"].id)            # no es hoja
    assert "último nivel" in error.value.mensaje
    with pytest.raises(NoEncontrado):
        _alta(db, admin, base, categoria_id=999999)
    with pytest.raises(NoEncontrado):
        _alta(db, admin, base, proveedor_id=999999)
    servicio_proveedores.cambiar_estado(db, admin, base["pesos"], EstadoProveedor.DESACTIVADO, False, None)
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base)
    assert "proveedor" in error.value.mensaje.lower()


def test_descuento_maximo(db, admin, base):
    with pytest.raises(DatoInvalido) as error:
        _alta(db, admin, base, descuento_producto="30.01")
    assert "30" in error.value.mensaje
    assert _alta(db, admin, base, descuento_producto="30").descuento_producto == Decimal("30.00")


def test_stock_infinito_solo_admin(db, admin, base, crear_usuario):
    supervisor = crear_usuario("supervisor")
    with pytest.raises(SinPermiso) as error:
        _alta(db, supervisor, base, stock_infinito=True)
    assert error.value.mensaje == "El stock infinito lo define el Admin"
    p = _alta(db, admin, base, stock_infinito=True)
    _editar(db, supervisor, p, descripcion="Remera editada", stock_infinito=True)   # no cambia: se permite
    with pytest.raises(SinPermiso):
        _editar(db, supervisor, p, stock_infinito=False)
    _editar(db, supervisor, p, descripcion="Remera sin el campo")          # omitido: no cambia
    assert p.stock_infinito and p.descripcion == "Remera sin el campo"


def test_edicion_valida_antes_de_modificar(db, admin, base):
    _alta(db, admin, base, descripcion="Existente")
    p = _alta(db, admin, base, descripcion="Otra", costo="1000", margen="0")
    with pytest.raises(ReglaDeNegocio):
        _editar(db, admin, p, descripcion="existente", costo="5000")
    assert p.costo == Decimal("1000.00") and p.descripcion == "Otra" and p.precio_venta == Decimal("1000.00")


def test_estado(db, admin, base):
    p = _alta(db, admin, base)
    servicio.cambiar_estado_producto(db, admin, p, False, None)
    servicio.cambiar_estado_producto(db, admin, p, False, None)      # sin cambio: no audita
    servicio.cambiar_estado_producto(db, admin, p, True, None)
    acciones = db.scalars(select(Auditoria.accion).where(Auditoria.entidad == "producto", Auditoria.entidad_id == p.id)
                          .order_by(Auditoria.id)).all()
    assert acciones == ["producto.crear", "producto.desactivar", "producto.activar"]


def test_respuesta(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10")
    (r,) = servicio.a_respuesta(db, [p])
    assert r.codigo_con_verificador == p.sku + p.verificador and r.moneda == "usd"
    assert r.categoria.camino == "Ropa > Remeras" and r.proveedor.nombre == "Prov dólares"
    assert r.foto_url is None
    assert servicio.a_detalle(db, p).fotos == []
```
Nota: si el fixture `config` modifica la fila de configuración, lo hace dentro de la transacción del test (se revierte). Verificá que `obtener_configuracion` no la cachee entre llamadas; si la cachea, adaptá el fixture.

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Schemas** — `backend/app/schemas/productos.py`:

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Moneda, TemporadaProducto

# Topes = columnas NUMERIC: un valor enorme es 422, nunca un 500 de la base.
Costo = Field(gt=0, lt=Decimal("100000000"), decimal_places=2)


class ProductoDatos(BaseModel):
    categoria_id: int
    descripcion: str = Field(min_length=1, max_length=500)
    costo: Decimal = Costo
    sku_proveedor: str | None = Field(default=None, max_length=30)
    descuento_producto: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    peso_gramos: Decimal | None = Field(default=None, gt=0, lt=Decimal("1000000"), decimal_places=2)
    temporada: TemporadaProducto = TemporadaProducto.ATEMPORAL
    ubicacion_deposito: str | None = Field(default=None, max_length=100)
    stock_infinito: bool = False


class ProductoCrear(ProductoDatos):
    proveedor_id: int
    margen: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=2)   # None → margen_default


class ProductoEditar(ProductoDatos):
    # SKU, verificador y proveedor no se editan.
    margen: Decimal = Field(ge=0, le=1000, decimal_places=2)
    # None = no cambia (un cliente que omite el campo no apaga el stock infinito).
    stock_infinito: bool | None = None


class ProductoEstado(BaseModel):
    activo: bool


class CategoriaResumen(BaseModel):
    id: int
    nombre: str
    camino: str


class ProveedorResumen(BaseModel):
    id: int
    nombre: str
    moneda: Moneda


class FotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    es_principal: bool
    orden: int


class ProductoResponse(BaseModel):
    id: int
    sku: str
    verificador: str
    codigo_con_verificador: str
    sku_proveedor: str | None
    descripcion: str
    categoria: CategoriaResumen
    proveedor: ProveedorResumen
    moneda: Moneda
    costo: Decimal
    margen: Decimal
    precio_venta: Decimal
    descuento_producto: Decimal
    peso_gramos: Decimal | None
    temporada: TemporadaProducto
    ubicacion_deposito: str | None
    stock_infinito: bool
    activo: bool
    foto_url: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def _campos(cls, producto, camino: str) -> dict:
        return dict(
            id=producto.id, sku=producto.sku, verificador=producto.verificador,
            codigo_con_verificador=producto.codigo_con_verificador, sku_proveedor=producto.sku_proveedor,
            descripcion=producto.descripcion,
            categoria=CategoriaResumen(id=producto.categoria.id, nombre=producto.categoria.nombre, camino=camino),
            proveedor=ProveedorResumen(id=producto.proveedor.id, nombre=producto.proveedor.nombre,
                                       moneda=producto.proveedor.moneda),
            moneda=producto.moneda, costo=producto.costo, margen=producto.margen,
            precio_venta=producto.precio_venta, descuento_producto=producto.descuento_producto,
            peso_gramos=producto.peso_gramos, temporada=producto.temporada,
            ubicacion_deposito=producto.ubicacion_deposito, stock_infinito=producto.stock_infinito,
            activo=producto.activo, foto_url=producto.foto_principal_url,
            created_at=producto.created_at, updated_at=producto.updated_at,
        )

    @classmethod
    def desde(cls, producto, camino: str) -> "ProductoResponse":
        return cls(**cls._campos(producto, camino))


class ProductoDetalle(ProductoResponse):
    fotos: list[FotoResponse]

    @classmethod
    def desde(cls, producto, camino: str) -> "ProductoDetalle":
        return cls(**cls._campos(producto, camino), fotos=[FotoResponse.model_validate(f) for f in producto.fotos])


class PrecioPreview(BaseModel):
    moneda: Moneda
    dolar_proveedor: Decimal | None
    precio_venta: Decimal
```

- [ ] **Step 4: Service** — `backend/app/services/productos.py`:

```python
"""Productos: alta, edición, estado, precio de venta y recálculo en cascada.
Sin variantes: cada artículo vendible es un producto con su código y precio."""
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.codigos import codificar_sku, digito_verificador
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import capitalizar_inicial, normalizar_texto, redondear, redondear_hacia_arriba, sin_tildes, sin_tildes_sql
from app.models import EstadoProveedor, Moneda, Producto, Proveedor
from app.schemas.productos import ProductoDetalle, ProductoResponse
from app.services import categorias as servicio_categorias
from app.services.configuracion import obtener_configuracion
from app.services.proveedores import obtener_proveedor

CAMPOS_AUDITADOS_DE_PRECIO = ("costo", "margen", "precio_venta")


def obtener_producto(db, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    return producto


def calcular_precio_venta(db, costo, margen, proveedor: Proveedor) -> Decimal:
    """ÚNICA definición del precio de venta (alta, edición, recálculo, preview e
    importación): CEIL(costo × dólar (o 1) × (1 + margen/100), redondeo)."""
    factor = proveedor.dolar_actual if proveedor.moneda is Moneda.USD else Decimal("1")
    bruto = Decimal(costo) * factor * (1 + Decimal(margen) / 100)
    precio = redondear_hacia_arriba(bruto, obtener_configuracion(db).redondeo)
    if precio >= Decimal("100000000"):
        raise DatoInvalido("El precio de venta resultante es demasiado grande.")
    return precio


def precio_preview(db, proveedor_id: int, costo, margen) -> dict:
    proveedor = obtener_proveedor(db, proveedor_id)
    return {
        "moneda": proveedor.moneda.value,
        "dolar_proveedor": proveedor.dolar_actual if proveedor.moneda is Moneda.USD else None,
        "precio_venta": calcular_precio_venta(db, costo, margen, proveedor),
    }


def recalcular_precios_de_proveedor(db, proveedor_id: int) -> int:
    """Lo llama services.proveedores tras cada cambio REAL del dólar, después del
    flush del valor nuevo (sin commit). Proveedor en pesos: no hace nada. El
    cambio queda auditado en el registro dolar.cambio del proveedor."""
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None or proveedor.moneda is not Moneda.USD:
        return 0
    productos = db.scalars(select(Producto).where(Producto.proveedor_id == proveedor_id)).all()
    for producto in productos:
        producto.precio_venta = calcular_precio_venta(db, producto.costo, producto.margen, proveedor)
    db.flush()
    return len(productos)


def _categoria_de_producto(db, categoria_id: int):
    categoria = servicio_categorias.obtener_categoria(db, categoria_id)
    if not servicio_categorias.es_hoja(db, categoria_id):
        raise ReglaDeNegocio("Elegí hasta el último nivel: la categoría del producto es la del final de la rama.")
    return categoria


def _descripcion_libre(db, descripcion: str, categoria_id: int, proveedor_id: int, excepto_id: int | None = None) -> str:
    limpia = capitalizar_inicial(descripcion)
    if not limpia:
        raise DatoInvalido("La descripción es obligatoria")
    condiciones = [
        func.lower(sin_tildes_sql(Producto.descripcion)) == sin_tildes(limpia).lower(),
        Producto.categoria_id == categoria_id,
        Producto.proveedor_id == proveedor_id,
    ]
    if excepto_id is not None:
        condiciones.append(Producto.id != excepto_id)
    existente = db.scalar(select(Producto).where(*condiciones))
    if existente is not None:
        inactivo = "" if existente.activo else ", que está inactivo y se puede volver a activar"
        raise ReglaDeNegocio(
            f"Ya existe un producto con esa descripción en este proveedor y categoría: {existente.sku}{inactivo}. "
            "Si es el mismo artículo en otro color o talle, cargalo como otro producto con una descripción que lo distinga."
        )
    return limpia


def _validar_descuento(db, descuento: Decimal) -> None:
    maximo = obtener_configuracion(db).descuento_maximo
    if descuento > maximo:
        raise DatoInvalido(f"El descuento del producto no puede superar el {maximo.normalize():f}%.")


def _validar_stock_infinito(autor, actual: bool, nuevo: bool) -> None:
    if nuevo != actual and not autor.es_admin:
        raise SinPermiso("El stock infinito lo define el Admin")


def _siguiente_sku(db) -> str:
    return codificar_sku(db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one())


def _asignar_opcionales(producto: Producto, datos) -> None:
    producto.sku_proveedor = normalizar_texto(datos.sku_proveedor)
    producto.descuento_producto = redondear(datos.descuento_producto)
    producto.peso_gramos = redondear(datos.peso_gramos) if datos.peso_gramos is not None else None
    producto.temporada = datos.temporada
    producto.ubicacion_deposito = normalizar_texto(datos.ubicacion_deposito)


def crear_producto(db, autor, datos, ip) -> Producto:
    categoria = _categoria_de_producto(db, datos.categoria_id)
    proveedor = obtener_proveedor(db, datos.proveedor_id)
    if proveedor.estado is not EstadoProveedor.ACTIVO:
        raise ReglaDeNegocio("El proveedor no está activo: no se le pueden cargar productos.")
    descripcion = _descripcion_libre(db, datos.descripcion, categoria.id, proveedor.id)
    _validar_descuento(db, datos.descuento_producto)
    _validar_stock_infinito(autor, False, datos.stock_infinito)
    margen = redondear(datos.margen if datos.margen is not None else obtener_configuracion(db).margen_default)
    costo = redondear(datos.costo)
    precio = calcular_precio_venta(db, costo, margen, proveedor)
    sku = _siguiente_sku(db)
    producto = Producto(sku=sku, verificador=digito_verificador(sku), descripcion=descripcion,
                        categoria_id=categoria.id, proveedor_id=proveedor.id, costo=costo, margen=margen,
                        precio_venta=precio, stock_infinito=datos.stock_infinito, activo=True)
    _asignar_opcionales(producto, datos)
    db.add(producto)
    db.flush()
    db.refresh(producto)
    registrar_auditoria(db, accion="producto.crear", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_nuevo=producto, ip_origen=ip)
    return producto


def editar_producto(db, autor, producto: Producto, datos, ip) -> Producto:
    # Primero se valida todo; recién después se modifica el producto.
    categoria_id = producto.categoria_id
    if datos.categoria_id != producto.categoria_id:
        categoria_id = _categoria_de_producto(db, datos.categoria_id).id
    descripcion = _descripcion_libre(db, datos.descripcion, categoria_id, producto.proveedor_id, excepto_id=producto.id)
    _validar_descuento(db, datos.descuento_producto)
    stock_infinito = producto.stock_infinito if datos.stock_infinito is None else datos.stock_infinito
    _validar_stock_infinito(autor, producto.stock_infinito, stock_infinito)
    costo, margen = redondear(datos.costo), redondear(datos.margen)
    precio = producto.precio_venta
    if costo != producto.costo or margen != producto.margen:
        precio = calcular_precio_venta(db, costo, margen, producto.proveedor)

    antes = snapshot(producto)
    producto.categoria_id = categoria_id
    producto.descripcion = descripcion
    producto.costo, producto.margen, producto.precio_venta = costo, margen, precio
    producto.stock_infinito = stock_infinito
    _asignar_opcionales(producto, datos)
    db.flush()
    db.refresh(producto)
    registrar_auditoria(db, accion="producto.editar", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=producto, ip_origen=ip)
    return producto


def cambiar_estado_producto(db, autor, producto: Producto, activo: bool, ip) -> Producto:
    if producto.activo is activo:
        return producto
    antes = snapshot(producto)
    producto.activo = activo
    db.flush()
    registrar_auditoria(db, accion="producto.activar" if activo else "producto.desactivar", entidad="producto",
                        entidad_id=producto.id, usuario_id=autor.id, estado_anterior=antes,
                        estado_nuevo=producto, ip_origen=ip)
    return producto


def a_respuesta(db, productos) -> list[ProductoResponse]:
    rutas = servicio_categorias.caminos(db)
    return [ProductoResponse.desde(p, rutas[p.categoria_id]) for p in productos]


def a_detalle(db, producto: Producto) -> ProductoDetalle:
    return ProductoDetalle.desde(producto, servicio_categorias.caminos(db)[producto.categoria_id])
```
Verificá que `snapshot(producto)` no intente serializar las relaciones (`categoria`, `proveedor`, `fotos`): si lo hace, pasale `campos=` con las columnas de la tabla o ajustá lo mínimo. `CAMPOS_AUDITADOS_DE_PRECIO` documenta qué mira el test; borrala si no la usás.

- [ ] **Step 5: Correr** — `test_productos.py`, `test_dolar_service.py` (el hook de proveedores ahora importa este módulo de verdad: los tests que monkeypatchean `_recalcular_precios` siguen pasando; `test_recalcular_sin_modulo_no_hace_nada` puede necesitar monkeypatchear `sys.modules` para simular que no existe: ajustalo si falla y explicalo) y la suite completa.

- [ ] **Step 6: Commit** — `feat(productos): alta, edición, estado y precio de venta con recálculo por dólar`.

---

### Task 5: Productos — búsqueda, listado, similares y código de barras

**Files:**
- Modify: `backend/app/services/productos.py`
- Test: `backend/tests/test_productos_busqueda.py`

**Interfaces:**
- Consumes: Task 4, `codigo_es_valido`, `filtro_texto`, `paginar`, `servicio_categorias.rama_de_ids`, python-barcode.
- Produces: `TAMANO_MAXIMO = 100`, `condiciones_codigo(texto) -> ColumnElement` (ÚNICA definición; la reusan stock y ventas), `buscar_por_codigo(db, codigo) -> Producto`, `listar_productos(db, *, busqueda=None, categoria_id=None, proveedor_id=None, temporada=None, activo=None, precio_desde=None, precio_hasta=None, pagina=1, tamano=10) -> tuple[list[Producto], int]`, `buscar_similares(db, descripcion, categoria_id=None, proveedor_id=None, limite=8) -> list[dict]` (`{id, sku, descripcion, activo}`), `svg_code128(texto, ancho_mm=None, alto_mm=None) -> str`, `barcode_svg(db, producto_id) -> str`, `barcode_svg_para_etiqueta(db, producto_id) -> str` (16mm × 4.5mm).

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_productos_busqueda.py`:

```python
from decimal import Decimal

import pytest

from app.core.errores import NoEncontrado
from app.models import TemporadaProducto
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores


@pytest.fixture
def datos(db, crear_usuario):
    admin = crear_usuario("admin")
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa"), None)
    remeras = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras", parent_id=ropa.id), None)
    calzado = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Calzado"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov búsqueda", moneda="ars"), None)
    otro = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Otro prov", moneda="ars"), None)

    def alta(descripcion, categoria=remeras, proveedor=prov, **extra):
        return servicio.crear_producto(db, admin, ProductoCrear(
            categoria_id=categoria.id, proveedor_id=proveedor.id, costo="1000", margen="0",
            descripcion=descripcion, **extra), None)

    productos = {
        "roja": alta("Remera lisa roja", sku_proveedor="PRV-100"),
        "azul": alta("Remera lisa azul", temporada=TemporadaProducto.PRIMAVERA_VERANO),
        "zapa": alta("Zapatilla urbana", categoria=calzado, costo="5000"),
        "otra": alta("Remera lisa roja", proveedor=otro),
    }
    return {"admin": admin, "ropa": ropa, "remeras": remeras, "calzado": calzado, "prov": prov, "otro": otro, **productos}


def _ids(resultado):
    items, _ = resultado
    return {p.id for p in items}


def test_buscar_por_codigo(db, datos):
    p = datos["roja"]
    assert servicio.buscar_por_codigo(db, p.codigo_con_verificador).id == p.id
    assert servicio.buscar_por_codigo(db, p.codigo_con_verificador.lower()).id == p.id
    assert servicio.buscar_por_codigo(db, p.sku).id == p.id
    malo = p.sku + ("0" if p.verificador != "0" else "1")
    with pytest.raises(NoEncontrado):
        servicio.buscar_por_codigo(db, malo)
    with pytest.raises(NoEncontrado):
        servicio.buscar_por_codigo(db, "ZZ999")


def test_listado_busqueda_por_codigo_sku_proveedor_y_descripcion(db, datos):
    p = datos["roja"]
    assert p.id in _ids(servicio.listar_productos(db, busqueda=p.codigo_con_verificador))
    assert _ids(servicio.listar_productos(db, busqueda=p.codigo_con_verificador)) == {p.id}
    assert _ids(servicio.listar_productos(db, busqueda="prv-100")) == {p.id}
    assert _ids(servicio.listar_productos(db, busqueda="LISA")) >= {datos["roja"].id, datos["azul"].id, datos["otra"].id}


def test_listado_filtros(db, datos):
    assert _ids(servicio.listar_productos(db, categoria_id=datos["ropa"].id)) >= {datos["roja"].id, datos["azul"].id}
    assert datos["zapa"].id not in _ids(servicio.listar_productos(db, categoria_id=datos["ropa"].id))
    assert _ids(servicio.listar_productos(db, proveedor_id=datos["otro"].id)) == {datos["otra"].id}
    assert _ids(servicio.listar_productos(db, temporada=TemporadaProducto.PRIMAVERA_VERANO)) == {datos["azul"].id}
    assert datos["zapa"].id in _ids(servicio.listar_productos(db, precio_desde=Decimal("4000")))
    assert datos["roja"].id not in _ids(servicio.listar_productos(db, precio_desde=Decimal("4000")))
    servicio.cambiar_estado_producto(db, datos["admin"], datos["azul"], False, None)
    assert datos["azul"].id not in _ids(servicio.listar_productos(db, activo=True))
    assert datos["azul"].id in _ids(servicio.listar_productos(db, activo=False))


def test_listado_paginado_y_ordenado(db, datos):
    items, total = servicio.listar_productos(db, proveedor_id=datos["prov"].id, pagina=1, tamano=2)
    assert total == 3 and len(items) == 2
    assert [p.descripcion for p in items] == ["Remera lisa azul", "Remera lisa roja"]


def test_similares(db, datos):
    assert servicio.buscar_similares(db, "Remera") == []                     # menos de 10 caracteres
    similares = servicio.buscar_similares(db, "remera LISA", categoria_id=datos["ropa"].id, proveedor_id=datos["prov"].id)
    assert {s["id"] for s in similares} == {datos["roja"].id, datos["azul"].id}
    assert set(similares[0]) == {"id", "sku", "descripcion", "activo"}
    assert servicio.buscar_similares(db, "remera lisa verde") == []           # exige todas las palabras de 3+


def test_barcode_svg(db, datos):
    p = datos["roja"]
    svg = servicio.barcode_svg(db, p.id)
    assert svg.startswith("<svg") and "viewBox" in svg and "mm" not in svg.split(">", 1)[1]
    etiqueta = servicio.barcode_svg_para_etiqueta(db, p.id)
    assert 'width="16mm"' in etiqueta and 'height="4.5mm"' in etiqueta and 'preserveAspectRatio="none"' in etiqueta
    with pytest.raises(NoEncontrado):
        servicio.barcode_svg(db, 999999)
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación** (agregar a `services/productos.py`; imports `re`, `from io import BytesIO`, `import barcode`, `from barcode.writer import SVGWriter`, `from sqlalchemy import or_`, `codigo_es_valido`, `filtro_texto`, `patron_ilike`, `paginar`, `TemporadaProducto`):

```python
TAMANO_MAXIMO = 100
MINIMO_SIMILARES = 10
_OPCIONES_BARCODE = {"module_width": 0.2, "module_height": 4.0, "write_text": False, "quiet_zone": 1.0}
_MEDIDA = re.compile(r'(\d+(?:\.\d+)?)mm')


def condiciones_codigo(texto: str):
    """ÚNICA definición de "buscar por código" (la reusan stock y ventas): ILIKE
    parcial sobre el SKU y, si el texto es SKU + verificador válido, también el
    match EXACTO del SKU sin el verificador."""
    limpio = (texto or "").strip().upper()
    condicion = Producto.sku.ilike(patron_ilike(limpio), escape="\\")
    if len(limpio) == 6 and codigo_es_valido(limpio):
        condicion = or_(condicion, Producto.sku == limpio[:5])
    return condicion


def buscar_por_codigo(db, codigo: str) -> Producto:
    """Etiqueta con verificador válido o el SKU solo; un verificador incorrecto no resuelve."""
    limpio = (codigo or "").strip().upper()
    sku = limpio[:5] if len(limpio) == 6 and codigo_es_valido(limpio) else limpio
    producto = db.scalar(select(Producto).where(Producto.sku == sku)) if len(sku) == 5 else None
    if producto is None:
        raise NoEncontrado("No hay ningún producto con ese código")
    return producto


def listar_productos(db, *, busqueda=None, categoria_id=None, proveedor_id=None, temporada=None, activo=None,
                     precio_desde=None, precio_hasta=None, pagina: int = 1, tamano: int = 10) -> tuple[list[Producto], int]:
    condiciones = []
    if busqueda and busqueda.strip():
        condiciones.append(or_(condiciones_codigo(busqueda), filtro_texto(Producto.sku_proveedor, busqueda),
                               filtro_texto(Producto.descripcion, busqueda)))
    if categoria_id is not None:
        condiciones.append(Producto.categoria_id.in_(servicio_categorias.rama_de_ids(db, categoria_id)))
    if proveedor_id is not None:
        condiciones.append(Producto.proveedor_id == proveedor_id)
    if temporada is not None:
        condiciones.append(Producto.temporada == temporada)
    if activo is not None:
        condiciones.append(Producto.activo.is_(activo))
    if precio_desde is not None:
        condiciones.append(Producto.precio_venta >= precio_desde)
    if precio_hasta is not None:
        condiciones.append(Producto.precio_venta <= precio_hasta)
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Producto).where(*condiciones))
    productos = db.scalars(
        select(Producto).where(*condiciones).order_by(func.lower(Producto.descripcion), Producto.sku)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(productos), total


def buscar_similares(db, descripcion: str, categoria_id=None, proveedor_id=None, limite: int = 8) -> list[dict]:
    """Parecidos al tipear la descripción (incluye inactivos): desde 10 caracteres,
    con TODAS las palabras de 3+ letras, en la rama de categoría y el proveedor."""
    limpia = normalizar_texto(descripcion) or ""
    if len(limpia) < MINIMO_SIMILARES:
        return []
    palabras = [p for p in limpia.split() if len(p) >= 3]
    if not palabras:
        return []
    condiciones = [filtro_texto(Producto.descripcion, p) for p in palabras]
    if categoria_id is not None:
        condiciones.append(Producto.categoria_id.in_(servicio_categorias.rama_de_ids(db, categoria_id)))
    if proveedor_id is not None:
        condiciones.append(Producto.proveedor_id == proveedor_id)
    filas = db.execute(
        select(Producto.id, Producto.sku, Producto.descripcion, Producto.activo).where(*condiciones)
        .order_by(func.lower(Producto.descripcion), Producto.sku).limit(limite)
    ).all()
    return [{"id": f.id, "sku": f.sku, "descripcion": f.descripcion, "activo": f.activo} for f in filas]


def svg_code128(texto: str, ancho_mm=None, alto_mm=None) -> str:
    """Code128 en SVG escalable: python-barcode usa unidades "mm" en cada
    atributo (no escala); se pasan a números con un viewBox en mm. Con ancho y
    alto, el SVG se fuerza a ese tamaño (preserveAspectRatio none)."""
    salida = BytesIO()
    barcode.get("code128", texto, writer=SVGWriter()).write(salida, _OPCIONES_BARCODE)
    svg = salida.getvalue().decode()
    svg = svg[svg.index("<svg"):]                                   # sin <?xml ...> ni DOCTYPE
    raiz = svg[:svg.index(">") + 1]
    ancho = _MEDIDA.search(re.search(r'width="([^"]+)"', raiz).group(1)).group(1)
    alto = _MEDIDA.search(re.search(r'height="([^"]+)"', raiz).group(1)).group(1)
    cuerpo = _MEDIDA.sub(r"\1", svg[len(raiz):])
    final_ancho = f"{ancho_mm}mm" if ancho_mm else f"{ancho}mm"
    final_alto = f"{alto_mm}mm" if alto_mm else f"{alto}mm"
    ajuste = ' preserveAspectRatio="none"' if ancho_mm and alto_mm else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {ancho} {alto}" '
            f'width="{final_ancho}" height="{final_alto}"{ajuste}>{cuerpo}')


def barcode_svg(db, producto_id: int) -> str:
    return svg_code128(obtener_producto(db, producto_id).codigo_con_verificador)


def barcode_svg_para_etiqueta(db, producto_id: int) -> str:
    return svg_code128(obtener_producto(db, producto_id).codigo_con_verificador, ancho_mm=16, alto_mm=4.5)
```
El test `"mm" not in svg.split(">", 1)[1]` exige que el cuerpo no conserve unidades mm (solo la raíz las tiene en width/height). Si `width="100%"` en los `rect` de fondo contiene "%", no molesta. Si la salida de python-barcode difiere (por ejemplo sin DOCTYPE), el `index("<svg")` sigue funcionando.

- [ ] **Step 4: Correr** — archivo + suite completa.

- [ ] **Step 5: Commit** — `feat(productos): búsqueda por código, listado, similares y código de barras`.

---

### Task 6: Fotos de productos

**Files:**
- Create: `backend/app/services/producto_fotos.py`
- Test: `backend/tests/test_producto_fotos.py`

**Interfaces:**
- Consumes: `ProductoFoto`, `Producto`, `settings.UPLOADS_DIR`, auditoría, errores.
- Produces: `MAXIMO_FOTOS = 5`, `TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024`, `formato_de_imagen(contenido: bytes) -> str | None` ("jpg" | "png" | "webp"), `obtener_foto(db, foto_id)`, `subir_foto(db, autor, producto, contenido, ip) -> ProductoFoto`, `marcar_principal(db, autor, foto, ip) -> ProductoFoto`, `eliminar_foto(db, autor, foto, ip) -> None`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_producto_fotos.py`:

```python
from pathlib import Path

import pytest
from sqlalchemy import select

from config import settings
from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.models import Auditoria
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import producto_fotos as servicio
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

JPG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 100


@pytest.fixture
def producto(db, crear_usuario):
    admin = crear_usuario("admin")
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Fotos"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov fotos", moneda="ars"), None)
    p = servicio_productos.crear_producto(db, admin, ProductoCrear(
        categoria_id=hoja.id, proveedor_id=prov.id, costo="10", descripcion="Con fotos"), None)
    return admin, p


def _archivo(foto) -> Path:
    return Path(settings.UPLOADS_DIR) / "productos" / foto.url.rsplit("/", 1)[1]


@pytest.mark.parametrize("contenido, formato", [(JPG, "jpg"), (PNG, "png"), (WEBP, "webp"), (b"GIF89a", None),
                                                 (b"", None), (b"RIFF\x00\x00\x00\x00AVI ", None)])
def test_formato_por_firma(contenido, formato):
    assert servicio.formato_de_imagen(contenido) == formato


def test_subir_guarda_archivo_y_marca_principal(db, producto):
    admin, p = producto
    foto = servicio.subir_foto(db, admin, p, JPG, None)
    assert foto.url.startswith(f"/uploads/productos/{p.sku}_") and foto.url.endswith(".jpg")
    assert len(foto.url.rsplit("_", 1)[1].split(".")[0]) == 12
    assert _archivo(foto).read_bytes() == JPG
    assert foto.es_principal
    segunda = servicio.subir_foto(db, admin, p, PNG, None)
    assert not segunda.es_principal and segunda.orden > foto.orden
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_subir", Auditoria.entidad_id == p.id))


def test_tope_de_cinco_fotos(db, producto):
    admin, p = producto
    for _ in range(5):
        servicio.subir_foto(db, admin, p, JPG, None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.subir_foto(db, admin, p, JPG, None)
    assert "5 fotos" in error.value.mensaje


def test_formato_y_tamano_invalidos(db, producto):
    admin, p = producto
    with pytest.raises(DatoInvalido):
        servicio.subir_foto(db, admin, p, b"GIF89a" + b"0" * 10, None)
    with pytest.raises(ReglaDeNegocio):
        servicio.subir_foto(db, admin, p, JPG + b"0" * (5 * 1024 * 1024), None)


def test_marcar_principal_desmarca_la_anterior(db, producto):
    admin, p = producto
    a = servicio.subir_foto(db, admin, p, JPG, None)
    b = servicio.subir_foto(db, admin, p, JPG, None)
    servicio.marcar_principal(db, admin, b, None)
    db.refresh(a)
    assert b.es_principal and not a.es_principal
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_principal", Auditoria.entidad_id == p.id))


def test_eliminar_principal_promueve_la_mas_antigua(db, producto):
    admin, p = producto
    a = servicio.subir_foto(db, admin, p, JPG, None)
    b = servicio.subir_foto(db, admin, p, JPG, None)
    c = servicio.subir_foto(db, admin, p, JPG, None)
    archivo = _archivo(a)
    servicio.eliminar_foto(db, admin, a, None)
    db.refresh(b)
    db.refresh(c)
    assert b.es_principal and not c.es_principal
    assert not archivo.exists()
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_eliminar", Auditoria.entidad_id == p.id))
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación** — `backend/app/services/producto_fotos.py`:

```python
"""Fotos de productos en el volumen /uploads (sobreviven a un rebuild).
Hasta 5 por producto; una sola principal; formato por firma de bytes."""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import ProductoFoto
from config import settings

MAXIMO_FOTOS = 5
TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024
URL_BASE = "/uploads/productos"


def _carpeta() -> Path:
    carpeta = Path(settings.UPLOADS_DIR) / "productos"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def formato_de_imagen(contenido: bytes) -> str | None:
    """Por firma de bytes, no por extensión ni Content-Type."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


def obtener_foto(db, foto_id: int) -> ProductoFoto:
    foto = db.get(ProductoFoto, foto_id)
    if foto is None:
        raise NoEncontrado("Foto no encontrada")
    return foto


def _auditar(db, autor, accion, foto, ip) -> None:
    registrar_auditoria(db, accion=accion, entidad="producto", entidad_id=foto.producto_id, usuario_id=autor.id,
                        estado_nuevo={"foto_id": foto.id, "url": foto.url, "es_principal": foto.es_principal},
                        ip_origen=ip)


def subir_foto(db, autor, producto, contenido: bytes, ip) -> ProductoFoto:
    if len(contenido) > TAMANO_MAXIMO_FOTO:
        raise ReglaDeNegocio("La foto supera los 5 MB.")
    formato = formato_de_imagen(contenido)
    if formato is None:
        raise DatoInvalido("La foto tiene que ser JPG, PNG o WEBP.")
    cantidad = db.scalar(select(func.count()).select_from(ProductoFoto).where(ProductoFoto.producto_id == producto.id))
    if cantidad >= MAXIMO_FOTOS:
        raise ReglaDeNegocio(f"Un producto puede tener hasta {MAXIMO_FOTOS} fotos.")
    orden = db.scalar(select(func.coalesce(func.max(ProductoFoto.orden) + 1, 0))
                      .where(ProductoFoto.producto_id == producto.id))
    nombre = f"{producto.sku}_{uuid4().hex[:12]}.{formato}"
    archivo = _carpeta() / nombre
    archivo.write_bytes(contenido)
    try:
        foto = ProductoFoto(producto_id=producto.id, url=f"{URL_BASE}/{nombre}", es_principal=cantidad == 0, orden=orden)
        db.add(foto)
        db.flush()
        db.refresh(foto)
        _auditar(db, autor, "producto.foto_subir", foto, ip)
    except Exception:
        archivo.unlink(missing_ok=True)       # sin fila no queda un archivo huérfano
        raise
    db.expire(producto, ["fotos"])
    return foto


def marcar_principal(db, autor, foto: ProductoFoto, ip) -> ProductoFoto:
    if foto.es_principal:
        return foto
    anterior = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == foto.producto_id,
                                                    ProductoFoto.es_principal.is_(True)))
    if anterior is not None:
        anterior.es_principal = False
        db.flush()                            # el índice único parcial no admite dos principales a la vez
    foto.es_principal = True
    db.flush()
    _auditar(db, autor, "producto.foto_principal", foto, ip)
    return foto


def eliminar_foto(db, autor, foto: ProductoFoto, ip) -> None:
    era_principal, producto_id = foto.es_principal, foto.producto_id
    archivo = _carpeta() / foto.url.rsplit("/", 1)[1]
    _auditar(db, autor, "producto.foto_eliminar", foto, ip)
    db.delete(foto)
    db.flush()
    if era_principal:
        siguiente = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id)
                              .order_by(ProductoFoto.created_at, ProductoFoto.id).limit(1))
        if siguiente is not None:
            siguiente.es_principal = True
            db.flush()
    # Último paso: el archivo no vuelve con un rollback.
    archivo.unlink(missing_ok=True)
```
Nota: `created_at` de fotos subidas en la misma transacción es igual (`now()` de Postgres es el inicio de la transacción): el desempate por `id` garantiza "la más antigua". Mencionalo en el reporte si el test lo evidencia.

- [ ] **Step 4: Correr** — archivo + suite completa.

- [ ] **Step 5: Commit** — `feat(productos): fotos de productos`.

---

### Task 7: PDF de etiquetas para la Zebra

**Files:**
- Create: `backend/app/reports/pdf.py`, `backend/app/reports/etiquetas_pdf.py`, `backend/app/templates/reports/etiquetas.html`
- Test: `backend/tests/test_etiquetas.py`

**Interfaces:**
- Consumes: `templates` (`app/core/templates.py`), WeasyPrint, `obtener_producto`, `svg_code128`.
- Produces: `pdf.documento(plantilla, contexto) -> weasyprint.Document`, `pdf.imprimir(plantilla, contexto) -> bytes` (ÚNICA vía de WeasyPrint; la reusan reportes); `etiquetas_pdf.TIPOS = ("rectangular", "colita")`, `MAXIMO_ETIQUETAS = 1000`, `etiquetas_documento(db, items: list[tuple[int, int]], tipo) -> Document`, `generar_etiquetas(db, items, tipo) -> bytes`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_etiquetas.py`:

```python
import pytest

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.reports import etiquetas_pdf
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

MM = 96 / 25.4   # WeasyPrint mide las páginas en px CSS


@pytest.fixture
def productos(db, crear_usuario):
    admin = crear_usuario("admin")
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Etiquetas"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov etiquetas", moneda="ars"), None)
    return [servicio_productos.crear_producto(db, admin, ProductoCrear(
        categoria_id=hoja.id, proveedor_id=prov.id, costo="10", descripcion=f"Etiqueta {i}"), None) for i in range(2)]


def _medidas(documento):
    return [(round(p.width / MM, 1), round(p.height / MM, 1)) for p in documento.pages]


def test_rectangular_tres_por_renglon(db, productos):
    documento = etiquetas_pdf.etiquetas_documento(db, [(productos[0].id, 4), (productos[1].id, 1)], "rectangular")
    assert _medidas(documento) == [(105.0, 10.0), (105.0, 10.0)]          # 5 etiquetas → 2 renglones


def test_colita_una_por_pagina(db, productos):
    documento = etiquetas_pdf.etiquetas_documento(db, [(productos[0].id, 3)], "colita")
    assert _medidas(documento) == [(66.0, 11.0)] * 3


def test_pdf_y_texto_del_codigo(db, productos):
    contenido = etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1)], "rectangular")
    assert contenido.startswith(b"%PDF")
    html = etiquetas_pdf.html_etiquetas(db, [(productos[0].id, 1)], "rectangular")
    assert productos[0].codigo_con_verificador in html and "data:image/svg+xml;base64," in html


def test_validaciones(db, productos):
    with pytest.raises(DatoInvalido):
        etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1)], "redonda")
    with pytest.raises(ReglaDeNegocio):
        etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1001)], "colita")
    with pytest.raises(NoEncontrado):
        etiquetas_pdf.generar_etiquetas(db, [(999999, 1)], "colita")
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: `app/reports/pdf.py`**:

```python
"""Única vía de WeasyPrint: plantilla Jinja de templates/reports → PDF."""
from weasyprint import HTML

from app.core.templates import APP_DIR, templates


def html(plantilla: str, contexto: dict) -> str:
    return templates.get_template(plantilla).render(**contexto)


def documento(plantilla: str, contexto: dict):
    return HTML(string=html(plantilla, contexto), base_url=str(APP_DIR)).render()


def imprimir(plantilla: str, contexto: dict) -> bytes:
    return documento(plantilla, contexto).write_pdf()
```

- [ ] **Step 4: `app/reports/etiquetas_pdf.py`**:

```python
"""Etiquetas para la Zebra GC420t (se abren en el navegador y se imprimen desde
el diálogo del sistema). No se guardan en disco."""
import base64

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.reports import pdf
from app.services.productos import obtener_producto, svg_code128

TIPOS = ("rectangular", "colita")
MAXIMO_ETIQUETAS = 1000
POR_RENGLON = 3
PLANTILLA = "reports/etiquetas.html"


def _contexto(db, items, tipo) -> dict:
    if tipo not in TIPOS:
        raise DatoInvalido("El tipo de etiqueta tiene que ser 'rectangular' o 'colita'.")
    if sum(cantidad for _, cantidad in items) > MAXIMO_ETIQUETAS:
        raise ReglaDeNegocio(f"Se pueden imprimir hasta {MAXIMO_ETIQUETAS} etiquetas por vez.")
    etiquetas = []
    for producto_id, cantidad in items:
        producto = obtener_producto(db, producto_id)
        svg = svg_code128(producto.codigo_con_verificador, ancho_mm=16, alto_mm=4.5)
        dato = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        etiquetas += [{"codigo": producto.codigo_con_verificador, "barcode": dato}] * cantidad
    paginas = ([etiquetas[i:i + POR_RENGLON] for i in range(0, len(etiquetas), POR_RENGLON)]
               if tipo == "rectangular" else [[e] for e in etiquetas])
    return {"tipo": tipo, "paginas": paginas}


def html_etiquetas(db, items, tipo) -> str:
    return pdf.html(PLANTILLA, _contexto(db, items, tipo))


def etiquetas_documento(db, items, tipo):
    return pdf.documento(PLANTILLA, _contexto(db, items, tipo))


def generar_etiquetas(db, items, tipo) -> bytes:
    return pdf.imprimir(PLANTILLA, _contexto(db, items, tipo))
```

- [ ] **Step 5: `templates/reports/etiquetas.html`**:

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  {% if tipo == "rectangular" %}
  @page { size: 105mm 10mm; margin: 0; }
  {% else %}
  @page { size: 66mm 11mm; margin: 0; }
  {% endif %}
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "DejaVu Sans", sans-serif; }
  .pagina { display: flex; page-break-after: always; }
  .pagina:last-child { page-break-after: auto; }
  .rectangular { width: 105mm; height: 10mm; gap: 3mm; }
  .colita { width: 66mm; height: 11mm; }
  .cola { width: 33mm; height: 11mm; }                 /* cola izquierda sin imprimir */
  .etiqueta { width: 33mm; display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .rectangular .etiqueta { height: 10mm; }
  .colita .etiqueta { height: 11mm; }
  .etiqueta img { width: 16mm; height: 4.5mm; }
  .codigo { font-size: 6pt; letter-spacing: 0.3pt; margin-top: 0.5mm; }
</style>
</head>
<body>
{% for pagina in paginas %}
  <div class="pagina {{ tipo }}">
    {% if tipo == "colita" %}<div class="cola"></div>{% endif %}
    {% for etiqueta in pagina %}
      <div class="etiqueta">
        <img src="{{ etiqueta.barcode }}" alt="">
        <span class="codigo">{{ etiqueta.codigo }}</span>
      </div>
    {% endfor %}
  </div>
{% endfor %}
</body>
</html>
```
Nota: con 3 etiquetas de 33 mm + 2 separaciones de 3 mm se llenan exactamente 105 mm. Si WeasyPrint agrega una página en blanco al final por `page-break-after`, el `:last-child` lo evita; si igual aparece, usar `page-break-before: always` en `.pagina + .pagina`.

- [ ] **Step 6: Correr** — archivo + suite completa.

- [ ] **Step 7: Commit** — `feat(productos): PDF de etiquetas para la Zebra`.

---

### Task 8: Endpoints de categorías y productos

**Files:**
- Create: `backend/app/api/v1/categorias.py`, `backend/app/api/v1/productos.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_categorias_api.py`, `backend/tests/test_productos_api.py`

**Interfaces:**
- Consumes: services de Tasks 3-7, `RespuestaPaginada`, `requiere_permiso(Modulo.PRODUCTOS, accion)`, `ip_de_request`.
- Produces: los endpoints del spec (rutas fijas antes de `/{producto_id}`; `/fotos/{foto_id}/...` y `/etiquetas` también antes). Schemas extra en `schemas/productos.py`: `ItemEtiqueta {producto_id: int, cantidad: int (1..1000)}`, `PedidoEtiquetas {items: list[ItemEtiqueta] (1..200), tipo: Literal["rectangular", "colita"]}`, `Similar {id, sku, descripcion, activo}`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_categorias_api.py`:
```python
URL = "/api/v1/categorias"


def test_crud_de_categorias(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json={"nombre": "Ropa"}, headers=h)
    assert r.status_code == 201
    ropa = r.json()
    hija = client.post(URL, json={"nombre": "Remeras", "parent_id": ropa["id"]}, headers=h).json()
    assert hija["nivel"] == 2
    arbol = client.get(f"{URL}/arbol", headers=h).json()
    nodo = next(n for n in arbol if n["id"] == ropa["id"])
    assert nodo["hijos"][0]["nombre"] == "Remeras"
    assert [c["nombre"] for c in client.get(URL, params={"parent_id": ropa["id"]}, headers=h).json()] == ["Remeras"]
    assert client.put(f"{URL}/{hija['id']}", json={"nombre": "Remeras lisas", "orden": 1}, headers=h).json()["nombre"] == "Remeras lisas"
    assert client.patch(f"{URL}/{hija['id']}/mover", json={"parent_id": None}, headers=h).json()["nivel"] == 1
    assert client.delete(f"{URL}/{hija['id']}", headers=h).status_code == 204
    assert client.get(f"{URL}/{hija['id']}", headers=h).status_code == 404
    assert client.get(URL, params={"nivel": 6}, headers=h).status_code == 422


def test_permisos_de_categorias(client, crear_usuario, headers_de):
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(f"{URL}/arbol", headers=vendedor).status_code == 200      # vendedor: productos ver
    assert client.post(URL, json={"nombre": "X"}, headers=vendedor).status_code == 403
```

`backend/tests/test_productos_api.py`:
```python
from sqlalchemy import select

from app.models import ConfiguracionSistema

URL = "/api/v1/productos"
JPG = b"\xff\xd8\xff\xe0" + b"0" * 100


def _base(client, h, db):
    fila = db.scalar(select(ConfiguracionSistema))
    fila.redondeo = 100
    db.flush()
    raiz = client.post("/api/v1/categorias", json={"nombre": "Ropa API"}, headers=h).json()
    hoja = client.post("/api/v1/categorias", json={"nombre": "Remeras API", "parent_id": raiz["id"]}, headers=h).json()
    prov = client.post("/api/v1/proveedores", json={"nombre": "Prov API", "moneda": "usd", "dolar_actual": "1000"},
                       headers=h).json()
    return hoja, prov


def _alta(client, h, hoja, prov, **extra):
    datos = {"categoria_id": hoja["id"], "proveedor_id": prov["id"], "costo": "10", "margen": "0",
             "descripcion": "remera api"}
    datos.update(extra)
    return client.post(URL, json=datos, headers=h)


def test_alta_listado_detalle_y_edicion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    r = _alta(client, h, hoja, prov)
    assert r.status_code == 201
    p = r.json()
    assert p["precio_venta"] == "10000.00" and p["moneda"] == "usd" and p["categoria"]["camino"] == "Ropa API > Remeras API"
    assert p["descripcion"] == "Remera api" and len(p["codigo_con_verificador"]) == 6
    lista = client.get(URL, params={"busqueda": p["codigo_con_verificador"]}, headers=h).json()
    assert lista["total"] == 1 and lista["resultados"][0]["id"] == p["id"]
    detalle = client.get(f"{URL}/{p['id']}", headers=h).json()
    assert detalle["fotos"] == []
    r = client.put(f"{URL}/{p['id']}", json={"categoria_id": hoja["id"], "costo": "20", "margen": "10",
                                            "descripcion": "Remera api"}, headers=h)
    assert r.status_code == 200 and r.json()["precio_venta"] == "22000.00"
    assert client.patch(f"{URL}/{p['id']}/estado", json={"activo": False}, headers=h).json()["activo"] is False
    assert client.get(f"{URL}/999999", headers=h).status_code == 404


def test_rutas_fijas(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov, descripcion="Remera lisa roja grande").json()
    vista = client.get(f"{URL}/precio-preview", params={"proveedor_id": prov["id"], "costo": "10.01", "margen": "10"},
                       headers=h).json()
    assert vista == {"moneda": "usd", "dolar_proveedor": "1000.00", "precio_venta": "11100.00"}
    similares = client.get(f"{URL}/similares", params={"descripcion": "remera lisa roja", "proveedor_id": prov["id"]},
                           headers=h).json()
    assert similares[0]["id"] == p["id"]
    assert client.get(f"{URL}/por-codigo", params={"codigo": p["codigo_con_verificador"]}, headers=h).json()["id"] == p["id"]
    assert client.get(f"{URL}/por-codigo", params={"codigo": "ZZ999"}, headers=h).status_code == 404
    r = client.get(f"{URL}/{p['id']}/barcode", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


def test_fotos_y_etiquetas(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov).json()
    r = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("x.jpg", JPG, "image/jpeg")}, headers=h)
    assert r.status_code == 201 and r.json()["es_principal"]
    segunda = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("y.png", JPG, "image/png")}, headers=h).json()
    assert client.patch(f"{URL}/fotos/{segunda['id']}/principal", headers=h).json()["es_principal"]
    assert client.delete(f"{URL}/fotos/{segunda['id']}", headers=h).status_code == 204
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["fotos"][0]["es_principal"]
    r = client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 2}], "tipo": "colita"},
                    headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline") and r.content.startswith(b"%PDF")
    assert client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 0}], "tipo": "colita"},
                       headers=h).status_code == 422


def test_permisos(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov).json()
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=vendedor).status_code == 200
    assert _alta(client, vendedor, hoja, prov, descripcion="Otra").status_code == 403
    assert client.patch(f"{URL}/{p['id']}/estado", json={"activo": False}, headers=vendedor).status_code == 403
    assert client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 1}],
                                                  "tipo": "rectangular"}, headers=vendedor).status_code == 200
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Routers.** Seguí exactamente el patrón de `app/api/v1/proveedores.py` (dependencias `puede_ver/crear/editar/eliminar = requiere_permiso(Modulo.PRODUCTOS, ...)`, `ip_de_request`, `db.commit()` en cada escritura).

`app/api/v1/categorias.py` — prefix `/categorias`:
- `GET ""` → `list[CategoriaResponse]`; query `nombre: str|None`, `nivel: int|None = Query(None, ge=1, le=NIVEL_MAXIMO)`, `parent_id: int|None`.
- `GET /arbol` → `list[CategoriaNodo]` (`servicio.arbol(db)`).
- `GET /{categoria_id}` → `CategoriaResponse`.
- `POST ""` (201, crear) / `PUT /{id}` (editar) / `PATCH /{id}/mover` (editar, body `CategoriaMover`) / `DELETE /{id}` (eliminar, 204, `Response(status_code=204)`).

`app/api/v1/productos.py` — prefix `/productos`, en este orden:
- `GET ""` → `RespuestaPaginada[ProductoResponse]`; query `busqueda, categoria_id, proveedor_id, temporada: TemporadaProducto|None, activo: bool|None, precio_desde: Decimal|None, precio_hasta: Decimal|None, pagina = Query(1, ge=1), tamano = Query(10, ge=1, le=TAMANO_MAXIMO)`; `resultados=servicio.a_respuesta(db, items)`.
- `GET /precio-preview` → `PrecioPreview`; query `proveedor_id: int`, `costo: Decimal = Query(gt=0, lt=100000000)`, `margen: Decimal = Query(ge=0, le=1000)`.
- `GET /similares` → `list[Similar]`; query `descripcion: str = Query(max_length=500)`, `categoria_id`, `proveedor_id`.
- `GET /por-codigo` → `ProductoDetalle`; query `codigo: str = Query(min_length=1, max_length=20)`.
- `POST /etiquetas` [ver] → `Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="etiquetas.pdf"'})`, con `response_class=Response` y `responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}}`.
- `PATCH /fotos/{foto_id}/principal` [editar] → `FotoResponse`.
- `DELETE /fotos/{foto_id}` [editar] → 204.
- `GET /{producto_id}` → `ProductoDetalle` (`servicio.a_detalle`).
- `POST ""` (201, crear) → `ProductoResponse`; `PUT /{id}` (editar) → `ProductoResponse`; `PATCH /{id}/estado` (editar) → `ProductoResponse` (todas con `a_respuesta(db, [p])[0]`).
- `GET /{id}/barcode` [ver] → `Response(svg, media_type="image/svg+xml")` (`response_class=Response`, `responses` con image/svg+xml).
- `POST /{id}/fotos` [editar] (201) → `FotoResponse`; `archivo: UploadFile = File(...)`, leer `archivo.file.read(TAMANO_MAXIMO_FOTO + 1)`.
Registrar ambos routers en `api/v1/__init__.py` como los demás.

- [ ] **Step 4: Correr** — ambos archivos + suite completa. `curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/v1/productos` → 401.

- [ ] **Step 5: Commit** — `feat(productos): API de categorías y productos`.

---

### Task 9: Sidebar "Productos" y pantalla de categorías

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/categorias/arbol.html`, `backend/app/static/js/categorias.js`
- Test: `backend/tests/test_paginas_productos.py`

**Interfaces:**
- Consumes: `MENU_SIDEBAR`, `requiere_pagina`, `contexto_base`, `_pagina`, `resolver_permiso`, API de categorías.
- Produces: `PAGINA_PRODUCTOS = {"nombre": "Productos", "url": "/productos", "icono": "productos", "modulo": Modulo.PRODUCTOS}` insertado en `MENU_SIDEBAR` entre "Inicio" y "Configuraciones"; ruta `GET /categorias` (`requiere_pagina(PAGINA_PRODUCTOS, actual="/productos")`, contexto `puede_crear`, `puede_editar`, `puede_eliminar`, `nivel_maximo`); componente `categoriasArbol({puedeCrear, puedeEditar, puedeEliminar, nivelMaximo})`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_paginas_productos.py`:

```python
def test_sidebar_muestra_productos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert 'href="/productos"' in html


def test_categorias_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/categorias").text
    assert "categoriasArbol(" in html and "/static/js/categorias.js?v=" in html
    assert 'href="/productos"' in html and "Nueva categoría" in html


def test_categorias_solo_consulta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/categorias").text
    assert "Nueva categoría" not in html and "puedeEditar: false" in html
```
(Si `MENU_SIDEBAR` ya tiene un test que fija su contenido, actualizalo.)

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Ruta** (en `pages.py`, junto a las de proveedores):
```python
@router.get("/categorias")
def categorias(request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_pagina(PAGINA_PRODUCTOS, actual="/productos"))):
    return _pagina(request, "pages/categorias/arbol.html", contexto_base(
        request, db, "/productos", usuario,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "editar"),
        puede_eliminar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "eliminar"),
        nivel_maximo=NIVEL_MAXIMO,
    ))
```
Verificá la firma real de `requiere_pagina` (si `actual` es posicional o keyword) y adaptala.

- [ ] **Step 4: Plantilla `pages/categorias/arbol.html`** (extiende `base.html`; bloques `titulo`, `contenido`, `scripts` como `pages/proveedores/listado.html`):
- `encabezado("Categorías", "/productos", "Productos")` con botón "Nueva categoría" (`boton boton-acento`, ícono "mas") solo si `puede_crear` → `nuevaRaiz()`.
- Barra de filtros (`barra_filtros(etiqueta="categorías encontradas")`): input "Nombre" (`filtros.nombre`, `@input="filtrar()"`) y select "Nivel" (Todos, 1..`nivel_maximo`, `@change="cargar()"`). Con un filtro activo se muestra la lista plana de `GET /api/v1/categorias` (nombre + nivel + camino calculado con `rutaCategoria(arbol, id)`); sin filtros, el árbol.
- Árbol colapsable: un `<template x-for>` recursivo no existe en Alpine; usar una lista **aplanada** calculada en JS (`visibles` = nodos en orden DFS con `profundidad`, omitiendo los hijos de nodos colapsados) y renderizarla con `x-for` e indentación `:style="'padding-left:' + (n.profundidad * 1.5) + 'rem'"`. Cada fila (`min-h-toque`): botón chevron (si tiene hijos) que alterna `abiertos[n.id]`; nombre (`x-text`); acciones con la macro `accion` (`mas` "Agregar subcategoría" si `puedeCrear && n.nivel < nivelMaximo`, `editar`, "Mover" (ícono `chevron-derecha`), `borrar`), cada una según permiso.
- Modal (`components/modal.html`) de alta/edición: `campo` Nombre (requerido) y Orden (number, min 0); para el alta muestra "Dentro de: <camino del padre>" o "Categoría raíz". Botón "Crear"/"Finalizar".
- Modal Mover: select con "Categoría raíz" + todas las categorías (camino completo) **excepto la propia rama** (calculada en JS recorriendo el nodo) y las que dejarían la rama en más de `nivelMaximo` niveles (el backend valida igual). Botón "Mover".
- Borrar: `confirmar({titulo: '¿Eliminar la categoría X?', textoConfirmar: 'Eliminar', peligro: true})` → `DELETE`; los 409 (tiene subcategorías o productos) se muestran con toast.

- [ ] **Step 5: `static/js/categorias.js`** — componente `window.categoriasArbol({ puedeCrear, puedeEditar, puedeEliminar, nivelMaximo })` con: `arbol`, `abiertos` (todos los de nivel 1 abiertos al cargar), `filtros {nombre, nivel}`, `planas`, `cargando`, `_ultima: ultimaRespuesta()`; `get visibles()` (DFS aplanado respetando `abiertos`), `get total()`, `cargar()` (con filtros → `GET /api/v1/categorias?…` a `planas`; siempre refresca `arbol` de `/arbol`), `filtrar()` (debounce 400 ms), `limpiarFiltros()`, `nuevaRaiz()`, `nuevaHija(n)`, `editar(n)`, `guardar()` (POST/PUT con `pedir`, `erroresDeCampos` en 422, toast y recarga), `abrirMover(n)`, `destinosPosibles` (getter), `mover()`, `eliminar(n)`. Todo texto de la API con `x-text` (sin `x-html`).

- [ ] **Step 6: Correr** — tests de páginas, `node --check backend/app/static/js/categorias.js`, suite completa.

- [ ] **Step 7: Commit** — `feat(productos): menú de productos y pantalla de categorías`.

---

### Task 10: Formulario de producto (macro + componente)

**Files:**
- Create: `backend/app/templates/components/producto_form.html`, `backend/app/static/js/producto_form.js`
- Test: `backend/tests_js/producto_form.test.mjs`, `backend/tests/test_paginas_productos.py` (agregar un test de render con una página de prueba: ver Step 1)

**Interfaces:**
- Consumes: API de categorías (`/arbol`), productos (`/precio-preview`, `/similares`, POST/PUT, `/{id}/fotos`), proveedores activos (`GET /api/v1/proveedores?estado=activo`), app.js (`pedir`, `toast`, `ultimaRespuesta`, `erroresDeCampos`, `webcamCapture`, `pesos`, `dolares`, `rutaDeIds`), macros `modal`, `campo`, `combobox`.
- Produces: macro `producto_form_modal(es_admin, nivel_maximo, margen_default, descuento_maximo)` que declara un bloque `x-data="productoForm({ esAdmin, nivelMaximo, margenDefault, descuentoMaximo })"` con su modal; se abre con el evento de ventana `abrir-producto-form` (`detail: {producto: null|ProductoDetalle}`) y al guardar emite `producto-guardado` (`detail: producto`). Funciones puras exportadas en `window.productoFormUtil` para testear: `nivelesDeCategoria(arbol, categoriaId) -> [idsElegidos]`, `opcionesDeNivel(arbol, elegidos, nivel) -> [nodos]`, `esHoja(arbol, id) -> bool`, `stockEntero(valor) -> number` (`Math.trunc`, mínimo 0; se deja lista para el 05).

- [ ] **Step 1: Tests que fallan**
`backend/tests_js/producto_form.test.mjs` (patrón de `usuarios.test.mjs`: cargar `app.js` + `producto_form.js` en `vm`):
  1. `nivelesDeCategoria(arbol, idDeUnaHojaDeNivel3)` devuelve los 3 ids desde la raíz; con `null` devuelve `[]`.
  2. `opcionesDeNivel(arbol, [raiz.id], 1)` devuelve los hijos de la raíz; `opcionesDeNivel(arbol, [], 0)` las raíces.
  3. `esHoja` true/false.
  4. Secuencia del preview: dos cambios de costo seguidos cuyo pedido viejo llega después → `precioPreview` queda el del último (usar `pedir` diferido).
  5. Similares: al cambiar a otro producto (`abrir` con otro) no se pisan los parecidos con una respuesta vieja.
En `test_paginas_productos.py` el render del formulario se prueba en la Task 11 (la página lo incluye).

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Macro `components/producto_form.html`** — `producto_form_modal(es_admin, nivel_maximo, margen_default, descuento_maximo)` (los dos últimos como string):
- `<div x-data="productoForm({ esAdmin: {{ es_admin|js }}, nivelMaximo: {{ nivel_maximo|js }}, margenDefault: {{ margen_default|js }}, descuentoMaximo: {{ descuento_maximo|js }} })" @abrir-producto-form.window="abrir($event.detail.producto)">` con `modal("Producto", "modal-producto-form", abierto="abierto", titulo_expr="form.id ? 'Editar producto' : 'Nuevo producto'")`.
- **Categoría:** `<template x-for="nivel in nivelesVisibles">` un `<select class="campo">` por nivel (etiqueta "Categoría" en el primero, "Subcategoría" en los demás), opciones de `opcionesDeNivel(arbol, elegidos, nivel)`; al cambiar un nivel se recortan los niveles siguientes. Ayuda: "Elegí hasta el último nivel: la categoría del producto es la del final de la rama." Error `errores.categoria_id`.
- **Proveedor:** en el alta, `combobox("pf-proveedor", "proveedoresOpciones", "form.proveedor_id", texto="texto", etiqueta="Proveedor *", vacio="Elegí un proveedor", al_cambiar="alCambiarProveedor()")` donde `texto` = "Nombre (US$)" o "Nombre ($)". En la edición, texto fijo con el nombre y la moneda (no editable).
- **SKU proveedor** (`campo`), **Descripción** (`campo` con `atributos` para `@input="buscarSimilares()"`, `@keydown.arrow-down.prevent`, `@keydown.arrow-up.prevent`, `@keydown.enter.prevent` (solo si hay lista abierta), `@keydown.escape`), con la lista de parecidos debajo (`role="listbox"`, cada ítem `x-text="s.descripcion + ' · ' + s.sku"` y la marca "(inactivo)"; elegir uno adopta su descripción). Aviso rojo si hay un parecido con la misma descripción normalizada (`normalizarTexto`). Ayuda: "Si el artículo viene en varios colores o talles, cargá un producto por cada uno."
- **Costo** (etiqueta dinámica `x-text`: "Costo en dólares (US$)" / "Costo en pesos ($)"), **Margen %** (precargado con `margenDefault` en el alta); ambos `:disabled="!form.proveedor_id"`. Debajo: `Precio de venta: <span x-text="precioPreview !== null ? pesos(precioPreview) : '—'">` (+ "· dólar $ X" si `dolarProveedor`).
- **Peso (g)**, **Descuento %** (`max` = `descuento_maximo`), **Temporada** (select: Atemporal / Otoño-Invierno / Primavera-Verano), **Ubicación en depósito**.
- `{% if es_admin %}` checkbox "Stock infinito (no descuenta al vender)" `{% endif %}`.
- **Foto inicial** (solo alta): input file `accept="image/jpeg,image/png,image/webp"` y bloque de webcam (`x-data="webcamCapture()"`, `<video x-ref="video">`, botones "Tomar foto"/"Capturar"/"Cancelar"); la foto elegida se guarda en `fotoInicial` (Blob) y se sube después del alta (`POST /{id}/fotos` con FormData); si la subida falla, el producto queda creado y se avisa con toast.
- Botón `x-text="form.id ? 'Finalizar' : 'Crear'"`, abajo a la derecha. Errores 422 por campo con `errores.<campo>`.
- Grilla `grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4` según el ancho; mobile-first; `min-h-toque` en checkboxes.

- [ ] **Step 4: `static/js/producto_form.js`** — `window.productoFormUtil = { nivelesDeCategoria, opcionesDeNivel, esHoja, stockEntero }` y `window.productoForm({ esAdmin, nivelMaximo, margenDefault, descuentoMaximo })` con estado `abierto, form, elegidos, arbol, proveedores, errores, guardando, precioPreview, dolarProveedor, similares, similarActivo, fotoInicial`, secuenciadores `_ultimaPreview`, `_ultimaSimilares`, `_ultimaApertura` (todos `ultimaRespuesta()`), y métodos:
- `async abrir(producto)`: resetea todo; carga `arbol` y (en el alta) `proveedores` con `_ultimaApertura`, descartando si mientras tanto se abrió otro (`this._apertura` incremental); en la edición copia el producto y calcula `elegidos = nivelesDeCategoria(arbol, producto.categoria.id)`.
- `get nivelesVisibles()`, `elegirNivel(nivel, id)`, `get categoriaId()` (último elegido si es hoja; si no, null).
- `get moneda()` (del proveedor elegido o del producto en edición), `alCambiarProveedor()` → `pedirPreview()`.
- `pedirPreview()` (debounce 300 ms; sin proveedor, costo o margen válidos → `precioPreview = null`; secuenciado con `_ultimaPreview`).
- `buscarSimilares()` (debounce 300 ms; < 10 caracteres → lista vacía; secuenciado con `_ultimaSimilares`; pasa `categoria_id` y `proveedor_id`), `moverSimilar(delta)`, `elegirSimilar(s)`, `get duplicadoExacto()`.
- `cuerpo()` (costo y margen como string; `categoria_id` = `categoriaId`), `async guardar()` (si `categoriaId` es null, marca `errores.categoria_id` y no llama a la API; POST o PUT; `erroresDeCampos` en 422; en el alta sube `fotoInicial` si hay; `window.dispatchEvent(new CustomEvent('producto-guardado', {detail: producto}))`; toast; cierra).
- `elegirArchivo(e)`, `async capturarFoto(camara)` (usa `camara.capturar()` y `camara.detener()`).

- [ ] **Step 5: Correr** — `node --check`, `node --test backend/tests_js/`, suite de pytest.

- [ ] **Step 6: Commit** — `feat(productos): formulario de producto`.

---

### Task 11: Listado de productos y ficha

**Files:**
- Modify: `backend/app/api/pages.py`, `docs/pendientes.md`
- Create: `backend/app/templates/pages/productos/listado.html`, `backend/app/templates/pages/productos/_modal_ficha.html`, `backend/app/static/js/productos.js`
- Test: `backend/tests/test_paginas_productos.py` (agregar)

**Interfaces:**
- Consumes: `PAGINA_PRODUCTOS`, macro `producto_form_modal`, API de productos/categorías/proveedores, `obtener_configuracion`, macros `encabezado`, `barra_filtros`, `tabla`, `paginacion`, `combobox`, `switch_estado`, `accion/acciones`, `miniatura`, `modal`.
- Produces: ruta `GET /productos` (contexto `puede_crear`, `puede_editar`, `nivel_maximo`, `margen_default`, `descuento_maximo`); componente `productosListado({ puedeEditar })`.

- [ ] **Step 1: Tests que fallan** (agregar a `test_paginas_productos.py`):
```python
def test_listado_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/productos").text
    assert "productosListado(" in html and "/static/js/productos.js?v=" in html
    assert "/static/js/producto_form.js?v=" in html and "productoForm(" in html
    assert 'href="/categorias"' in html and "Crear nuevo" in html
    assert "Stock infinito" in html                       # solo Admin


def test_listado_vendedor(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/productos").text
    assert "Crear nuevo" not in html and "puedeEditar: false" in html and "Stock infinito" not in html

```
(Los tres roles de sistema tienen `productos ver`; el 403 de página ya lo cubre `requiere_pagina` en los tests de módulos anteriores.)

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Ruta**:
```python
@router.get("/productos")
def productos(request: Request, db: Session = Depends(get_db),
              usuario: Usuario = Depends(requiere_pagina(PAGINA_PRODUCTOS, actual="/productos"))):
    config = obtener_configuracion(db)
    return _pagina(request, "pages/productos/listado.html", contexto_base(
        request, db, "/productos", usuario,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "editar"),
        nivel_maximo=NIVEL_MAXIMO, margen_default=str(config.margen_default),
        descuento_maximo=str(config.descuento_maximo),
    ))
```
(`margen_default`/`descuento_maximo` son Decimal: pasalos a la macro como string, `str(config.margen_default)`, y convertilos con `Number()` en JS.)

- [ ] **Step 4: Plantilla `pages/productos/listado.html`**:
- `encabezado("Productos")` con botones "Categorías" (`<a href="/categorias" class="boton boton-secundario">`) y "+ Crear nuevo" (si `puede_crear`, `@click="$dispatch('abrir-producto-form', {producto: null})"`).
- `barra_filtros(etiqueta="productos encontrados")`: input "Código, SKU o descripción" (`filtros.busqueda`, debounce 400 ms); `combobox` Categoría (opciones = categorías con `texto` = camino completo vía `rutaCategoria`), `combobox` Proveedor, `combobox` Temporada; `switch_estado(modelo="filtros.activos", al_cambiar="cargar(1)")` (activos/inactivos). "Limpiar filtros" y el contador vienen de la macro.
- `tabla` con columnas: Código (`fila.codigo_con_verificador` + leyenda chica "+ dígito verificador" vía `html` con texto fijo y el código pasado por `escaparHtml`), Foto (`miniatura("fila.foto_url", "sm")` — si la macro `tabla` no admite macros por columna, usar su mecanismo `html` con un `<img>` armado en JS con `escaparHtml` en el src o agregá a `tabla` un slot; elegí lo mínimo y explicalo), Descripción, Categoría (`fila.categoria.camino`), Proveedor, Costo (`costoTexto(fila)`: `$ ` + `pesos()` o `dolares()`), Margen % , Precio de venta (`pesos(fila.precio_venta)`). Acciones: Ver (`abrirFicha(fila)`), Editar (si `puedeEditar`, abre el formulario con el detalle cargado de `GET /{id}`), Desactivar/Activar (si `puedeEditar`, con `confirmar()`).
- `paginacion()` debajo (de a 10).
- `{% include "pages/productos/_modal_ficha.html" %}` y `{{ producto_form_modal(es_admin, nivel_maximo, margen_default, descuento_maximo) }}`.
- Scripts: `producto_form.js` y `productos.js`.

- [ ] **Step 5: `_modal_ficha.html`**: modal con título = descripción, código con verificador grande, SVG del código de barras (`<img :src="'/api/v1/productos/' + ficha.id + '/barcode'">`), datos (categoría, proveedor, costo con moneda, margen, precio de venta, descuento, peso, temporada, ubicación, stock infinito, estado); **Fotos**: grilla con `miniatura` grande, marca "Principal", botones "Marcar principal" y "Borrar" (con `confirmar`), "Subir foto" (input file) y "Tomar foto" (webcam) — solo con `puedeEditar` y si hay menos de 5; **Imprimir etiquetas**: input "Cant:" (entero ≥1, default 1) y botones "Rectangular" / "Con colita" que hacen `POST /api/v1/productos/etiquetas` con `pedir`… — ojo: `pedir` parsea JSON; para el PDF usar `fetch` directo (`credentials: 'same-origin'`, JSON body), `blob()` y `window.open(URL.createObjectURL(blob))`; errores con `mensajeDeError`.

- [ ] **Step 6: `static/js/productos.js`** — `window.productosListado({ puedeEditar })`: `filtros {busqueda, categoria_id, proveedor_id, temporada, activos: true}`, `filas`, `total`, `pagina`, `tamano: 10`, `cargando`, `_ultima`, `_ultimaFicha` (secuenciador de la ficha: abrir otra ficha mientras carga descarta la vieja, también comparando el id), `arbol`, `proveedores`, `temporadas`; `init()` (carga catálogos y el listado; escucha `producto-guardado` en window → `cargar()` y, si la ficha abierta es ese producto, la refresca), `cargar(pagina)`, `filtrar()`, `limpiarFiltros()`, `get categoriasOpciones()` (lista plana con `texto` = camino), `costoTexto(p)`, `abrirFicha(p)`, `editar(p)` (carga el detalle y `dispatch('abrir-producto-form', {producto})`), `cambiarEstado(p)`, `subirFoto(archivo|blob)`, `marcarPrincipal(f)`, `borrarFoto(f)`, `imprimir(tipo)`.

- [ ] **Step 7: `docs/pendientes.md`** — agregar en una sección "Módulo 04: pendientes para el 05":
  - "El módulo 05 agrega `stock`/`stock_minimo` y completa lo que el 04 dejó afuera a propósito: `stock_inicial` en el alta (ingreso de proveedor vía `services.stock.aplicar_movimiento`), columna Stock y `bajo_minimo` en el listado y la ficha, toggle 'Stock 0' con checkboxes y 'Desactivar seleccionados', y `stock_cero` en `listar_productos`. El formulario ya expone `productoFormUtil.stockEntero`."

- [ ] **Step 8: Verificación final**
```bash
docker compose exec -T backend pytest -p no:warnings
for f in app categorias producto_form productos; do node --check backend/app/static/js/$f.js; done
node --test backend/tests_js/
```
Checklist manual (navegador, para el usuario): crear el árbol de categorías (3 niveles), mover y borrar; crear un producto en pesos y uno en dólares (ver el preview del precio), probar el duplicado y los parecidos; subir fotos y tomar una con la webcam; imprimir etiquetas rectangular y con colita; cambiar el dólar del proveedor y ver el precio recalculado.

- [ ] **Step 9: Commit** — `feat(productos): listado y ficha de productos`.
