# Módulo 05 — Control de stock: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stock por producto con movimientos trazables (un único camino: `aplicar_movimiento`), mínimo de reposición, ingresos, bajas con motivo, auditorías de inventario (conteos) con PDF/Excel, hub "Gestión de Stock" y sus pantallas; y completar lo del módulo 04 que dependía del stock (stock inicial en el alta, columna Stock, "Stock 0" y desactivación masiva).

**Architecture:** Igual que 02-04: API REST (`/api/v1/stock`, `/api/v1/auditorias-inventario`) con services sin commit, errores tipados y auditoría en la misma transacción; pantallas Jinja + un componente Alpine por pantalla. `services/stock.py::aplicar_movimiento` es el ÚNICO lugar que escribe `productos.stock` (bloquea la fila del producto). Las ventas (módulo 06) lo usarán con `permitir_faltante=True`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (SQL a mano), PostgreSQL 15, WeasyPrint (`app/reports/pdf.py`), openpyxl (`app/core/excel.py`), Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/05_stock.md` + `CLAUDE.md` + `docs/pendientes.md` (sección "Módulo 04: pendientes para el 05" y "Patrones que 03-09 deben copiar").

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `modulo-05-stock`. UN commit por tarea: `feat(stock): …` (o `fix(…): …`) + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout de otra rama. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo:** verificar con tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest -p no:warnings`, suite completa antes de cada commit). JS: `node --check` y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores `DatoInvalido` 400 / `SinPermiso` 403 / `NoEncontrado` 404 / `ReglaDeNegocio` 409; auditoría con `registrar_auditoria` y `estado_anterior` tomado ANTES del cambio; **validar todo antes de modificar**; locks (`FOR UPDATE` + `populate_existing`) donde dos operaciones simultáneas puedan pisarse. Routers hacen `db.commit()`.
- Límites contra las columnas: cantidades enteras entre 1 y 1.000.000 en schemas; el stock resultante nunca puede salir del rango de INTEGER (tope ±2.000.000.000 → 400). Nunca un 500 por datos del usuario.
- Filtros de texto con `filtro_texto`; búsqueda por código SIEMPRE con `productos.condiciones_codigo` (definición única).
- Pantallas: `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; sin `x-html` con datos de la API sin escapar; escrituras con `pedir()`; cargas que se pueden pisar secuenciadas con su propio `ultimaRespuesta()` y descartadas si cambió el id abierto; `erroresDeCampos()` para 422; `confirmar()` antes de acciones destructivas; reusar macros; modales solo se cierran con la X; mobile-first, `min-h-toque`, tablas en `overflow-x-auto`.

## Decisiones y desvíos

1. `incluir_sin_stock` en `listar_stock`: por defecto `True`; con `False` solo stock > 0.
2. Un `ajuste_auditoria` que dejaría stock negativo (vendieron entre el conteo y el cierre) da 409 y no cierra el conteo: el usuario vuelve a contar ese producto. Es lo que pide el spec ("baja o ajuste sin stock suficiente → 409").
3. Los productos con `stock_infinito` no se pueden contar en una auditoría (400) ni reciben mínimo (400): no tienen stock que controlar.
4. Excel de la auditoría con un helper nuevo `core/excel.py::generar_tabla(hoja, columnas, filas) -> bytes` (una sola hoja, misma protección contra fórmulas); `generar_plantilla` lo reusa.
5. El módulo 04 recibe acá lo que dejó para el 05: `stock_inicial` (int ≥ 0) en `ProductoCrear` → `registrar_ingreso` con nota "Stock inicial"; `stock`, `stock_minimo` y `bajo_minimo` en `ProductoResponse`; filtro `stock_cero` en `listar_productos`; en la UI, campo Stock inicial, columna Stock (resaltada si `bajo_minimo`, roja si negativa), toggle "Stock 0" con checkboxes y "Desactivar seleccionados".

---

## File Structure

```
backend/migrations/versions/0005_stock.py                 (new) Task 1
backend/app/models/stock.py, productos.py, __init__.py    (new/mod) Task 1
backend/tests/test_modelo_stock.py                        (new) Task 1
backend/app/schemas/stock.py                              (new) Tasks 2-4
backend/app/services/stock.py                             (new) Task 2
backend/tests/test_stock.py                               (new) Task 2
backend/app/services/bajas_stock.py                       (new) Task 3
backend/tests/test_bajas_stock.py                         (new) Task 3
backend/app/services/auditoria_inventario.py              (new) Task 4
backend/app/core/excel.py                                 (mod) Task 4
backend/app/reports/auditoria_pdf.py, templates/reports/auditoria_inventario.html  (new) Task 4
backend/tests/test_auditoria_inventario.py                (new) Task 4
backend/app/schemas/productos.py, services/productos.py   (mod) Task 5
backend/tests/test_productos_stock.py                     (new) Task 5
backend/app/api/v1/stock.py, auditorias_inventario.py, productos.py, __init__.py  (new/mod) Task 6
backend/tests/test_stock_api.py                           (new) Task 6
backend/app/api/pages.py                                  (mod) Tasks 7-9
backend/app/templates/pages/stock/{hub,listado}.html, static/js/stock.js       (new) Task 7
backend/app/templates/pages/motivos_baja/listado.html, static/js/motivos_baja.js  (new) Task 8
backend/app/templates/pages/auditorias/{listado,conteo}.html, static/js/auditorias.js  (new) Task 9
backend/tests/test_paginas_stock.py                       (new) Tasks 7-9
backend/app/templates/components/producto_form.html, pages/productos/*, static/js/{producto_form,productos}.js  (mod) Task 10
docs/pendientes.md                                        (mod) Task 10
```

---

### Task 1: Migración 0005 y modelos

**Files:**
- Create: `backend/migrations/versions/0005_stock.py`, `backend/app/models/stock.py`
- Modify: `backend/app/models/productos.py` (columnas `stock`, `stock_minimo`, propiedad `bajo_minimo`), `backend/app/models/__init__.py`
- Test: `backend/tests/test_modelo_stock.py`

**Interfaces:**
- Produces: `TipoMovimientoStock` (`INGRESO_PROVEEDOR="ingreso_proveedor"`, `VENTA="venta"`, `ANULACION_VENTA="anulacion_venta"`, `BAJA="baja"`, `AJUSTE_AUDITORIA="ajuste_auditoria"`), `EstadoAuditoriaInventario` (`EN_CURSO="en_curso"`, `CERRADA="cerrada"`), modelos `MovimientoStock`, `AuditoriaInventario` (relación `items` ordenada por id, `usuario`), `AuditoriaItem` (`diferencia` como `Computed`, relación `producto`); `Producto.stock`, `Producto.stock_minimo`, `Producto.bajo_minimo` (propiedad Python: `stock_minimo > 0 and stock <= stock_minimo`) y `BAJO_MINIMO_SQL` (expresión SQLAlchemy equivalente, para filtros: `and_(Producto.stock_minimo > 0, Producto.stock <= Producto.stock_minimo)`), definida en `models/productos.py`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_modelo_stock.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditoriaInventario, AuditoriaItem, Categoria, EstadoAuditoriaInventario, Moneda, MotivoBaja,
    MovimientoStock, Producto, Proveedor, TipoMovimientoStock, Usuario,
)


@pytest.fixture
def base(db, crear_usuario):
    usuario = crear_usuario("admin")
    cat = Categoria(nombre="Stock cat", nivel=1)
    prov = Proveedor(nombre="Stock prov", moneda=Moneda.ARS)
    db.add_all([cat, prov])
    db.flush()
    producto = Producto(sku="AA001", verificador="9", descripcion="Con stock", categoria_id=cat.id,
                        proveedor_id=prov.id, costo=Decimal("1"), margen=Decimal("0"), precio_venta=Decimal("1"))
    motivo = db.scalar(select(MotivoBaja).limit(1))
    db.add(producto)
    db.flush()
    db.refresh(producto)
    return {"usuario": usuario, "producto": producto, "motivo": motivo, "categoria": cat}


def _mov(base, **extra):
    datos = dict(tipo=TipoMovimientoStock.INGRESO_PROVEEDOR, producto_id=base["producto"].id, cantidad=5,
                 stock_resultante=5, usuario_id=base["usuario"].id)
    datos.update(extra)
    return MovimientoStock(**datos)


def test_stock_y_minimo_por_defecto(db, base):
    p = base["producto"]
    assert (p.stock, p.stock_minimo, p.bajo_minimo) == (0, 0, False)
    p.stock_minimo, p.stock = 3, 3
    assert p.bajo_minimo
    p.stock = 4
    assert not p.bajo_minimo
    p.stock_minimo = -1
    with pytest.raises(IntegrityError):
        db.flush()


def test_movimiento_valido(db, base):
    db.add(_mov(base))
    db.flush()
    assert db.execute(text("SELECT tipo::text FROM movimientos_stock")).scalars().all()[-1] == "ingreso_proveedor"


@pytest.mark.parametrize("extra", [
    {"cantidad": 0},
    {"cantidad": -1},                                                          # ingreso negativo
    {"tipo": TipoMovimientoStock.BAJA, "cantidad": 2},                        # baja positiva
    {"tipo": TipoMovimientoStock.BAJA, "cantidad": -2},                       # baja sin motivo
    {"tipo": TipoMovimientoStock.VENTA, "cantidad": -1},                      # venta sin referencia
    {"tipo": TipoMovimientoStock.ANULACION_VENTA, "cantidad": 1},             # anulación sin referencia
    {"tipo": TipoMovimientoStock.AJUSTE_AUDITORIA, "cantidad": 1},            # ajuste sin auditoría
])
def test_checks_de_movimientos(db, base, extra):
    db.add(_mov(base, **extra))
    with pytest.raises(IntegrityError):
        db.flush()


def test_baja_con_motivo_y_venta_con_referencia(db, base):
    db.add_all([_mov(base, tipo=TipoMovimientoStock.BAJA, cantidad=-1, motivo_baja_id=base["motivo"].id),
                _mov(base, tipo=TipoMovimientoStock.VENTA, cantidad=-1, referencia_venta_id=123)])
    db.flush()


def test_una_sola_auditoria_en_curso_y_diferencia_generada(db, base):
    a = AuditoriaInventario(usuario_id=base["usuario"].id)
    db.add(a)
    db.flush()
    assert a.estado is EstadoAuditoriaInventario.EN_CURSO
    item = AuditoriaItem(auditoria_id=a.id, producto_id=base["producto"].id, cantidad_sistema=5, cantidad_contada=3)
    db.add(item)
    db.flush()
    db.refresh(item)
    assert item.diferencia == -2
    db.add(AuditoriaInventario(usuario_id=base["usuario"].id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_item_unico_y_contada_no_negativa(db, base):
    a = AuditoriaInventario(usuario_id=base["usuario"].id)
    db.add(a)
    db.flush()
    db.add(AuditoriaItem(auditoria_id=a.id, producto_id=base["producto"].id, cantidad_sistema=0, cantidad_contada=-1))
    with pytest.raises(IntegrityError):
        db.flush()
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Migración** — `0005_stock.py` (revision "0005", down "0004", estilo de la 0004):

```sql
ALTER TABLE productos
    ADD COLUMN stock        INTEGER NOT NULL DEFAULT 0,   -- solo lo escribe services.stock.aplicar_movimiento
    ADD COLUMN stock_minimo INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_productos_stock_minimo CHECK (stock_minimo >= 0);

CREATE TYPE tipo_movimiento_stock AS ENUM ('ingreso_proveedor', 'venta', 'anulacion_venta', 'baja', 'ajuste_auditoria');
CREATE TYPE estado_auditoria_inventario AS ENUM ('en_curso', 'cerrada');

CREATE TABLE auditorias_inventario (
    id                  BIGSERIAL PRIMARY KEY,
    usuario_id          BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
    estado              estado_auditoria_inventario NOT NULL DEFAULT 'en_curso',
    filtro_categoria_id BIGINT REFERENCES categorias (id) ON DELETE RESTRICT,   -- informativo
    fecha_inicio        TIMESTAMP NOT NULL DEFAULT now(),
    fecha_fin           TIMESTAMP,
    notas               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_auditorias_inventario_estado ON auditorias_inventario (estado);
CREATE INDEX ix_auditorias_inventario_fecha_inicio ON auditorias_inventario (fecha_inicio);
-- Una sola auditoría en curso a la vez.
CREATE UNIQUE INDEX uq_auditoria_inventario_en_curso ON auditorias_inventario ((true)) WHERE estado = 'en_curso';

CREATE TABLE auditoria_items (
    id               BIGSERIAL PRIMARY KEY,
    auditoria_id     BIGINT NOT NULL REFERENCES auditorias_inventario (id) ON DELETE CASCADE,
    producto_id      BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
    cantidad_sistema INTEGER NOT NULL,        -- foto del stock AL REGISTRAR el ítem
    cantidad_contada INTEGER NOT NULL,
    diferencia       INTEGER GENERATED ALWAYS AS (cantidad_contada - cantidad_sistema) STORED,
    CONSTRAINT ck_auditoria_items_contada CHECK (cantidad_contada >= 0),
    CONSTRAINT uq_auditoria_items_producto UNIQUE (auditoria_id, producto_id)
);
CREATE INDEX ix_auditoria_items_producto_id ON auditoria_items (producto_id);

-- Append-only en la práctica: los errores se corrigen con otro movimiento.
CREATE TABLE movimientos_stock (
    id                  BIGSERIAL PRIMARY KEY,
    tipo                tipo_movimiento_stock NOT NULL,
    producto_id         BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
    cantidad            INTEGER NOT NULL,
    stock_resultante    INTEGER NOT NULL,
    motivo_baja_id      BIGINT REFERENCES motivos_baja (id) ON DELETE RESTRICT,
    auditoria_id        BIGINT REFERENCES auditorias_inventario (id) ON DELETE RESTRICT,
    referencia_venta_id BIGINT,                 -- la FK a ventas se agrega en la sesión 06
    usuario_id          BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
    timestamp           TIMESTAMP NOT NULL DEFAULT now(),
    notas               TEXT,
    CONSTRAINT ck_movimientos_cantidad CHECK (cantidad <> 0),
    CONSTRAINT ck_movimientos_signo CHECK (
        (tipo IN ('ingreso_proveedor', 'anulacion_venta') AND cantidad > 0) OR
        (tipo IN ('venta', 'baja') AND cantidad < 0) OR
        (tipo = 'ajuste_auditoria')
    ),
    CONSTRAINT ck_movimientos_venta CHECK (tipo NOT IN ('venta', 'anulacion_venta') OR referencia_venta_id IS NOT NULL),
    CONSTRAINT ck_movimientos_baja CHECK (tipo <> 'baja' OR motivo_baja_id IS NOT NULL),
    CONSTRAINT ck_movimientos_ajuste CHECK (tipo <> 'ajuste_auditoria' OR auditoria_id IS NOT NULL)
);
CREATE INDEX ix_movimientos_stock_tipo ON movimientos_stock (tipo);
CREATE INDEX ix_movimientos_stock_producto_id ON movimientos_stock (producto_id);
CREATE INDEX ix_movimientos_stock_referencia_venta_id ON movimientos_stock (referencia_venta_id);
CREATE INDEX ix_movimientos_stock_timestamp ON movimientos_stock (timestamp);
```
Downgrade: drop `movimientos_stock`, `auditoria_items`, `auditorias_inventario`, los dos tipos, y `ALTER TABLE productos DROP CONSTRAINT ck_productos_stock_minimo, DROP COLUMN stock_minimo, DROP COLUMN stock`.

- [ ] **Step 4: Modelos** — en `models/productos.py` agregar a `Producto`:
```python
    # Desnormalizado a propósito (campo calculable desde movimientos_stock):
    # se guarda para listar/filtrar/vender sin sumar el historial. SOLO lo
    # escribe services.stock.aplicar_movimiento (bloquea la fila).
    stock: Mapped[int] = mapped_column(Integer, default=0)
    stock_minimo: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def bajo_minimo(self) -> bool:
        return self.stock_minimo > 0 and self.stock <= self.stock_minimo
```
y, después de la clase, `BAJO_MINIMO_SQL = and_(Producto.stock_minimo > 0, Producto.stock <= Producto.stock_minimo)`.

`models/stock.py` (enums con `enum_db`; `MovimientoStock` con relaciones `producto`, `usuario`, `motivo_baja` lazy="joined" para el historial; `AuditoriaInventario` con `items` `relationship(order_by="AuditoriaItem.id", lazy="selectin", passive_deletes=True)` y `usuario` joined; `AuditoriaItem.diferencia: Mapped[int] = mapped_column(Integer, Computed("cantidad_contada - cantidad_sistema", persisted=True))`, relación `producto` joined). Exportar todo en `models/__init__.py` (incluido `BAJO_MINIMO_SQL`).

- [ ] **Step 5: Migrar y correr** — `docker compose restart backend`, `alembic current` → 0005; tests del modelo; `alembic downgrade -1 && alembic upgrade head`; suite completa.

- [ ] **Step 6: Commit** — `feat(stock): migración 0005 y modelos de stock, movimientos y auditorías de inventario`.

---

### Task 2: Service de stock (`aplicar_movimiento` y consultas)

**Files:**
- Create: `backend/app/schemas/stock.py`, `backend/app/services/stock.py`
- Test: `backend/tests/test_stock.py`

**Interfaces:**
- Consumes: modelos de Task 1, `productos.condiciones_codigo`, `productos.obtener_producto`, `categorias.rama_de_ids`, `categorias.caminos`, `paginar`, `rango_fechas`, auditoría, errores.
- Produces (schemas): `IngresoCrear {producto_id, cantidad: int (1..1_000_000), notas: str|None (≤500)}`, `MinimoEditar {stock_minimo: int (0..1_000_000)}`, `StockResponse {producto_id, codigo, descripcion, categoria (camino), proveedor (nombre), stock, stock_minimo, bajo_minimo, stock_infinito, foto_url}` (+ `StockResponse.desde(producto, camino)`), `ResumenStock {productos_con_stock, unidades, valorizado: Decimal, bajo_minimo}`, `MovimientoResponse {id, tipo, producto_id, codigo, descripcion, cantidad, stock_resultante, motivo_baja: str|None, auditoria_id, referencia_venta_id, usuario_id, usuario_nombre, timestamp, notas}` (+ `.desde(m)`).
- Produces (service): `TAMANO_MAXIMO = 100`, `STOCK_MAXIMO = 2_000_000_000`, `aplicar_movimiento(db, autor, *, tipo, producto_id, cantidad, motivo_baja_id=None, auditoria_id=None, referencia_venta_id=None, permitir_faltante=False, notas=None, ip_origen=None) -> MovimientoStock`, `registrar_ingreso(db, autor, producto_id, cantidad, notas, ip) -> MovimientoStock`, `definir_minimo(db, autor, producto_id, stock_minimo, ip) -> Producto`, `listar_stock(db, *, busqueda=None, categoria_id=None, proveedor_id=None, solo_bajo_minimo=False, incluir_sin_stock=True, pagina=1, tamano=10) -> tuple[list[Producto], int]`, `alertas(db, limite=20) -> list[Producto]`, `resumen(db) -> dict`, `listar_movimientos(db, *, producto_id=None, tipo=None, desde=None, hasta=None, pagina=1, tamano=10) -> tuple[list[MovimientoStock], int]`, `a_respuesta(db, productos) -> list[StockResponse]`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_stock.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, MotivoBaja, MovimientoStock, TipoMovimientoStock
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear, ProductoEditar
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores
from app.services import stock as servicio


@pytest.fixture
def base(db, crear_usuario):
    admin = crear_usuario("admin")
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa stock"), None)
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras stock", parent_id=ropa.id), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov stock", moneda="ars"), None)

    def alta(descripcion, **extra):
        datos = {"categoria_id": hoja.id, "proveedor_id": prov.id, "costo": "1000", "margen": "0",
                 "descripcion": descripcion}
        datos.update(extra)
        return servicio_productos.crear_producto(db, admin, ProductoCrear(**datos), None)

    return {"admin": admin, "ropa": ropa, "hoja": hoja, "prov": prov, "alta": alta,
            "motivo": db.scalar(select(MotivoBaja).limit(1))}


def test_ingreso_actualiza_stock_y_audita(db, base):
    p = base["alta"]("Remera ingreso")
    m = servicio.registrar_ingreso(db, base["admin"], p.id, 10, "Compra", None)
    assert (m.cantidad, m.stock_resultante, m.tipo) == (10, 10, TipoMovimientoStock.INGRESO_PROVEEDOR)
    assert p.stock == 10
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "stock.ingreso_proveedor", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior == {"stock": 0} and registro.estado_nuevo["stock"] == 10


def test_salida_sin_stock_suficiente(db, base):
    p = base["alta"]("Remera faltante")
    servicio.registrar_ingreso(db, base["admin"], p.id, 2, None, None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-3,
                                    motivo_baja_id=base["motivo"].id)
    assert error.value.mensaje == "No hay stock suficiente de 'Remera faltante': hay 2 y se piden 3"
    assert p.stock == 2
    assert db.scalar(select(MovimientoStock).where(MovimientoStock.tipo == TipoMovimientoStock.BAJA)) is None


def test_venta_con_faltante_deja_negativo(db, base):
    p = base["alta"]("Remera venta")
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.VENTA, producto_id=p.id, cantidad=-2,
                                    referencia_venta_id=1, permitir_faltante=True)
    assert m.stock_resultante == -2 and p.stock == -2


def test_permitir_faltante_solo_ventas(db, base):
    p = base["alta"]("Remera sin faltante")
    with pytest.raises(DatoInvalido):
        servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-1,
                                    motivo_baja_id=base["motivo"].id, permitir_faltante=True)


@pytest.mark.parametrize("tipo, cantidad", [
    (TipoMovimientoStock.INGRESO_PROVEEDOR, -1), (TipoMovimientoStock.BAJA, 1), (TipoMovimientoStock.VENTA, 1),
    (TipoMovimientoStock.INGRESO_PROVEEDOR, 0),
])
def test_signo_incoherente(db, base, tipo, cantidad):
    p = base["alta"]("Remera signo")
    with pytest.raises(DatoInvalido):
        servicio.aplicar_movimiento(db, base["admin"], tipo=tipo, producto_id=p.id, cantidad=cantidad,
                                    motivo_baja_id=base["motivo"].id, referencia_venta_id=1)


def test_stock_infinito_no_se_toca(db, base):
    p = base["alta"]("Remera infinita", stock_infinito=True)
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.VENTA, producto_id=p.id, cantidad=-5,
                                    referencia_venta_id=1)
    assert p.stock == 0 and m.stock_resultante == 0
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-5,
                                    motivo_baja_id=base["motivo"].id)
    assert m.stock_resultante == 0


def test_tope_de_stock(db, base):
    p = base["alta"]("Remera tope")
    servicio.registrar_ingreso(db, base["admin"], p.id, 1_000_000, None, None)
    p.stock = servicio.STOCK_MAXIMO - 10          # simula un stock enorme (solo para el test)
    db.flush()
    with pytest.raises(DatoInvalido):
        servicio.registrar_ingreso(db, base["admin"], p.id, 11, None, None)


def test_producto_inexistente(db, base):
    with pytest.raises(NoEncontrado):
        servicio.registrar_ingreso(db, base["admin"], 999999, 1, None, None)


def test_minimo(db, base):
    p = base["alta"]("Remera mínimo")
    servicio.definir_minimo(db, base["admin"], p.id, 3, None)
    assert p.stock_minimo == 3 and p.bajo_minimo
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "stock.minimo", Auditoria.entidad_id == p.id))
    infinito = base["alta"]("Remera infinita mínimo", stock_infinito=True)
    with pytest.raises(DatoInvalido):
        servicio.definir_minimo(db, base["admin"], infinito.id, 1, None)


def test_listar_stock(db, base):
    a = base["alta"]("Remera lista A")
    b = base["alta"]("Remera lista B")
    infinito = base["alta"]("Remera lista infinita", stock_infinito=True)
    inactivo = base["alta"]("Remera lista inactiva")
    servicio_productos.cambiar_estado_producto(db, base["admin"], inactivo, False, None)
    servicio.registrar_ingreso(db, base["admin"], a.id, 5, None, None)
    servicio.definir_minimo(db, base["admin"], b.id, 2, None)
    ids = lambda **f: {p.id for p in servicio.listar_stock(db, proveedor_id=base["prov"].id, **f)[0]}
    assert ids() == {a.id, b.id}                                  # sin infinitos ni inactivos
    assert ids(solo_bajo_minimo=True) == {b.id}
    assert ids(incluir_sin_stock=False) == {a.id}
    assert ids(busqueda=infinito.codigo_con_verificador) == {infinito.id}   # por código sí aparece
    assert ids(categoria_id=base["ropa"].id) == {a.id, b.id}      # filtro por rama
    assert ids(busqueda="lista a") == {a.id}


def test_alertas_y_resumen(db, base):
    a = base["alta"]("Remera resumen A", costo="100")
    b = base["alta"]("Remera resumen B", costo="100")
    servicio.registrar_ingreso(db, base["admin"], a.id, 4, None, None)
    servicio.definir_minimo(db, base["admin"], b.id, 1, None)
    assert b.id in {p.id for p in servicio.alertas(db)}
    r = servicio.resumen(db)
    assert r["productos_con_stock"] >= 1 and r["unidades"] >= 4 and r["bajo_minimo"] >= 1
    assert r["valorizado"] >= Decimal("4") * a.precio_venta


def test_movimientos(db, base):
    p = base["alta"]("Remera movimientos")
    servicio.registrar_ingreso(db, base["admin"], p.id, 3, "Primera", None)
    servicio.registrar_ingreso(db, base["admin"], p.id, 2, "Segunda", None)
    items, total = servicio.listar_movimientos(db, producto_id=p.id)
    assert total == 2 and [m.notas for m in items] == ["Segunda", "Primera"]      # más reciente primero
    assert servicio.listar_movimientos(db, producto_id=p.id, tipo=TipoMovimientoStock.BAJA)[1] == 0
    assert servicio.listar_movimientos(db, producto_id=p.id, desde=date(2000, 1, 1), hasta=date.today())[1] == 2


def test_stock_no_esta_en_los_schemas_de_producto():
    assert "stock" not in ProductoEditar.model_fields and "stock" not in ProductoCrear.model_fields
```

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación.** Núcleo (exacto):

```python
SIGNO_POR_TIPO = {
    TipoMovimientoStock.INGRESO_PROVEEDOR: 1, TipoMovimientoStock.ANULACION_VENTA: 1,
    TipoMovimientoStock.VENTA: -1, TipoMovimientoStock.BAJA: -1,
    TipoMovimientoStock.AJUSTE_AUDITORIA: 0,        # cualquier signo
}
STOCK_MAXIMO = 2_000_000_000


def aplicar_movimiento(db, autor, *, tipo, producto_id, cantidad, motivo_baja_id=None, auditoria_id=None,
                       referencia_venta_id=None, permitir_faltante=False, notas=None, ip_origen=None):
    """ÚNICO camino por el que cambia productos.stock. Bloquea la fila del
    producto, valida, guarda el stock resultante y audita. Sin commit."""
    signo = SIGNO_POR_TIPO[tipo]
    if cantidad == 0 or (signo and (cantidad > 0) != (signo > 0)):
        raise DatoInvalido("La cantidad no corresponde al tipo de movimiento.")
    if permitir_faltante and tipo is not TipoMovimientoStock.VENTA:
        raise DatoInvalido("Solo una venta puede dejar el stock en negativo.")
    producto = db.get(Producto, producto_id, with_for_update=True, populate_existing=True)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    antes = producto.stock
    resultante = antes if producto.stock_infinito else antes + cantidad
    if not producto.stock_infinito:
        if cantidad < 0 and resultante < 0 and not permitir_faltante:
            raise ReglaDeNegocio(
                f"No hay stock suficiente de '{producto.descripcion}': hay {antes} y se piden {-cantidad}")
        if abs(resultante) > STOCK_MAXIMO:
            raise DatoInvalido("El stock resultante está fuera del rango permitido.")
    movimiento = MovimientoStock(tipo=tipo, producto_id=producto.id, cantidad=cantidad, stock_resultante=resultante,
                                 motivo_baja_id=motivo_baja_id, auditoria_id=auditoria_id,
                                 referencia_venta_id=referencia_venta_id, usuario_id=autor.id,
                                 timestamp=ahora_db(), notas=(notas or "").strip() or None)
    producto.stock = resultante
    db.add(movimiento)
    db.flush()
    registrar_auditoria(db, accion=f"stock.{tipo.value}", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_anterior={"stock": antes},
                        estado_nuevo={"stock": resultante, "cantidad": cantidad, "movimiento_id": movimiento.id},
                        ip_origen=ip_origen)
    return movimiento
```
El resto según las interfaces:
- `registrar_ingreso`: `aplicar_movimiento(tipo=INGRESO_PROVEEDOR, cantidad=cantidad, ...)` (valida `cantidad` entero > 0 → `DatoInvalido`).
- `definir_minimo`: bloquea el producto igual que arriba; `stock_infinito` → `DatoInvalido("Un producto con stock infinito no lleva mínimo.")`; `stock_minimo < 0` → `DatoInvalido`; si no cambia, no audita; audita `stock.minimo` con `{"stock_minimo": antes}` / `{"stock_minimo": nuevo}`.
- `listar_stock`: condiciones `Producto.activo.is_(True)`; si hay `busqueda`: `or_(condiciones_codigo(b), filtro_texto(sku_proveedor), filtro_texto(descripcion))` y, **solo** si la búsqueda NO matchea por código, excluye `stock_infinito` → implementalo como `or_(Producto.stock_infinito.is_(False), condiciones_codigo(b))` (los infinitos aparecen solo si el código coincide); sin búsqueda, `stock_infinito.is_(False)`; `categoria_id` por rama; `proveedor_id`; `solo_bajo_minimo` → `BAJO_MINIMO_SQL`; `incluir_sin_stock=False` → `stock > 0`; orden `lower(descripcion), sku`; paginado con `paginar` y total con count.
- `alertas(limite)`: activos, sin infinito, `BAJO_MINIMO_SQL`, orden por `stock - stock_minimo` ascendente, `limit`.
- `resumen`: una sola query con `func.count().filter(stock > 0)`, `func.coalesce(func.sum(stock).filter(stock > 0), 0)`, `coalesce(sum(stock * precio_venta).filter(stock > 0), 0)` y `count().filter(BAJO_MINIMO_SQL)`, sobre activos sin infinito; `valorizado` redondeado.
- `listar_movimientos`: filtros; `rango_fechas(MovimientoStock.timestamp, desde, hasta)`; orden `timestamp desc, id desc`; paginado.
- `a_respuesta`: una sola llamada a `categorias.caminos(db)`.

- [ ] **Step 4: Correr** — archivo + suite.

- [ ] **Step 5: Commit** — `feat(stock): movimientos de stock, ingresos, mínimos y consultas`.

---

### Task 3: Motivos y bajas de stock

**Files:**
- Create: `backend/app/services/bajas_stock.py`; Modify: `backend/app/schemas/stock.py`
- Test: `backend/tests/test_bajas_stock.py`

**Interfaces:**
- Consumes: `aplicar_movimiento`, `MotivoBaja`, auditoría.
- Produces (schemas): `MotivoBajaCrear {nombre (1..100)}`, `MotivoBajaEditar {nombre, activo: bool}`, `MotivoBajaResponse {id, nombre, activo}`, `BajaCrear {producto_id, cantidad: int (1..1_000_000), motivo_baja_id, notas (≤500)}`.
- Produces (service): `obtener_motivo(db, id)`, `listar_motivos(db, *, nombre=None, activo=None) -> list[MotivoBaja]` (orden por nombre), `crear_motivo(db, autor, datos, ip)`, `editar_motivo(db, autor, motivo, datos, ip)`, `registrar_baja(db, autor, producto_id, cantidad, motivo_baja_id, notas, ip) -> MovimientoStock`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_bajas_stock.py`:
  - motivo: alta con nombre normalizado; duplicado sin mayúsculas ni tildes → 409; editar (nombre y activo) audita `motivo_baja.editar` con estado anterior; validar antes de modificar (duplicado al editar deja el objeto intacto); `listar_motivos(activo=True)` y filtro por nombre sin tildes.
  - baja: `registrar_baja(… cantidad=2 …)` guarda `-2`, `stock_resultante` correcto, motivo en el movimiento, audita `stock.baja`; motivo inactivo → 409 "El motivo de baja no está activo."; motivo inexistente → 404; cantidad 0 → 400; sin stock suficiente → 409 (lo da `aplicar_movimiento`).
  (Escribí los tests completos con el mismo estilo de `test_stock.py`, reusando su fixture de productos copiada en el archivo.)

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación** — seguir el patrón de `services/proveedores.py` para el nombre único (`func.lower(sin_tildes_sql(...))`, mensaje `"Ya existe el motivo '<nombre>'"`). `registrar_baja`: obtener y validar el motivo ANTES de llamar a `aplicar_movimiento(tipo=BAJA, cantidad=-cantidad, motivo_baja_id=…)`.

- [ ] **Step 4: Correr** — archivo + suite.

- [ ] **Step 5: Commit** — `feat(stock): motivos y bajas de stock`.

---

### Task 4: Auditorías de inventario (conteos) con PDF y Excel

**Files:**
- Create: `backend/app/services/auditoria_inventario.py`, `backend/app/reports/auditoria_pdf.py`, `backend/app/templates/reports/auditoria_inventario.html`
- Modify: `backend/app/core/excel.py` (agregar `generar_tabla`, y que `generar_plantilla` la reuse), `backend/app/schemas/stock.py`
- Test: `backend/tests/test_auditoria_inventario.py`

**Interfaces:**
- Consumes: modelos, `aplicar_movimiento`, `buscar_por_codigo` (para registrar por código desde la pantalla, vía API), `pdf.imprimir`, `generar_tabla`.
- Produces (schemas): `AuditoriaIniciar {filtro_categoria_id: int|None, notas (≤500)}`, `ItemContado {producto_id, cantidad_contada: int (0..1_000_000)}`, `ItemsRegistrar {items: list[ItemContado] (1..500)}`, `ItemEditar {cantidad_contada}`, `AuditoriaItemResponse {id, producto_id, codigo, descripcion, cantidad_sistema, cantidad_contada, diferencia}`, `AuditoriaResponse {id, estado, usuario_id, usuario_nombre, filtro_categoria_id, fecha_inicio, fecha_fin, notas, cantidad_items}`, `AuditoriaDetalle` (+ `items`).
- Produces (service): `obtener_auditoria(db, id, bloquear=False)`, `en_curso(db) -> AuditoriaInventario | None`, `iniciar(db, autor, datos, ip)`, `registrar_items(db, autor, auditoria, items, ip) -> list[AuditoriaItem]`, `editar_item(db, autor, auditoria, item_id, cantidad_contada, ip)`, `eliminar_item(db, autor, auditoria, item_id, ip)`, `finalizar(db, autor, auditoria, ip) -> AuditoriaInventario`, `listar(db, *, estado=None, desde=None, hasta=None, pagina=1, tamano=10) -> tuple[list, int]`; `auditoria_pdf.generar_pdf_auditoria(db, auditoria) -> bytes`, `auditoria_pdf.generar_xls_auditoria(db, auditoria) -> bytes`; `excel.generar_tabla(hoja, columnas, filas) -> bytes`.

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_auditoria_inventario.py` (completos, mismo estilo que `test_stock.py`):
  1. `iniciar` crea en curso y audita `auditoria_inventario.iniciar`; un segundo `iniciar` → 409 "Ya hay un conteo en curso."; categoría inexistente → 404.
  2. `registrar_items`: captura `cantidad_sistema` = stock AL REGISTRAR; registrar de nuevo el mismo producto sobreescribe `cantidad_contada` Y vuelve a capturar `cantidad_sistema`; producto con stock infinito → 400; producto inexistente → 404; auditoría cerrada → 409.
  3. `editar_item`/`eliminar_item`: solo en curso (409 si cerrada); ítem de otra auditoría → 404.
  4. `finalizar`: sin ítems → 409; con ítems genera un `ajuste_auditoria` por diferencia ≠ 0 (cantidad = diferencia, `auditoria_id` seteado), ninguno para diferencia 0; stock final = contado; estado `cerrada`, `fecha_fin` seteada; audita `auditoria_inventario.cerrar`; después de cerrar se puede iniciar otra.
  5. Ajuste que dejaría negativo (se vendió entre el conteo y el cierre: bajar el stock con una venta con `permitir_faltante` después de registrar) → 409 y la auditoría sigue en curso, sin ningún ajuste aplicado.
  6. `listar` por estado y fechas.
  7. PDF: `generar_pdf_auditoria` empieza con `b"%PDF"`; el HTML contiene el código y la diferencia. Excel: `load_workbook` del resultado tiene encabezados `["Código", "Descripción", "Sistema", "Contado", "Diferencia"]` y una fila por ítem; una descripción que empieza con "=" queda como texto (`data_type == "s"`).

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación.**
- `iniciar`: si `en_curso(db)` → 409; valida categoría; crea; `db.flush()`; si el índice único parcial salta por carrera, el handler de `IntegrityError` ya lo convierte en 409.
- Toda operación sobre una auditoría la obtiene con `obtener_auditoria(db, id, bloquear=True)` (`with_for_update` + `populate_existing`) y exige `EN_CURSO` (`ReglaDeNegocio("El conteo ya está cerrado.")`).
- `registrar_items`: por cada ítem obtiene el producto (`NoEncontrado`), rechaza `stock_infinito` (`DatoInvalido`), valida TODO antes de escribir; luego upsert (si existe el ítem de ese producto, actualiza `cantidad_contada` y `cantidad_sistema`; si no, crea). Productos repetidos dentro del mismo pedido: gana el último. Audita `auditoria_inventario.items` con la lista `{producto_id, cantidad_contada}`.
- `finalizar`: bloquea; sin ítems → 409 "Registrá al menos un producto antes de cerrar el conteo."; por cada ítem con `diferencia != 0` → `aplicar_movimiento(tipo=AJUSTE_AUDITORIA, cantidad=diferencia, auditoria_id=…, notas=f"Conteo #{id}")`. Si alguno falla, la excepción sube y el router hace rollback (nada queda aplicado). Luego `estado = CERRADA`, `fecha_fin = ahora_db()`, audita `auditoria_inventario.cerrar` con `{"ajustes": n}`.
- PDF: plantilla `reports/auditoria_inventario.html` A4 vertical, título "Conteo de inventario #N", fecha, usuario, estado, notas y tabla Código | Descripción | Sistema | Contado | Diferencia (diferencias ≠ 0 en negrita). Usar `pdf.imprimir`.
- Excel: `generar_tabla("Conteo", ["Código", "Descripción", "Sistema", "Contado", "Diferencia"], filas)`. `generar_tabla` = hoja única con encabezados en negrita, anchos ajustados, panel congelado y `_textos_como_texto`; `generar_plantilla` pasa a usarla y agrega la hoja de instrucciones (sin cambiar su comportamiento: sus tests siguen pasando).

- [ ] **Step 4: Correr** — archivo + `test_excel.py` + suite.

- [ ] **Step 5: Commit** — `feat(stock): auditorías de inventario con PDF y Excel`.

---

### Task 5: Productos con stock (lo que el 04 dejó para el 05)

**Files:**
- Modify: `backend/app/schemas/productos.py`, `backend/app/services/productos.py`
- Test: `backend/tests/test_productos_stock.py`

**Interfaces:**
- Produces: `ProductoCrear.stock_inicial: int = Field(0, ge=0, le=1_000_000)`; `ProductoResponse` (+ `ProductoDetalle`) con `stock: int`, `stock_minimo: int`, `bajo_minimo: bool`; `listar_productos(..., stock_cero: bool = False)` → `stock <= 0 AND NOT stock_infinito`.

- [ ] **Step 1: Tests que fallan** — `test_productos_stock.py`:
  - alta con `stock_inicial=7` → `stock == 7`, un movimiento `ingreso_proveedor` con nota "Stock inicial", auditorías `producto.crear` y `stock.ingreso_proveedor`; con 0 → sin movimiento.
  - alta con stock inicial y producto con stock infinito → sin movimiento de stock ni error? **Decisión:** si `stock_infinito` es True se ignora el stock inicial (no se registra movimiento).
  - `a_respuesta` trae `stock`, `stock_minimo`, `bajo_minimo`.
  - `listar_productos(stock_cero=True)` incluye stock 0 y negativo, excluye stock > 0 e infinitos.

- [ ] **Step 2: Correr y ver que falla.**

- [ ] **Step 3: Implementación** — en `crear_producto`, después de la auditoría del alta: `if datos.stock_inicial and not producto.stock_infinito:` importar local (`from app.services.stock import registrar_ingreso` — import local para evitar el ciclo productos ↔ stock) y llamar `registrar_ingreso(db, autor, producto.id, datos.stock_inicial, "Stock inicial", ip)`; `db.refresh(producto)` después. `ProductoResponse._campos` agrega los tres campos. `listar_productos` agrega `stock_cero`.

- [ ] **Step 4: Correr** — archivo + suite.

- [ ] **Step 5: Commit** — `feat(productos): stock inicial, stock en la respuesta y filtro de stock cero`.

---

### Task 6: Endpoints de stock y auditorías de inventario

**Files:**
- Create: `backend/app/api/v1/stock.py`, `backend/app/api/v1/auditorias_inventario.py`
- Modify: `backend/app/api/v1/__init__.py`, `backend/app/api/v1/productos.py` (query `stock_cero: bool = False`)
- Test: `backend/tests/test_stock_api.py`

**Interfaces:** los endpoints del spec (sección BACKEND — ENDPOINTS), con estas dependencias (patrón de `api/v1/proveedores.py`):
- `puede_ver = requiere_permiso(Modulo.STOCK, "ver")`
- `puede_ingresar = requiere_permiso(Modulo.STOCK, "crear")`
- `puede_minimos = requiere_permiso(Modulo.STOCK, "editar")`
- `puede_baja = requiere_permiso(Modulo.STOCK, "crear", Recurso.STOCK_BAJA)`
- `puede_motivos = requiere_permiso(Modulo.STOCK, "editar", Recurso.STOCK_MOTIVOS_BAJA)`
- `puede_auditar = requiere_permiso(Modulo.STOCK, "crear", Recurso.STOCK_AUDITORIA)`
Listados paginados con `RespuestaPaginada`, `pagina = Query(1, ge=1, le=100_000)`, `tamano = Query(10, ge=1, le=TAMANO_MAXIMO)`. `GET /stock/alertas?limite=` con `Query(20, ge=1, le=100)`. Rutas fijas de `/stock` (`/alertas`, `/resumen`, `/movimientos`, `/motivos-baja`, `/ingresos`, `/bajas`, `/minimos/{producto_id}`) — no hay `/{id}` genérico en ese router. En auditorías: `POST /{id}/items` además acepta `{codigo, cantidad_contada}` en un endpoint aparte `POST /{id}/items/por-codigo` (usa `buscar_por_codigo`) para el escáner de la pantalla; PDF inline (`application/pdf`) y Excel attachment (`TIPO_XLSX`, `filename="conteo-<id>.xlsx"`), ambos con `response_class=Response` y `responses=`.

- [ ] **Step 1: Tests que fallan** — `test_stock_api.py`:
  - vendedor: `GET /stock` 200; `POST /stock/ingresos` 403; `POST /stock/bajas` 201 (tiene `stock.baja`); `PUT /stock/minimos/{id}` 403; `POST /stock/motivos-baja` 403; `POST /auditorias-inventario` 201 (tiene `stock.auditoria`).
  - admin: ingreso (201, stock sube), mínimo (200), baja con motivo (201), movimientos del producto (2 filas, más reciente primero), resumen y alertas (200), listado con `solo_bajo_minimo`.
  - baja sin stock → 409 con el mensaje exacto.
  - auditoría: iniciar, registrar por id y por código (con verificador), editar y eliminar ítem, finalizar → stock ajustado; segundo iniciar mientras hay uno → 409; PDF (`%PDF`) y Excel (content-type xlsx).
  - `GET /api/v1/productos?stock_cero=true` filtra.
  - cantidades 0 y 1_000_001 → 422.

- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Routers** (commit en cada escritura; `ip_de_request`).
- [ ] **Step 4: Correr** — archivo + suite; `curl` sin auth a `/api/v1/stock` → 401.
- [ ] **Step 5: Commit** — `feat(stock): API de stock y auditorías de inventario`.

---

### Task 7: Hub "Gestión de Stock" y pantalla de stock

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/stock/hub.html`, `backend/app/templates/pages/stock/listado.html`, `backend/app/static/js/stock.js`
- Test: `backend/tests/test_paginas_stock.py`

**Interfaces:**
- Produces: `PAGINA_STOCK_HUB = {"nombre": "Gestión de Stock", "url": "/gestion-de-stock", "icono": "stock", "modulo": Modulo.STOCK}` en `MENU_SIDEBAR` después de Productos; `SECCION_STOCK` (`/stock`) y `SECCION_AUDITORIAS` (`/auditorias-inventario`) en `SECCIONES_STOCK` (descripciones del spec); `PAGINA_MOTIVOS_BAJA` (`/motivos-baja`, modulo STOCK, accion "editar", recurso `STOCK_MOTIVOS_BAJA`); helper `_contexto_stock(request, db, usuario, **extra)` con `puede_ingresar`, `puede_minimos`, `puede_baja`, `puede_motivos`, `puede_auditar` (vía `resolver_permiso` con el mismo módulo/acción/recurso que la API) y `actual="/gestion-de-stock"`; rutas `GET /gestion-de-stock` (macro `hub`), `GET /stock`; componente `stockListado({ puedeIngresar, puedeMinimos, puedeBaja })`.

- [ ] **Step 1: Tests que fallan** — `test_paginas_stock.py`: sidebar muestra `href="/gestion-de-stock"` al vendedor; el hub muestra las dos tarjetas; `/stock` del admin tiene `stockListado(`, `/static/js/stock.js?v=`, botón "Motivos de baja" y los flags en true; el vendedor ve `puedeBaja: true`, `puedeIngresar: false`, sin "Motivos de baja".

- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Rutas y plantillas.** Listado (`pages/stock/listado.html`): encabezado "Stock" con volver al hub y botón "Motivos de baja" (si `puede_motivos`); tarjetas con los 4 números de `/stock/resumen` (grilla `grid-cols-2 lg:grid-cols-4`, valorizado con `pesos()`); `barra_filtros` con búsqueda (debounce 400), `combobox` Categoría (camino) y Proveedor (lista de `GET /api/v1/productos/proveedores`), `switch` "Solo bajo mínimo"; `tabla` con Código, Foto, Descripción, Stock (clase roja si < 0), Mínimo (+ texto "Reponer" en rojo si `bajo_minimo`) y acciones Ingreso / Mínimo / Baja / Movimientos según permisos; `paginacion`. Modales (`modal`): Ingreso (cantidad entera ≥1, nota), Mínimo ("Mínimo de reposición", entero ≥0), Baja (cantidad, motivo como select de `GET /stock/motivos-baja?activo=true`, nota "Qué pasó"), Movimientos (tabla Fecha, Tipo (texto legible), Cantidad con signo, Stock resultante, Usuario, Nota; paginada; secuenciada con su propio `ultimaRespuesta` + chequeo de producto abierto). Después de cada escritura: toast, cerrar modal, recargar listado y resumen.
- [ ] **Step 4: `static/js/stock.js`** con `window.stockListado(...)` (patrón de `productos.js`; tipos legibles en un objeto `TIPOS_MOVIMIENTO`).
- [ ] **Step 5: Correr** — tests de páginas, `node --check`, suite.
- [ ] **Step 6: Commit** — `feat(stock): hub de gestión de stock y pantalla de stock`.

---

### Task 8: Pantalla de motivos de baja

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/motivos_baja/listado.html`, `backend/app/static/js/motivos_baja.js`
- Test: `backend/tests/test_paginas_stock.py` (agregar)

- [ ] **Step 1: Tests** — admin entra a `/motivos-baja` (`motivosBaja(`, js incluido); vendedor → 403.
- [ ] **Step 2: Ruta** `GET /motivos-baja` con `requiere_pagina(PAGINA_MOTIVOS_BAJA, actual="/gestion-de-stock")`, volver a `/stock`.
- [ ] **Step 3: Plantilla + JS**: filtro Nombre (debounce) y `switch_estado` (activos/inactivos), tabla Nombre + Estado + acciones Editar y Activar/Desactivar (con `confirmar` al desactivar), modal de alta/edición con `campo` Nombre (placeholder "Rotura"). Todo por `GET/POST/PUT /api/v1/stock/motivos-baja`.
- [ ] **Step 4: Correr** — tests, `node --check`, suite.
- [ ] **Step 5: Commit** — `feat(stock): pantalla de motivos de baja`.

---

### Task 9: Auditorías de stock (listado y pantalla de conteo)

**Files:**
- Modify: `backend/app/api/pages.py`
- Create: `backend/app/templates/pages/auditorias/listado.html`, `backend/app/templates/pages/auditorias/conteo.html`, `backend/app/static/js/auditorias.js`
- Test: `backend/tests/test_paginas_stock.py` (agregar)

**Interfaces:** rutas `GET /auditorias-inventario` y `GET /auditorias-inventario/{id}` (404 de página si no existe; contexto `puede_auditar`); componentes `auditoriasListado({ puedeAuditar })` y `auditoriaConteo({ id, puedeAuditar })`.

- [ ] **Step 1: Tests** — listado del vendedor con "Iniciar conteo"; conteo de una auditoría creada con el service en el test (incluye `auditoriaConteo(`); id inexistente → página 404.
- [ ] **Step 2: Rutas.**
- [ ] **Step 3: Listado**: botón "Iniciar conteo" (modal con categoría opcional y notas; deshabilitado con el aviso "Ya hay un conteo en curso" si existe uno en curso — dato de `GET /auditorias-inventario?estado=en_curso`); filtros Estado y rango de fechas (con botón "Buscar": tabla de alto volumen); tabla Iniciada, Usuario, Estado, Ítems y acciones Continuar/Ver, PDF (abre inline en ventana nueva, abierta sincrónica en el click como las etiquetas del 04), Excel (link de descarga); paginado.
- [ ] **Step 4: Conteo**: encabezado con número, estado y notas; si está en curso, línea "Escaneá o tipeá el código" + "Contadas" (entero ≥0, default 1) + "Agregar" (Enter en el código enfoca "Contadas"; Enter en "Contadas" registra vía `POST /{id}/items/por-codigo` y vuelve a enfocar el código); tabla Código | Descripción | Sistema | Contado (editable inline con guardado en blur/Enter, `PATCH`) | Dif. (en rojo si ≠ 0) | Quitar (`confirmar`); botón "Cerrar" con `confirmar({titulo: '¿Cerrar el conteo?', mensaje: 'Se ajusta el stock de los productos con diferencias.'})` → `PATCH /{id}/finalizar`; cerrada: solo lectura con PDF y Excel. Errores 409 (ajuste negativo) con toast.
- [ ] **Step 5: Correr** — tests, `node --check`, suite.
- [ ] **Step 6: Commit** — `feat(stock): pantallas de auditorías de stock`.

---

### Task 10: Pantallas de productos con stock

**Files:**
- Modify: `backend/app/templates/components/producto_form.html`, `backend/app/static/js/producto_form.js`, `backend/app/templates/pages/productos/listado.html`, `backend/app/templates/pages/productos/_modal_ficha.html`, `backend/app/static/js/productos.js`, `backend/app/api/pages.py`, `docs/pendientes.md`
- Test: `backend/tests/test_paginas_productos.py`, `backend/tests_js/producto_form.test.mjs`

- [ ] **Step 1: Tests** — la página `/productos` tiene "Stock 0" y "Stock inicial" (en el alta); JS: `stockEntero` sigue OK y el cuerpo del alta incluye `stock_inicial` entero (Math.trunc, ≥0) y el de la edición no.
- [ ] **Step 2: Formulario**: campo "Stock inicial" (solo alta, entero ≥0, `inputmode="numeric"`, oculto si "Stock infinito" está tildado) → `stock_inicial` en el POST.
- [ ] **Step 3: Listado**: columna Stock (texto rojo si < 0, resaltado "bajo mínimo" si `bajo_minimo`; "∞" si `stock_infinito`); toggle "Stock 0" (`filtros.stock_cero`) que agrega la columna de checkboxes (con "seleccionar todos los de la página") y el botón rojo "Desactivar seleccionados" (`confirmar` con la cantidad; `PATCH /{id}/estado` por cada uno, en serie; toast con cuántos se desactivaron y cuáles fallaron; recarga). La ficha muestra stock, mínimo y un link "Ver en Stock" (`/stock`).
- [ ] **Step 4: `docs/pendientes.md`** — borrar la sección "Módulo 04: pendientes para el 05" (ya resuelta).
- [ ] **Step 5: Verificación final**
```bash
docker compose exec -T backend pytest -p no:warnings
for f in app producto_form productos stock motivos_baja auditorias; do node --check backend/app/static/js/$f.js; done
node --test backend/tests_js/
```
Checklist manual (usuario): ingreso, mínimo y baja desde /stock; ver movimientos; motivos de baja; iniciar un conteo, escanear, cerrar y ver el stock ajustado; PDF y Excel del conteo; alta de producto con stock inicial; "Stock 0" y desactivación masiva.
- [ ] **Step 6: Commit** — `feat(productos): stock en el formulario, el listado y la ficha`.
