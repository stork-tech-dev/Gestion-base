# Módulo 06 — Clientes y Ventas: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clientes (con datos fiscales), medios de pago con planes de cuotas, motivos de descuento, promociones, la pantalla de venta de escritorio (carrito persistido como venta `en_curso`), la confirmación y anulación de ventas, y el hub de Ventas con el "Resumen de Ventas".

**Architecture:** Igual que 02-05: API REST (`/api/v1/clientes`, `/api/v1/configuracion`, `/api/v1/ventas`) con services sin commit, errores tipados y auditoría en la misma transacción; pantallas Jinja + un componente Alpine por pantalla. Toda la aritmética de dinero vive en `services/descuentos.py`, `services/medios_pago.py`, `services/promociones.py` y `services/ventas.py::_recalcular`; el JS nunca calcula totales: muestra lo que devuelve la API. El stock cambia solo vía `services.stock.aplicar_movimiento`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (SQL a mano), PostgreSQL 15, Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `modulos/06_ventas.md` + `CLAUDE.md` + `docs/pendientes.md` ("Patrones que 03-09 deben copiar"). Donde este plan y el spec difieran, manda la sección "Decisiones y desvíos" de este plan.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `modulo-06-ventas` (creada desde `dev` en la Task 1). UN commit por tarea: `feat(ventas): …` (o `feat(clientes): …`, `fix(…): …`) + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout de otra rama. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo:** verificar con tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests en el contenedor (`docker compose exec -T backend pytest -p no:warnings`, suite completa antes de cada commit). JS: `node --check` y `node --test backend/tests_js/`.
- Services: nunca `commit`; errores `DatoInvalido` 400 / `SinPermiso` 403 / `NoEncontrado` 404 / `ReglaDeNegocio` 409; auditoría con `registrar_auditoria` y `estado_anterior` tomado ANTES del cambio; **validar todo antes de modificar**; locks (`with_for_update()` + `populate_existing`) donde dos operaciones simultáneas puedan pisarse. Routers hacen `db.commit()`.
- Dinero: siempre `Decimal`, nunca `float`. Redondeos solo con `core/utils.py` (`redondear`, `redondear_hacia_abajo`). El redondeo del negocio sale de `obtener_configuracion(db).redondeo` (seed 1000) y el tope de `obtener_configuracion(db).tope_descuento_venta` (seed 50): nunca literales.
- Límites contra las columnas: montos en schemas `ge=0, le=99_999_999.99` (NUMERIC(10,2)); porcentajes `NUMERIC(5,2)`; nunca un 500 por datos del usuario.
- Filtros de texto con `filtro_texto`; búsqueda por código SIEMPRE con `productos.condiciones_codigo` / `productos.buscar_por_codigo` (definición única).
- Pantallas: `requiere_pagina(ITEM)`; valores a Alpine solo con `|js` en atributos; sin `x-html` con datos de la API sin escapar; escrituras con `pedir()`; cargas que se pueden pisar con su propio `ultimaRespuesta()`; `erroresDeCampos()` para 422; `confirmar()` antes de acciones destructivas; reusar macros de `templates/components/`; modales solo se cierran con la X; mobile-first, `min-h-toque`, tablas en `overflow-x-auto`.
- `costo_unitario` NUNCA sale en ninguna respuesta de `/api/v1/ventas` (solo lo usará Reportes).

## Decisiones y desvíos

Decisiones de producto tomadas con el usuario al inicio del módulo:

1. **Promociones por medio de pago:** una promo con alcance `medio_de_pago` rige solo si TODOS los pagos cargados son de medios alcanzados. Sin pagos cargados no bloquea. Los pagos se mandan al backend apenas se eligen (no solo al confirmar), así el total mostrado siempre lo calcula la API.
2. **Promo de tipo `porcentaje`:** se encadena sobre el precio con el descuento del producto: `aplicar_descuentos(precio_lista, descuento_producto, porcentaje_promo, redondeo)` (redondeo hacia abajo). No cuenta para el tope de descuento.
3. **Precio vivo:** cada `_recalcular` relee `precio_venta`, `descuento_producto` y `costo_en_pesos` del producto; se congelan al confirmar. Para que el cliente no pague algo distinto de lo que vio, `confirmar` recibe `total_esperado`: si tras recalcular el total cambió → 409 "Los precios cambiaron mientras cargabas la venta: revisá el total y volvé a confirmar." y la pantalla llama a `POST /ventas/{id}/recalcular`.
4. **Ventas abandonadas:** no se hace nada; quedan `en_curso` hasta que su dueño las retome o descarte.

Desvíos técnicos:

5. **Pagos parciales permitidos mientras la venta está en curso; la suma exacta se garantiza por construcción.** `registrar_pagos` reemplaza los pagos y `_recalcular` los normaliza: con 1 pago, su monto = lo cobrable; con 2, el segundo = cobrable − primero. Si el resto es ≤ 0 o un plan deja de valer para su monto: en `registrar_pagos` → 400 con el motivo; en los demás recálculos → se borran los pagos (el spec: "si los pagos cargados ya no cubren el total, los borra"). `confirmar` igual verifica `sum(monto) == cobrable` (defensa).
6. **Permiso de anular:** `VENTAS ver` + `venta.anular` (acción `eliminar`). El spec pedía `VENTAS eliminar`, pero el supervisor sembrado no lo tiene y no podría anular.
7. **Turno de caja (sesión 07):** `services/ventas.py::_turno_para_operar(db) -> int | None` devuelve `None` hoy (no bloquea) y es el ÚNICO punto que la sesión 07 reemplaza por `services.turnos.turno_para_operar()`. `turno_id` / `turno_anulacion_id` quedan NULL. El test "confirmar sin turno → 409" es de la sesión 07.
8. **Columnas extra en `ventas`:** `promocion_a_mano BOOLEAN NOT NULL DEFAULT FALSE` (para que "elegir otra promoción" dure hasta el próximo cambio del carrito) y el índice `uq_ventas_en_curso_usuario` (UNIQUE parcial en `usuario_id` WHERE `estado='en_curso'`): garantiza en la base "nunca dos en curso por usuario" aun con dos pestañas.
9. `todos_productos` y `todos_categorias` son equivalentes (`categoria_id` es NOT NULL): ambos devuelven `None` en `productos_alcanzados`.
10. **Ítems en promoción de grupo:** todas las unidades de un grupo completo quedan `en_promocion=True` (las pagas y las gratis); el sobrante no. Así ninguna unidad del grupo acepta descuento manual.
11. `GET /api/v1/ventas/vendedores` [VENTAS ver] → `[{id, nombre}]` de usuarios activos, para el combobox "Vendedor" del resumen (el Vendedor no tiene USUARIOS ver).
12. `POST /api/v1/ventas/{id}/recalcular` [VENTAS crear] (ver decisión 3).

---

## File Structure

```
backend/migrations/versions/0006_ventas.py                        (new) Task 1
backend/app/models/clientes.py, ventas.py, medios_pago.py,
    descuentos.py, promociones.py, __init__.py                    (new/mod) Task 1
backend/app/models/stock.py                                        (mod) Task 1  FK referencia_venta → ventas
backend/tests/fabricas.py                                          (new) Task 1  helpers de catálogo para tests
backend/tests/test_modelo_ventas.py                                (new) Task 1
backend/app/schemas/clientes.py, medios_pago.py, descuentos.py     (new) Task 2
backend/app/services/clientes.py, medios_pago.py, descuentos.py    (new) Task 2
backend/tests/test_clientes.py, test_medios_pago.py, test_descuentos.py  (new) Task 2
backend/app/schemas/promociones.py, services/promociones.py        (new) Task 3
backend/tests/test_promociones.py                                  (new) Task 3
backend/app/schemas/ventas.py, services/ventas.py                  (new) Task 4
backend/tests/test_ventas.py, test_anulacion.py                    (new) Task 4
backend/app/api/v1/clientes.py, configuracion.py, ventas.py, __init__.py  (new/mod) Task 5
backend/tests/test_clientes_api.py, test_configuracion_api.py, test_ventas_api.py  (new) Task 5
backend/app/api/pages.py                                           (mod) Tasks 6-8
backend/app/templates/pages/clientes/listado.html, static/js/clientes.js           (new) Task 6
backend/app/templates/components/cliente_form.html                 (new) Task 6  (lo reusa la venta)
backend/app/templates/pages/{medios_pago,motivos_descuento,promociones}/listado.html,
    static/js/{medios_pago,motivos_descuento,promociones}.js       (new) Task 6
backend/tests/test_paginas_ventas.py                               (new) Tasks 6-8
backend/app/templates/pages/ventas/{hub,nueva}.html, static/js/venta.js  (new) Task 7
backend/tests_js/venta.test.mjs                                    (new) Task 7
backend/app/templates/pages/ventas/listado.html, static/js/ventas.js     (new) Task 8
backend/tests_js/ventas.test.mjs                                   (new) Task 8
docs/pendientes.md                                                 (mod) Task 8
```

Revisión por tarea (proceso acordado): **Tasks 2, 3, 4 y 5** llevan revisor (dinero, stock, locks, permisos, auditoría). Tasks 1, 6, 7 y 8 no: las cubre la revisión final completa (Opus).

---

### Task 1: Migración 0006, modelos y fábricas de test

**Files:**
- Create: `backend/migrations/versions/0006_ventas.py`, `backend/app/models/{clientes,medios_pago,descuentos,promociones,ventas}.py`, `backend/tests/fabricas.py`, `backend/tests/test_modelo_ventas.py`
- Modify: `backend/app/models/__init__.py` (exportar todo lo nuevo), `backend/app/models/stock.py` (`referencia_venta_id` con `ForeignKey("ventas.id", ondelete="RESTRICT")`, borrar el comentario "La FK a ventas se agrega en la sesión 06")

**Interfaces:**
- Produces (enums `str, Enum`, mapeados con `enum_db(...)`):
  - `CondicionIva`: `CONSUMIDOR_FINAL="consumidor_final"`, `RESPONSABLE_INSCRIPTO="responsable_inscripto"`, `MONOTRIBUTISTA="monotributista"`, `EXENTO="exento"`.
  - `TipoPromocion`: `DOS_X_UNO="dos_x_uno"`, `TRES_X_DOS="tres_x_dos"`, `PORCENTAJE="porcentaje"`; constantes en `models/promociones.py`: `TAMANO_GRUPO = {DOS_X_UNO: 2, TRES_X_DOS: 3}`, `PAGAS_POR_GRUPO = {DOS_X_UNO: 1, TRES_X_DOS: 2}`.
  - `TipoAlcancePromocion`: `PRODUCTO`, `CATEGORIA`, `TODOS_PRODUCTOS`, `TODOS_CATEGORIAS`, `MEDIO_DE_PAGO` (valores en minúscula igual al nombre).
  - `EstadoVenta`: `EN_CURSO="en_curso"`, `CONFIRMADA="confirmada"`, `ANULADA="anulada"`.
- Modelos: `Cliente`, `MedioDePago` (relación `planes` ordenada por `(cuotas, recargo_cliente)`, `lazy="selectin"`), `PlanCuotas` (métodos `disponible_para(monto) -> bool` = `activo and monto_minimo <= monto`; propiedad `sin_interes` = `recargo_cliente == 0`), `MotivoDescuento` (relación `medios` → `list[MedioDePago]` vía `motivo_medios_pago`, `secondary`, `lazy="selectin"`), `Promocion` (relación `alcances` `lazy="selectin"`, método `vigente_el(dia: date) -> bool` = `activo and (fecha_inicio is None or fecha_inicio <= dia) and (fecha_fin is None or dia <= fecha_fin)`), `PromocionAlcance`, `ClientePromocion`, `Venta` (relaciones `cliente`, `usuario`, `anulada_por`, `promocion` joined; `items` ordenada por `orden` y `pagos` ordenada por `id`, ambas `lazy="selectin"`, `cascade="all, delete-orphan"`, `passive_deletes=True`), `VentaItem` (relaciones `producto` y `motivo_descuento` joined), `VentaPago` (relaciones `medio_de_pago` y `plan_cuotas` joined).
- `tests/fabricas.py::catalogo(db, admin) -> dict` con claves `categoria`, `subcategoria`, `proveedor` (ARS) y `alta(descripcion, costo="1000", **extra) -> Producto` (margen 0, así con redondeo 1000 el `precio_venta` = costo redondeado hacia arriba a 1000). Lo usan los tests de las Tasks 2-5.

- [ ] **Step 0: Rama**

```bash
git checkout dev && git checkout -b modulo-06-ventas
```

- [ ] **Step 1: Tests que fallan** — `backend/tests/test_modelo_ventas.py`. Cubrir, cada uno con `pytest.raises(IntegrityError)` + `db.rollback()` si corresponde (mirar `tests/test_modelo_stock.py` para el patrón de savepoint que ya se usa):

```python
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    Cliente, CondicionIva, EstadoVenta, MedioDePago, PlanCuotas, Venta, VentaItem, VentaPago,
)
from tests.fabricas import catalogo


def test_seed_medios_de_pago(db):
    nombres = set(db.scalars(select(MedioDePago.nombre)))
    assert {"Efectivo", "Débito", "Tarjeta de Crédito", "Transferencia"} <= nombres
    efectivo = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    assert efectivo.nombre == "Efectivo" and efectivo.soporta_cuotas is False
    credito = db.scalar(select(MedioDePago).where(MedioDePago.nombre == "Tarjeta de Crédito"))
    assert credito.soporta_cuotas is True


def test_un_solo_medio_efectivo(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(MedioDePago(nombre="Otro efectivo", es_efectivo=True))
            db.flush()


def test_efectivo_no_admite_cuotas(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE medios_de_pago SET soporta_cuotas = TRUE WHERE es_efectivo"))


def test_cliente_no_consumidor_final_exige_cuit(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Cliente(nombre="Sin CUIT", condicion_iva=CondicionIva.RESPONSABLE_INSCRIPTO))
            db.flush()


def test_plan_disponible_para_y_sin_interes(db):
    plan = PlanCuotas(cuotas=3, recargo_cliente=Decimal("0"), costo_medio=Decimal("5"),
                      monto_minimo=Decimal("10000"), activo=True)
    assert plan.sin_interes is True
    assert plan.disponible_para(Decimal("10000")) is True
    assert plan.disponible_para(Decimal("9999.99")) is False


def test_venta_en_curso_unica_por_usuario(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    db.add(Venta(numero="V-900001", usuario_id=vendedor.id))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Venta(numero="V-900002", usuario_id=vendedor.id))
            db.flush()


def test_check_estado_confirmada_exige_codigo(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Venta(numero="V-900003", usuario_id=vendedor.id, estado=EstadoVenta.CONFIRMADA))
            db.flush()


def test_item_en_promocion_no_lleva_descuento(db, crear_usuario):
    admin = crear_usuario("admin")
    producto = catalogo(db, admin)["alta"]("Remera modelo")
    venta = Venta(numero="V-900004", usuario_id=admin.id)
    db.add(venta)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(VentaItem(venta_id=venta.id, producto_id=producto.id, precio_unitario=1000, precio_lista=1000,
                             costo_unitario=500, descuento_item=10, precio_final=900, en_promocion=True, orden=1))
            db.flush()


def test_pago_monto_total_es_monto_mas_recargo(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    venta = Venta(numero="V-900005", usuario_id=vendedor.id)
    db.add(venta)
    db.flush()
    medio = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(VentaPago(venta_id=venta.id, medio_de_pago_id=medio.id, monto=100, recargo=10, monto_total=100))
            db.flush()


def test_fk_movimiento_a_venta(db):
    fk = db.scalar(text("SELECT 1 FROM pg_constraint WHERE conname = 'fk_movimientos_stock_referencia_venta'"))
    assert fk == 1
```

- [ ] **Step 2: Correr y ver que fallan** — `docker compose exec -T backend pytest tests/test_modelo_ventas.py -p no:warnings` → FAIL (ImportError).

- [ ] **Step 3: Migración** — `backend/migrations/versions/0006_ventas.py` (`revision = "0006"`, `down_revision = "0005"`), SQL a mano como la 0005. Contenido completo del `upgrade()`:

```sql
CREATE SEQUENCE ventas_numero_seq START 1;
CREATE TYPE condicion_iva AS ENUM ('consumidor_final', 'responsable_inscripto', 'monotributista', 'exento');
CREATE TYPE tipo_promocion AS ENUM ('dos_x_uno', 'tres_x_dos', 'porcentaje');
CREATE TYPE tipo_alcance_promocion AS ENUM ('producto', 'categoria', 'todos_productos', 'todos_categorias', 'medio_de_pago');
CREATE TYPE estado_venta AS ENUM ('en_curso', 'confirmada', 'anulada');

-- cuit y condicion_iva no se usan hoy en ningún cálculo: quedan cargados
-- para la futura facturación electrónica.
CREATE TABLE clientes (
    id            BIGSERIAL PRIMARY KEY,
    nombre        VARCHAR(150) NOT NULL,          -- nombre o razón social
    dni           VARCHAR(15) UNIQUE,             -- solo dígitos
    cuit          VARCHAR(11) UNIQUE,             -- solo dígitos, verificador válido (lo valida el service)
    condicion_iva condicion_iva NOT NULL DEFAULT 'consumidor_final',
    domicilio     VARCHAR(200),
    codigo_postal VARCHAR(10),
    localidad     VARCHAR(100),
    telefono      VARCHAR(30),
    email         VARCHAR(150),
    activo        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_clientes_cuit_fuera_de_cf CHECK (condicion_iva = 'consumidor_final' OR cuit IS NOT NULL)
);

CREATE TABLE medios_de_pago (
    id             BIGSERIAL PRIMARY KEY,
    nombre         VARCHAR(60) NOT NULL UNIQUE,
    soporta_cuotas BOOLEAN NOT NULL DEFAULT FALSE,
    es_efectivo    BOOLEAN NOT NULL DEFAULT FALSE,   -- el arqueo lo busca por esta marca, nunca por nombre
    activo         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP NOT NULL DEFAULT now(),
    updated_at     TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_medios_de_pago_efectivo_sin_cuotas CHECK (NOT (es_efectivo AND soporta_cuotas))
);
CREATE UNIQUE INDEX uq_medios_de_pago_efectivo ON medios_de_pago ((true)) WHERE es_efectivo;

CREATE TABLE planes_cuotas (
    id               BIGSERIAL PRIMARY KEY,
    medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
    cuotas           SMALLINT NOT NULL,
    recargo_cliente  NUMERIC(5,2) NOT NULL DEFAULT 0,   -- % que paga el cliente (0 = sin interés)
    costo_medio      NUMERIC(5,2) NOT NULL DEFAULT 0,   -- % que cobra la terminal: SOLO reportes
    monto_minimo     NUMERIC(10,2) NOT NULL DEFAULT 0,
    activo           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_planes_cuotas_cuotas CHECK (cuotas >= 1),
    CONSTRAINT ck_planes_cuotas_recargo CHECK (recargo_cliente BETWEEN 0 AND 100),
    CONSTRAINT ck_planes_cuotas_costo CHECK (costo_medio BETWEEN 0 AND 100),
    CONSTRAINT ck_planes_cuotas_minimo CHECK (monto_minimo >= 0),
    CONSTRAINT uq_planes_cuotas UNIQUE (medio_de_pago_id, cuotas, recargo_cliente)
);

CREATE TABLE motivos_descuento (
    id                          BIGSERIAL PRIMARY KEY,
    nombre                      VARCHAR(100) NOT NULL UNIQUE,
    nota                        VARCHAR(500),
    porcentaje_sugerido         NUMERIC(5,2),   -- NULL = quien vende elige
    habilita_cuotas_sin_interes BOOLEAN NOT NULL DEFAULT FALSE,
    activo                      BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_inicio                DATE,
    fecha_fin                   DATE,
    created_at                  TIMESTAMP NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_motivos_descuento_sugerido CHECK (porcentaje_sugerido IS NULL OR (porcentaje_sugerido > 0 AND porcentaje_sugerido <= 100)),
    CONSTRAINT ck_motivos_descuento_fechas CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_inicio <= fecha_fin)
);
CREATE TABLE motivo_medios_pago (   -- vacío = todos los medios
    id               BIGSERIAL PRIMARY KEY,
    motivo_id        BIGINT NOT NULL REFERENCES motivos_descuento (id) ON DELETE CASCADE,
    medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
    CONSTRAINT uq_motivo_medios_pago UNIQUE (motivo_id, medio_de_pago_id)
);

CREATE TABLE promociones (
    id                   BIGSERIAL PRIMARY KEY,
    nombre               VARCHAR(100) NOT NULL UNIQUE,
    nota                 VARCHAR(500),
    tipo                 tipo_promocion NOT NULL,
    activo               BOOLEAN NOT NULL DEFAULT TRUE,
    porcentaje_descuento INTEGER,
    fecha_inicio         DATE,
    fecha_fin            DATE,
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    updated_at           TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_promociones_porcentaje CHECK (porcentaje_descuento IS NULL OR porcentaje_descuento BETWEEN 1 AND 75),
    CONSTRAINT ck_promociones_porcentaje_tipo CHECK ((tipo = 'porcentaje') = (porcentaje_descuento IS NOT NULL)),
    CONSTRAINT ck_promociones_fechas CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_inicio <= fecha_fin)
);
-- referencia_id no es FK: apunta a productos, categorías o medios según tipo_alcance
-- (0 = "todos"). El service valida que exista.
CREATE TABLE promocion_alcance (
    id            BIGSERIAL PRIMARY KEY,
    promocion_id  BIGINT NOT NULL REFERENCES promociones (id) ON DELETE CASCADE,
    tipo_alcance  tipo_alcance_promocion NOT NULL,
    referencia_id BIGINT NOT NULL,
    CONSTRAINT uq_promocion_alcance UNIQUE (promocion_id, tipo_alcance, referencia_id)
);
CREATE TABLE cliente_promociones (   -- promociones exclusivas de ciertos clientes
    id           BIGSERIAL PRIMARY KEY,
    cliente_id   BIGINT NOT NULL REFERENCES clientes (id) ON DELETE RESTRICT,
    promocion_id BIGINT NOT NULL REFERENCES promociones (id) ON DELETE CASCADE,
    CONSTRAINT uq_cliente_promociones UNIQUE (cliente_id, promocion_id)
);
CREATE INDEX ix_cliente_promociones_promocion_id ON cliente_promociones (promocion_id);

-- Importes desnormalizados a propósito: son la foto del cierre; se recalculan
-- mientras está en_curso y se congelan al confirmar.
-- turno_id / turno_anulacion_id: la FK a turnos se agrega en la sesión 07.
CREATE TABLE ventas (
    id                 BIGSERIAL PRIMARY KEY,
    numero             VARCHAR(12) NOT NULL UNIQUE,
    cliente_id         BIGINT REFERENCES clientes (id) ON DELETE RESTRICT,
    usuario_id         BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
    estado             estado_venta NOT NULL DEFAULT 'en_curso',
    subtotal           NUMERIC(10,2) NOT NULL DEFAULT 0,
    descuento_total    NUMERIC(10,2) NOT NULL DEFAULT 0,
    recargo_total      NUMERIC(10,2) NOT NULL DEFAULT 0,
    total              NUMERIC(10,2) NOT NULL DEFAULT 0,
    codigo_cambio      VARCHAR(8) UNIQUE,
    promocion_id       BIGINT REFERENCES promociones (id) ON DELETE RESTRICT,
    promocion_a_mano   BOOLEAN NOT NULL DEFAULT FALSE,   -- la eligió quien vende: dura hasta el próximo cambio del carrito
    confirmada_en      TIMESTAMP,
    turno_id           BIGINT,
    anulada_en         TIMESTAMP,
    anulada_por_id     BIGINT REFERENCES usuarios (id) ON DELETE RESTRICT,
    motivo_anulacion   VARCHAR(500),
    turno_anulacion_id BIGINT,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    updated_at         TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_ventas_importes CHECK (subtotal >= 0 AND descuento_total >= 0 AND recargo_total >= 0 AND total >= 0),
    CONSTRAINT ck_ventas_estado CHECK (
        (estado = 'en_curso'   AND codigo_cambio IS NULL AND confirmada_en IS NULL AND anulada_en IS NULL) OR
        (estado = 'confirmada' AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL AND anulada_en IS NULL) OR
        (estado = 'anulada'    AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL
                               AND anulada_en IS NOT NULL AND anulada_por_id IS NOT NULL
                               AND motivo_anulacion IS NOT NULL))
);
CREATE INDEX ix_ventas_cliente_id ON ventas (cliente_id);
CREATE INDEX ix_ventas_usuario_id ON ventas (usuario_id);
CREATE INDEX ix_ventas_estado ON ventas (estado);
CREATE INDEX ix_ventas_confirmada_en ON ventas (confirmada_en);
CREATE INDEX ix_ventas_turno_id ON ventas (turno_id);
CREATE INDEX ix_ventas_turno_anulacion_id ON ventas (turno_anulacion_id);
-- Nunca dos ventas en curso del mismo usuario (aun con dos pestañas).
CREATE UNIQUE INDEX uq_ventas_en_curso_usuario ON ventas (usuario_id) WHERE estado = 'en_curso';

-- Una fila por UNIDAD. precio_lista, precio_unitario y costo_unitario son la
-- foto del momento de la venta (precio, costo y dólar cambian).
CREATE TABLE venta_items (
    id                    BIGSERIAL PRIMARY KEY,
    venta_id              BIGINT NOT NULL REFERENCES ventas (id) ON DELETE CASCADE,
    producto_id           BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
    precio_unitario       NUMERIC(10,2) NOT NULL,
    precio_lista          NUMERIC(10,2) NOT NULL,
    costo_unitario        NUMERIC(12,2) NOT NULL,
    descuento_item        NUMERIC(5,2) NOT NULL DEFAULT 0,
    motivo_descuento_id   BIGINT REFERENCES motivos_descuento (id) ON DELETE RESTRICT,
    porcentaje_modificado BOOLEAN NOT NULL DEFAULT FALSE,
    precio_final          NUMERIC(10,2) NOT NULL,
    en_promocion          BOOLEAN NOT NULL DEFAULT FALSE,
    orden                 SMALLINT NOT NULL,
    CONSTRAINT ck_venta_items_importes CHECK (precio_unitario >= 0 AND precio_lista >= 0 AND costo_unitario >= 0 AND precio_final >= 0),
    CONSTRAINT ck_venta_items_descuento CHECK (descuento_item BETWEEN 0 AND 100),
    CONSTRAINT ck_venta_items_motivo CHECK (descuento_item = 0 OR motivo_descuento_id IS NOT NULL),
    CONSTRAINT ck_venta_items_promo_sin_descuento CHECK (NOT (en_promocion AND descuento_item > 0))
);
CREATE INDEX ix_venta_items_venta_id ON venta_items (venta_id);
CREATE INDEX ix_venta_items_producto_id ON venta_items (producto_id);

CREATE TABLE venta_pagos (
    id               BIGSERIAL PRIMARY KEY,
    venta_id         BIGINT NOT NULL REFERENCES ventas (id) ON DELETE CASCADE,
    medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
    plan_cuotas_id   BIGINT REFERENCES planes_cuotas (id) ON DELETE RESTRICT,
    monto            NUMERIC(10,2) NOT NULL,   -- antes del recargo
    recargo          NUMERIC(10,2) NOT NULL DEFAULT 0,
    monto_total      NUMERIC(10,2) NOT NULL,
    CONSTRAINT ck_venta_pagos_monto CHECK (monto > 0 AND recargo >= 0),
    CONSTRAINT ck_venta_pagos_total CHECK (monto_total = monto + recargo)
);
CREATE INDEX ix_venta_pagos_venta_id ON venta_pagos (venta_id);

ALTER TABLE movimientos_stock
    ADD CONSTRAINT fk_movimientos_stock_referencia_venta
    FOREIGN KEY (referencia_venta_id) REFERENCES ventas (id) ON DELETE RESTRICT;
CREATE INDEX ix_movimientos_stock_referencia_venta_id ON movimientos_stock (referencia_venta_id);

INSERT INTO medios_de_pago (nombre, es_efectivo, soporta_cuotas) VALUES
    ('Efectivo', TRUE, FALSE), ('Débito', FALSE, FALSE),
    ('Tarjeta de Crédito', FALSE, TRUE), ('Transferencia', FALSE, FALSE)
ON CONFLICT (nombre) DO NOTHING;
```

`downgrade()`: DROP en orden inverso (FK de movimientos, tablas, tipos, sequence). Los permisos del supervisor (`configuracion.promociones`, `venta.anular`) **ya están en `migrations/seed.sql`**: no repetirlos. Revisar si `seed.sql` o `tests/conftest.py::_recrear_base` necesitan algo para las tablas nuevas (los tests crean la base con las migraciones; verificar con `test_seed.py`).

- [ ] **Step 4: Modelos** — un archivo por agregado (`clientes.py`: `CondicionIva`, `Cliente`, `ClientePromocion`; `medios_pago.py`: `MedioDePago`, `PlanCuotas`; `descuentos.py`: `MotivoDescuento` + tabla `motivo_medios_pago` como `Table` para el `secondary`; `promociones.py`: enums, constantes, `Promocion`, `PromocionAlcance`; `ventas.py`: `EstadoVenta`, `Venta`, `VentaItem`, `VentaPago`). Cada desnormalización lleva el mismo comentario que el SQL. `referencia_id` de `PromocionAlcance` comentado ("no es FK a propósito: el destino depende de tipo_alcance"). `Venta.cobrable` como propiedad Python = `total - recargo_total`. `updated_at` con `onupdate=func.now()` como en `stock.py`.

- [ ] **Step 5: `tests/fabricas.py`**

```python
"""Fábricas de datos para tests (catálogo mínimo de productos). Solo tests:
nunca se usan contra la base de desarrollo."""
import itertools

from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

_numeros = itertools.count(1)


def catalogo(db, admin) -> dict:
    n = next(_numeros)
    categoria = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre=f"Ropa fab {n}"), None)
    subcategoria = servicio_categorias.crear_categoria(
        db, admin, CategoriaCrear(nombre=f"Remeras fab {n}", parent_id=categoria.id), None)
    proveedor = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre=f"Prov fab {n}", moneda="ars"), None)

    def alta(descripcion, costo="1000", categoria_id=None, **extra):
        datos = {"categoria_id": categoria_id or subcategoria.id, "proveedor_id": proveedor.id,
                 "costo": costo, "margen": "0", "descripcion": descripcion}
        datos.update(extra)
        return servicio_productos.crear_producto(db, admin, ProductoCrear(**datos), None)

    return {"categoria": categoria, "subcategoria": subcategoria, "proveedor": proveedor, "alta": alta}
```

(Si `ProductoCrear` exige `stock_inicial` u otros campos, ajustarlo leyendo `app/schemas/productos.py`; para cargar stock usar `services.stock.registrar_ingreso`.)

- [ ] **Step 6: Correr** `pytest tests/test_modelo_ventas.py` → PASS; luego la suite completa → PASS.

- [ ] **Step 7: Commit** — `feat(ventas): migración 0006 y modelos de clientes, medios de pago, descuentos, promociones y ventas`.

---

### Task 2: Services de clientes, medios de pago y descuentos ★ (con revisor)

**Files:**
- Create: `backend/app/schemas/{clientes,medios_pago,descuentos}.py`, `backend/app/services/{clientes,medios_pago,descuentos}.py`, `backend/tests/{test_clientes,test_medios_pago,test_descuentos}.py`

**Interfaces:**
- Consumes: modelos de la Task 1; `core/codigos.py::cuit_es_valido(cuit) -> bool`; `core/utils.py::{redondear, redondear_hacia_abajo, normalizar_texto, filtro_texto, sin_tildes, sin_tildes_sql, paginar, ahora_db}`; `services/configuracion.py::obtener_configuracion`.
- Produces:
  - `services/clientes.py`: `obtener_cliente(db, cliente_id) -> Cliente` (404 "Cliente no encontrado"); `listar_clientes(db, *, busqueda=None, localidad=None, condicion_iva=None, activo=None, pagina=1, tamano=10) -> tuple[list[Cliente], int]`; `buscar(db, texto, limite=10) -> list[Cliente]`; `crear_cliente(db, autor, datos, ip) -> Cliente`; `editar_cliente(db, autor, cliente, datos, ip) -> Cliente`; `cambiar_estado(db, autor, cliente, activo, ip) -> Cliente`; `ficha(db, cliente_id) -> dict` con claves `cliente`, `promociones` (list[Promocion]), `compras_cantidad` (int), `compras_total` (Decimal). `solo_digitos(texto) -> str | None` (definición única; `None` si queda vacío).
  - `services/medios_pago.py`: `obtener_medio`, `listar_medios(db, *, nombre=None, soporta_cuotas=None, activo=None) -> list[MedioDePago]`, `crear_medio`, `editar_medio`, `cambiar_estado_medio`, `medio_efectivo(db) -> MedioDePago`, `obtener_plan`, `listar_planes(db, medio_id) -> list[PlanCuotas]`, `crear_plan(db, autor, medio, datos, ip)`, `editar_plan`, `cambiar_estado_plan`, `planes_disponibles(medio: MedioDePago, monto: Decimal, habilita_sin_interes: bool) -> list[PlanCuotas]`, `calcular_recargo(monto: Decimal, plan: PlanCuotas | None) -> Decimal`.
  - `services/descuentos.py`: `porcentajes_validos(db) -> list[int]`, `tope(db) -> Decimal`, `validar_porcentaje(db, p) -> Decimal`, `validar_tope(db, desc_producto, desc_venta, descripcion) -> None`, `calcular_descuento_total(desc_producto, desc_venta) -> Decimal`, `aplicar_descuentos(precio_lista, desc_producto, desc_venta, redondeo) -> Decimal`, `resolver_porcentaje(db, motivo_id, porcentaje) -> tuple[MotivoDescuento, Decimal, bool]`, `obtener_motivo`, `listar_motivos(db, *, nombre=None, habilita_cuotas_sin_interes=None, activo=None)`, `crear_motivo`, `editar_motivo`, `cambiar_estado_motivo`.

**Reglas (todas con test):**

Clientes:
- `nombre` obligatorio (`normalizar_texto`, ≤150). `dni` y `cuit` pasan por `solo_digitos`; vacío → `None`. DNI: 7 u 8 dígitos (400 "El DNI debe tener 7 u 8 dígitos"). CUIT: 11 dígitos y `cuit_es_valido` (400 "El CUIT no es válido: revisá el dígito verificador"). Si `condicion_iva != CONSUMIDOR_FINAL` y no hay CUIT → 400 "El CUIT es obligatorio si no es consumidor final".
- Únicos: DNI → 409 `f"El DNI {dni} ya está cargado en el cliente '{otro.nombre}'"`; igual con CUIT. Excluir el propio id al editar.
- `email` opcional, validado por Pydantic (`EmailStr` si `email-validator` está instalado; si no, patrón simple `^[^@\s]+@[^@\s]+\.[^@\s]+$`). Resto de campos `normalizar_texto` con sus largos.
- `listar_clientes`: `busqueda` = OR de `filtro_texto(nombre)`, `dni LIKE solo_digitos+'%'`, `cuit LIKE solo_digitos+'%'` (las dos últimas solo si hay dígitos); `localidad` con `filtro_texto`; orden `lower(nombre), id`.
- `buscar`: solo activos, mismo OR, `limite` 1..20.
- `ficha`: compras = ventas `CONFIRMADA` del cliente (no anuladas): `count` y `coalesce(sum(total), 0)`.
- Auditoría `cliente.crear` / `cliente.editar` (con `estado_anterior`) / `cliente.activar` / `cliente.desactivar`.

Medios de pago y planes:
- Nombre único sin importar mayúsculas y tildes (mismo patrón que `bajas_stock._nombre_libre`). `es_efectivo` y `soporta_cuotas` a la vez → 400 "El efectivo no se cobra en cuotas". Un segundo `es_efectivo` → 409 "Ya hay un medio marcado como efectivo: '…'". Desactivar el efectivo → 409 "El efectivo no se puede desactivar: lo usa la caja". Pasar `soporta_cuotas` a False con planes activos → 409 "Desactivá primero sus planes de cuotas".
- Planes: solo en medios con `soporta_cuotas` (409 "Este medio no se cobra en cuotas"); `cuotas` 1..60, `recargo_cliente` y `costo_medio` 0..100, `monto_minimo` ≥ 0 (en schema); duplicado (medio, cuotas, recargo) → 409 "Ya existe un plan de N cuotas con X% de recargo".
- `planes_disponibles(medio, monto, habilita)`: si `not medio.soporta_cuotas` → `[]`; si no, `[p for p in medio.planes if p.activo and (p.disponible_para(monto) or (habilita and p.sin_interes))]`.
- `calcular_recargo(monto, plan)`: `Decimal("0")` si `plan is None`; si no `redondear(monto * plan.recargo_cliente / 100)`. `costo_medio` NUNCA se usa (comentario explícito).
- Auditoría `medio_de_pago.crear/editar/activar/desactivar` y `plan_cuotas.crear/editar/activar/desactivar`.

Descuentos:

```python
PASO_PORCENTAJE = 5


def tope(db) -> Decimal:
    """Tope de descuento por producto (producto + venta, suma directa). ÚNICA lectura."""
    return obtener_configuracion(db).tope_descuento_venta


def porcentajes_validos(db) -> list[int]:
    return list(range(PASO_PORCENTAJE, int(tope(db)) + 1, PASO_PORCENTAJE))


def validar_porcentaje(db, porcentaje) -> Decimal:
    valor = Decimal(str(porcentaje))
    if valor != valor.to_integral_value() or int(valor) not in porcentajes_validos(db):
        raise DatoInvalido(f"El descuento tiene que ser de 5 en 5, hasta el {int(tope(db))}%")
    return valor


def validar_tope(db, desc_producto: Decimal, desc_venta: Decimal, descripcion: str) -> None:
    limite = tope(db)
    if desc_producto + desc_venta > limite:
        raise DatoInvalido(f"El descuento total no puede superar el {int(limite)}% por producto: "
                           f"'{descripcion}' ya tiene {desc_producto}% de descuento propio")


def calcular_descuento_total(desc_producto: Decimal, desc_venta: Decimal) -> Decimal:
    """Descuento efectivo encadenado, para mostrar: 1 − (1−dp)(1−dv), en %."""
    factor = (1 - desc_producto / 100) * (1 - desc_venta / 100)
    return redondear((1 - factor) * 100)


def aplicar_descuentos(precio_lista: Decimal, desc_producto: Decimal, desc_venta: Decimal,
                       redondeo: Decimal) -> Decimal:
    """ÚNICA fórmula de precio con descuentos: encadenados y redondeados HACIA
    ABAJO al múltiplo de redondeo. Nunca 0: si el redondeo lo haría 0, queda
    el bruto a centavos (y como mínimo $0,01)."""
    bruto = precio_lista * (1 - desc_producto / 100) * (1 - desc_venta / 100)
    final = redondear_hacia_abajo(bruto, redondeo)
    if final <= 0:
        final = max(redondear(bruto), Decimal("0.01"))
    return final
```

- `resolver_porcentaje(db, motivo_id, porcentaje)`: motivo existente y activo (409 "El motivo '…' está inactivo"); si `porcentaje is None`: usa `porcentaje_sugerido` o 400 "Elegí el porcentaje de descuento"; valida con `validar_porcentaje`; `modificado = motivo.porcentaje_sugerido is not None and valor != motivo.porcentaje_sugerido`. Devuelve `(motivo, valor, modificado)`. **No** valida vigencia ni medios (spec: se guardan y muestran, no se validan hoy; comentarlo).
- Motivos CRUD: nombre único (mismo patrón), `porcentaje_sugerido` validado con `validar_porcentaje` si viene, fechas coherentes (400), `medio_de_pago_ids: list[int]` sin repetidos y existentes (404) sincronizados con `_sincronizar_medios(motivo, medios)`. Auditoría `motivo_descuento.crear/editar/activar/desactivar` con `medio_de_pago_ids` en el snapshot.

**Tests mínimos** (`test_descuentos.py`, con `redondeo=Decimal("1000")` explícito salvo donde se lee de la config):

```python
def test_aplicar_descuentos_encadenado_y_hacia_abajo():
    # 10000 × 0.9 × 0.85 = 7650 → múltiplo de 1000 hacia abajo = 7000
    assert aplicar_descuentos(Decimal("10000"), Decimal("10"), Decimal("15"), Decimal("1000")) == Decimal("7000")


def test_aplicar_descuentos_nunca_cero():
    assert aplicar_descuentos(Decimal("1000"), Decimal("0"), Decimal("50"), Decimal("1000")) == Decimal("500.00")


def test_tope_leido_de_configuracion(db):
    config = obtener_configuracion(db)
    config.tope_descuento_venta = Decimal("20")
    db.flush()
    assert porcentajes_validos(db) == [5, 10, 15, 20]
    with pytest.raises(DatoInvalido):
        validar_porcentaje(db, 25)


def test_tope_suma_directa(db):
    with pytest.raises(DatoInvalido, match="no puede superar el 50%"):
        validar_tope(db, Decimal("30"), Decimal("25"), "Remera")
    validar_tope(db, Decimal("30"), Decimal("20"), "Remera")   # 50 justo: OK


def test_porcentaje_no_multiplo_de_5(db):
    with pytest.raises(DatoInvalido):
        validar_porcentaje(db, 12)


def test_resolver_porcentaje_usa_sugerido_y_marca_modificado(db, crear_usuario): ...
def test_resolver_sin_sugerido_exige_porcentaje(db, crear_usuario): ...
def test_motivo_inactivo_409(db, crear_usuario): ...
def test_motivo_sincroniza_medios_y_audita(db, crear_usuario): ...
```

`test_clientes.py`: CUIT con verificador inválido → 400 (usar `20390591581` como válido y `20390591582` como inválido; confirmar con `cuit_es_valido`); CUIT obligatorio fuera de consumidor final; DNI/CUIT únicos con el mensaje que nombra al otro cliente; limpieza a dígitos (`"20-39059158-1"` → `"20390591581"`); `buscar` por nombre sin tildes, por prefijo de DNI y de CUIT, excluye inactivos; `ficha` cuenta solo confirmadas (crear las ventas a mano con el modelo, estado CONFIRMADA + código + fecha); auditorías.

`test_medios_pago.py`: un solo efectivo (409); efectivo sin cuotas (400); efectivo no se desactiva; plan en medio sin cuotas (409); plan duplicado (409); `planes_disponibles` con mínimo y con `habilita_sin_interes` (entra el sin interés bajo el mínimo, NO el con interés); `calcular_recargo(Decimal("10000"), plan_15%) == Decimal("1500.00")`; `medio_efectivo`.

- [ ] Step 1: tests que fallan → Step 2: FAIL → Step 3: schemas + services → Step 4: PASS + suite completa → Step 5: commit `feat(ventas): services de clientes, medios de pago y descuentos`.

---

### Task 3: Service de promociones ★ (con revisor)

**Files:**
- Create: `backend/app/schemas/promociones.py`, `backend/app/services/promociones.py`, `backend/tests/test_promociones.py`

**Interfaces:**
- Consumes: `Promocion`, `PromocionAlcance`, `ClientePromocion`, `TAMANO_GRUPO`, `PAGAS_POR_GRUPO` (Task 1); `services/categorias.py::rama_de_ids(db, categoria_id) -> list[int]`; `services/descuentos.py::aplicar_descuentos`.
- Produces:
  - `unidades_gratis(cantidad: int, promo: Promocion) -> int` = `(cantidad // TAMANO_GRUPO[tipo]) * (TAMANO_GRUPO[tipo] - PAGAS_POR_GRUPO[tipo])`.
  - `elegir_unidades_gratis(items: list, promo) -> tuple[set[int], set[int]]` → `(ids_en_grupo, ids_gratis)`; `items` son objetos con `id`, `precio_unitario`, `orden`.
  - `productos_alcanzados(db, promo) -> set[int] | None`.
  - `aplica_con_medios(promo, medio_ids: set[int]) -> bool`.
  - `promociones_aplicables(db, cliente_id: int | None, dia: date, medio_ids: set[int]) -> list[Promocion]`.
  - `simular(db, promo, items, redondeo) -> tuple[Decimal, dict[int, Decimal], set[int]]` → `(ahorro, precio_final_por_item_id, ids_en_promocion)`; `items` = los elegibles (sin descuento manual) con `id`, `producto_id`, `precio_lista`, `precio_unitario`, `orden`, y `descuento_producto` (Decimal) disponible vía `item.producto.descuento_producto`.
  - `mejor_promocion(db, candidatas, items, redondeo) -> Promocion | None` (mayor ahorro; empate → menor id; `None` si ninguna ahorra > 0).
  - CRUD: `obtener_promocion`, `listar_promociones(db, *, nombre=None, tipo=None, rige_hoy=None, activo=None)`, `crear_promocion`, `editar_promocion`, `cambiar_estado_promocion`, `catalogos(db) -> dict` (productos activos `{id, codigo, descripcion}`, categorías `{id, camino}` usando `categorias.caminos`, medios activos `{id, nombre}`), `asignar_a_cliente(db, autor, cliente, promocion_id, ip)`, `quitar_de_cliente(db, autor, cliente, promocion_id, ip)`, `promociones_de_cliente(db, cliente_id) -> list[Promocion]`.

**Algoritmos:**

```python
def elegir_unidades_gratis(items, promo) -> tuple[set[int], set[int]]:
    """Grupos completos por precio DESC (orden de carga como desempate); en
    cada grupo quedan gratis las más baratas DEL GRUPO.
    Ej. 2x1 con [100, 90, 80, 70, 60] → grupos [100,90] [80,70] → gratis 90 y 70."""
    tamano = TAMANO_GRUPO[promo.tipo]
    gratis_por_grupo = tamano - PAGAS_POR_GRUPO[promo.tipo]
    ordenados = sorted(items, key=lambda i: (-i.precio_unitario, i.orden))
    completos = len(ordenados) // tamano * tamano
    en_grupo, gratis = set(), set()
    for inicio in range(0, completos, tamano):
        grupo = ordenados[inicio:inicio + tamano]
        en_grupo.update(i.id for i in grupo)
        gratis.update(i.id for i in grupo[-gratis_por_grupo:])
    return en_grupo, gratis


def aplica_con_medios(promo, medio_ids: set[int]) -> bool:
    """Decisión de producto: rige solo si TODOS los pagos son de medios
    alcanzados. Sin pagos cargados (medio_ids vacío) no bloquea. Sin alcance de
    medio, o con referencia 0, rige con cualquiera."""
    medios = {a.referencia_id for a in promo.alcances if a.tipo_alcance is TipoAlcancePromocion.MEDIO_DE_PAGO}
    if not medios or 0 in medios or not medio_ids:
        return True
    return medio_ids <= medios


def simular(db, promo, items, redondeo):
    alcanzados = productos_alcanzados(db, promo)
    candidatos = [i for i in items if alcanzados is None or i.producto_id in alcanzados]
    finales, en_promo = {}, set()
    if promo.tipo is TipoPromocion.PORCENTAJE:
        for i in candidatos:
            finales[i.id] = aplicar_descuentos(i.precio_lista, i.producto.descuento_producto,
                                               Decimal(promo.porcentaje_descuento), redondeo)
            en_promo.add(i.id)
    else:
        en_grupo, gratis = elegir_unidades_gratis(candidatos, promo)
        for i in candidatos:
            if i.id in en_grupo:
                finales[i.id] = Decimal("0") if i.id in gratis else i.precio_unitario
                en_promo.add(i.id)
    ahorro = sum((i.precio_unitario - finales[i.id] for i in candidatos if i.id in finales), Decimal("0"))
    return ahorro, finales, en_promo
```

- `productos_alcanzados`: si algún alcance es `TODOS_PRODUCTOS` o `TODOS_CATEGORIAS` → `None`; si no, unión de los `PRODUCTO` y de `Producto.id` cuyos `categoria_id` está en `rama_de_ids` de cada `CATEGORIA`. Una promo solo con alcance de medio de pago (sin alcance de productos) → `None` (alcanza a todos los productos).
- `promociones_aplicables`: activas, `vigente_el(dia)`, `aplica_con_medios`, y exclusivas: una promo con filas en `cliente_promociones` solo se ofrece si `cliente_id` está entre ellas (sin cliente → no se ofrece). Orden por id.
- CRUD: nombre único (mismo patrón); `porcentaje_descuento` obligatorio (1..75) si `tipo == PORCENTAJE` y debe venir `None` si no (400); fechas coherentes; `alcances: list[{tipo_alcance, referencia_id}]` al menos uno de productos (`PRODUCTO`, `CATEGORIA`, `TODOS_*`) (400 "Elegí a qué productos alcanza"), sin repetidos (400), cada `referencia_id` existente (404) salvo 0 en `TODOS_*`/`MEDIO_DE_PAGO` (para `TODOS_*` forzar 0); sincronizar alcances reemplazándolos. `asignar_a_cliente`: promo existente, sin duplicar (409 "El cliente ya tiene esa promoción"). Auditoría `promocion.crear/editar/activar/desactivar` (con los alcances en el snapshot) y `cliente.promocion_asignar` / `cliente.promocion_quitar` (entidad `cliente`).
- `listar_promociones(rige_hoy=True/False)`: filtra por `vigente_el(hoy)` en SQL (`activo AND (fecha_inicio IS NULL OR fecha_inicio <= hoy) AND (fecha_fin IS NULL OR hoy <= fecha_fin)`), con `hoy = ahora_db().date()`.

**Tests mínimos** (`test_promociones.py`; para `elegir_unidades_gratis` usar objetos simples `SimpleNamespace(id=…, precio_unitario=Decimal(…), orden=…)`):
- `unidades_gratis(5, 2x1) == 2`, `unidades_gratis(5, 3x2) == 1`, `unidades_gratis(1, 2x1) == 0`.
- 2x1 con [100,90,80,70,60] → gratis {90, 70}, en grupo {100,90,80,70}.
- 3x2 con [100,90,80,70] → gratis {80}, en grupo {100,90,80}.
- Empate de precio: el de mayor `orden` es el gratis.
- Porcentaje 20% sobre producto con `descuento_producto` 10%, lista 10000, redondeo 1000 → 10000×0.9×0.8 = 7200 → 7000.
- Alcance por categoría incluye subcategorías; alcance por producto; `todos_*` → None.
- `aplica_con_medios`: sin pagos → True; todos alcanzados → True; uno fuera → False.
- `mejor_promocion`: elige mayor ahorro; empate → menor id; ninguna ahorra → None.
- Exclusivas: promo asignada al cliente A no aparece para B ni sin cliente; sí para A.
- Vigencia: fuera de fechas no aparece; inactiva no aparece.
- CRUD: porcentaje obligatorio solo en tipo porcentaje; alcance repetido 400; referencia inexistente 404; nombre duplicado 409; auditorías.

- [ ] Step 1-5 como la Task 2. Commit `feat(ventas): service de promociones`.

---

### Task 4: Service de ventas (flujo, recálculo, pagos, confirmar, anular, listado) ★ (con revisor)

**Files:**
- Create: `backend/app/schemas/ventas.py`, `backend/app/services/ventas.py`, `backend/tests/test_ventas.py`, `backend/tests/test_anulacion.py`

**Interfaces:**
- Consumes: Tasks 1-3; `services/productos.py::{buscar_por_codigo, obtener_producto}`; `services/stock.py::aplicar_movimiento`; `models.TipoMovimientoStock`; `core/auditoria.py::{registrar_auditoria, snapshot}`.
- Produces (`services/ventas.py`):

```python
MAX_MEDIOS_DE_PAGO = 2
ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # A-Z0-9 sin I, O, 0, 1
LARGO_CODIGO = 4
INTENTOS_CODIGO = 20
TAMANO_MAXIMO = 100

def obtener_venta(db, venta_id) -> Venta                              # 404 "Venta no encontrada"
def bloquear_venta(db, venta_id) -> Venta                             # SELECT … FOR UPDATE + populate_existing
def venta_en_curso(db, usuario) -> Venta | None
def iniciar_venta(db, autor, ip) -> Venta
def agregar_item(db, autor, venta_id, *, codigo=None, producto_id=None, ip=None) -> tuple[Venta, str | None]  # (venta, aviso)
def quitar_item(db, autor, venta_id, item_id) -> Venta
def asociar_cliente(db, autor, venta_id, cliente_id: int | None) -> Venta
def aplicar_descuento_item(db, autor, venta_id, item_id, motivo_id: int | None, porcentaje, ip) -> Venta
def elegir_promocion(db, autor, venta_id, promocion_id: int | None) -> Venta
def registrar_pagos(db, autor, venta_id, pagos: list) -> Venta     # pagos: [{medio_de_pago_id, monto, plan_cuotas_id}]
def recalcular(db, autor, venta_id) -> Venta
def confirmar_venta(db, autor, venta_id, total_esperado: Decimal, ip) -> Venta
def descartar_venta(db, autor, venta_id, ip) -> None
def anular_venta(db, autor, venta_id, motivo: str, ip) -> Venta
def medios_para_venta(db, venta, monto: Decimal | None) -> list[dict]   # [{medio, planes}]
def promociones_para_venta(db, venta) -> list[dict]                     # [{promocion, ahorro}]
def listar_ventas(db, *, cliente_id=None, usuario_id=None, estado=None, numero=None, codigo_cambio=None,
                  total_desde=None, total_hasta=None, fecha_desde=None, fecha_hasta=None,
                  pagina=1, tamano=10) -> tuple[list[Venta], int]
def vendedores(db) -> list[Usuario]
def _turno_para_operar(db) -> int | None
```

**Reglas:**

- `_venta_propia_en_curso(db, autor, venta_id)`: `bloquear_venta`; si `estado != EN_CURSO` → 409 "La venta ya no está en curso"; si `usuario_id != autor.id` → 403 "Solo quien inició la venta puede operarla". TODAS las operaciones de los pasos 2-8 empiezan con esto (el lock evita que dos pestañas pisen el mismo carrito).
- `iniciar_venta`: si hay una en curso del autor, la devuelve (sin auditar). Si no: `numero = f"V-{db.scalar(select(func.nextval('ventas_numero_seq'))):06d}"`, `Venta(usuario_id=autor.id, numero=…)`, flush, auditoría `venta.iniciar` (entidad `venta`). El UNIQUE parcial es la red ante dos POST simultáneos (lo traduce el handler de `IntegrityError` a 409).
- `agregar_item`: exactamente uno de `codigo` / `producto_id` (400). Con código: `buscar_por_codigo` (404). Producto inactivo → 409 "'…' está inactivo". `orden = max(orden)+1` (o 1). Los precios los completa `_recalcular`; al crear el ítem poner `precio_lista = precio_unitario = precio_final = producto.precio_venta` y `costo_unitario = producto.costo_en_pesos` para no violar NOT NULL. Aviso (sin bloquear): si `not producto.stock_infinito` y `producto.stock - unidades_ya_cargadas_de_ese_producto <= 0` → `f"Sin stock de '{producto.descripcion}': controlá bien el código antes de continuar."`. Sin auditoría por ítem.
- `quitar_item`: 404 si el ítem no es de la venta.
- `asociar_cliente`: `None` quita; si no, cliente existente y activo (409 "El cliente '…' está inactivo").
- `aplicar_descuento_item`: ítem de la venta (404); si `item.en_promocion` → 409 "Este producto está en una promoción: no admite otro descuento". `motivo_id is None` → quita (`descuento_item=0`, `motivo=None`, `porcentaje_modificado=False`). Si no: `resolver_porcentaje`, `validar_tope(db, producto.descuento_producto, porcentaje, producto.descripcion)`. Auditoría `venta.descuento` con `estado_anterior={"item_id", "descuento_item", "motivo_descuento_id"}` y el nuevo. El permiso `venta.descuento` lo chequea el router.
- `elegir_promocion`: `None` → sin promoción a mano; si no, debe estar entre `promociones_aplicables(…)` para esta venta (409 "Esa promoción no aplica a esta venta"). Setea `promocion_id`, `promocion_a_mano=True` y recalcula con `respetar_manual=True`.
- Todo cambio del carrito (`agregar_item`, `quitar_item`, `asociar_cliente`, `aplicar_descuento_item`) pone `promocion_a_mano=False` antes de recalcular. `registrar_pagos` y `recalcular` NO lo tocan.

`_recalcular(db, venta, *, estricto=False)` — núcleo (ÚNICO lugar donde se calculan importes de una venta):

```python
def _recalcular(db, venta, *, estricto=False):
    redondeo = obtener_configuracion(db).redondeo
    # 1. Precio vivo: relee cada producto (decisión 3) y recalcula sin promociones.
    for item in venta.items:
        producto = item.producto
        item.precio_lista = producto.precio_venta
        item.costo_unitario = producto.costo_en_pesos
        item.precio_unitario = aplicar_descuentos(producto.precio_venta, producto.descuento_producto,
                                                  Decimal("0"), redondeo)
        item.en_promocion = False
        item.precio_final = (aplicar_descuentos(producto.precio_venta, producto.descuento_producto,
                                                item.descuento_item, redondeo)
                             if item.descuento_item else item.precio_unitario)
    # 2. Promoción: la manual si sigue aplicando; si no, la de mayor ahorro.
    elegibles = [i for i in venta.items if not i.descuento_item]
    medio_ids = {p.medio_de_pago_id for p in venta.pagos}
    aplicables = promociones_aplicables(db, venta.cliente_id, ahora_db().date(), medio_ids)
    if venta.promocion_a_mano and (venta.promocion_id is None or any(p.id == venta.promocion_id for p in aplicables)):
        promo = next((p for p in aplicables if p.id == venta.promocion_id), None)
    else:
        venta.promocion_a_mano = False
        promo = mejor_promocion(db, aplicables, elegibles, redondeo)
    venta.promocion_id = promo.id if promo else None
    if promo:
        _, finales, en_promo = simular(db, promo, elegibles, redondeo)
        for item in elegibles:
            if item.id in en_promo:
                item.precio_final, item.en_promocion = finales[item.id], True
    # 3. Totales sin recargo.
    venta.subtotal = sum((i.precio_lista for i in venta.items), Decimal("0"))
    cobrable = sum((i.precio_final for i in venta.items), Decimal("0"))
    venta.descuento_total = venta.subtotal - cobrable
    # 4. Pagos: se normalizan (decisión 5) y se recalcula su recargo.
    _normalizar_pagos(db, venta, cobrable, estricto=estricto)
    venta.recargo_total = sum((p.recargo for p in venta.pagos), Decimal("0"))
    venta.total = cobrable + venta.recargo_total
    db.flush()
```

`_normalizar_pagos(db, venta, cobrable, *, estricto)`:
- sin pagos → nada.
- `cobrable <= 0` → problema "No hay nada para cobrar".
- 1 pago: `monto = cobrable`. 2 pagos: el segundo `monto = cobrable - primero.monto`; si ≤ 0 → problema "El primer pago ya cubre todo: sacá el segundo medio de pago".
- Por pago con plan: `habilita = any(i.motivo_descuento and i.motivo_descuento.habilita_cuotas_sin_interes for i in venta.items)`; si el plan no está en `planes_disponibles(medio, pago.monto, habilita)` → problema `f"El plan de {plan.cuotas} cuotas no está disponible para {monto}"`.
- `pago.recargo = calcular_recargo(pago.monto, plan)`, `pago.monto_total = monto + recargo`.
- Ante un problema: si `estricto` → `raise DatoInvalido(problema)`; si no → borrar todos los pagos (`venta.pagos.clear()`).

- `registrar_pagos`: `len(pagos) <= MAX_MEDIOS_DE_PAGO` (400 "Hasta 2 medios de pago"); lista vacía = borrar pagos. Cada pago: medio existente y activo (409), `monto > 0` (schema), `plan_cuotas_id` si viene: plan del mismo medio y activo (400 "El plan no corresponde a ese medio de pago"), medio con cuotas. Reemplaza `venta.pagos` y llama `_recalcular(db, venta, estricto=True)`. El monto del único pago y el del segundo los fija el backend (decisión 5): la API ignora los que vengan en esas posiciones salvo el primero de dos.
- `recalcular`: `_venta_propia_en_curso` + `_recalcular`.
- `confirmar_venta`:
  1. `_venta_propia_en_curso`; `turno_id = _turno_para_operar(db)` (hoy `None`; en la sesión 07 levanta 409).
  2. `_recalcular(db, venta)`; sin ítems → 409 "La venta no tiene productos"; sin pagos o `sum(p.monto) != venta.cobrable` → 409 "Cargá los medios de pago para cubrir el total"; `venta.total != total_esperado` → 409 "Los precios cambiaron mientras cargabas la venta: revisá el total y volvé a confirmar."
  3. Movimientos: `Counter(i.producto_id for i in venta.items)`, recorrido en `sorted(…)` por `producto_id` ascendente: `aplicar_movimiento(db, autor, tipo=VENTA, producto_id=pid, cantidad=-n, referencia_venta_id=venta.id, permitir_faltante=True, ip_origen=ip)`.
  4. `codigo_cambio = _generar_codigo(db)`: `"".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))`, reintentando si ya existe (`select(Venta.id).where(Venta.codigo_cambio == c)`) hasta `INTENTOS_CODIGO` (después 409 "No se pudo generar el código de cambio: reintentá").
  5. `confirmada_en = ahora_db()`, `turno_id`, `estado = CONFIRMADA`. Auditoría `venta.confirmada` con `estado_nuevo` = snapshot de la venta + `items` (producto_id, precio_final) + `pagos`.
- `descartar_venta`: auditoría `venta.descartar` con el snapshot (numero, subtotal, cantidad de ítems) ANTES de `db.delete(venta)`.
- `anular_venta`: `bloquear_venta`; `EN_CURSO` → 409 "Una venta en curso se descarta, no se anula"; `ANULADA` → 409 "La venta ya está anulada"; motivo `strip()`, 1..500 (400 "El motivo de anulación es obligatorio"). `turno = _turno_para_operar(db)`. `antes = snapshot(venta)`. Movimientos `ANULACION_VENTA` con cantidad POSITIVA por producto en orden ascendente (`referencia_venta_id=venta.id`). Sella `anulada_en`, `anulada_por_id=autor.id`, `motivo_anulacion`, `turno_anulacion_id=turno`, `estado=ANULADA`. Los pagos NO se tocan. Auditoría `venta.anular` con `estado_anterior=antes` y `estado_nuevo` con el motivo. Cualquier usuario con el permiso puede anular (no hace falta ser quien vendió).
- `medios_para_venta(db, venta, monto)`: medios activos ordenados por nombre, cada uno con `planes_disponibles(medio, monto or venta.cobrable, habilita)`.
- `promociones_para_venta`: `promociones_aplicables` de la venta, cada una con su `ahorro` (de `simular` sobre los elegibles), sin tocar la venta.
- `listar_ventas`: `numero` con `filtro_texto`; `codigo_cambio` exacto `upper()`; fechas sobre `coalesce(confirmada_en, created_at)` con `rango_fechas`; totales con `>=`/`<=`; orden `coalesce(confirmada_en, created_at) DESC, id DESC`; carga cliente, usuario y pagos (`selectinload`).
- `_turno_para_operar`:

```python
def _turno_para_operar(db) -> int | None:
    """Turno de caja en el que se cobra/anula. Hasta la sesión 07 no hay caja:
    devuelve None y no bloquea. La sesión 07 reemplaza SOLO esta función por
    services.turnos.turno_para_operar() (409 si no hay turno abierto de hoy)."""
    return None
```

**Schemas (`schemas/ventas.py`):** `ItemAgregar {codigo: str | None (1..30), producto_id: int | None}`, `ClienteAsociar {cliente_id: int | None}`, `DescuentoAplicar {item_id: int, motivo_id: int | None, porcentaje: int | None (ge=1, le=100)}`, `PromocionElegir {promocion_id: int | None}`, `PagoDatos {medio_de_pago_id: int, monto: Decimal (gt=0, le=99_999_999.99, decimal_places=2), plan_cuotas_id: int | None}`, `PagosRegistrar {pagos: list[PagoDatos] (max_length=2)}`, `ConfirmarVenta {total_esperado: Decimal (ge=0, decimal_places=2)}`, `AnularVenta {motivo: str (1..500)}`. Respuestas: `VentaItemResponse` (id, producto_id, codigo, descripcion, categoria, foto_url, precio_lista, precio_unitario, descuento_item, descuento_efectivo = `calcular_descuento_total(descuento_producto, descuento_item)`, motivo `{id, nombre} | None`, porcentaje_modificado, precio_final, en_promocion, orden — **sin costo**), `VentaPagoResponse` (id, medio `{id, nombre}`, plan `{id, cuotas, recargo_cliente} | None`, monto, recargo, monto_total), `VentaResponse` (id, numero, estado, cliente `{id, nombre, condicion_iva} | None`, usuario `{id, nombre}`, items, pagos, subtotal, descuento_total, recargo_total, total, cobrable, promocion `{id, nombre} | None`, promocion_a_mano, codigo_cambio, confirmada_en, created_at, anulada_en, anulada_por `{id, nombre} | None`, motivo_anulacion), `VentaResumen` (lo del spec: numero, fecha = `confirmada_en or created_at`, usuario, cliente, subtotal, descuento_total, total, codigo_cambio, estado, medios `list[str]`, anulada_en, anulada_por, motivo_anulacion), `AgregarItemResponse {venta: VentaResponse, aviso: str | None}`, `ProductoVenta` (id, codigo = `codigo_con_verificador`, descripcion, categoria, precio = `aplicar_descuentos(precio_venta, descuento_producto, 0, redondeo)`, precio_lista, stock, stock_infinito, foto_url), `OpcionesDescuento {motivos: [{id, nombre, nota, porcentaje_sugerido, habilita_cuotas_sin_interes}], porcentajes: list[int], tope: Decimal}`, `MedioParaVenta {id, nombre, es_efectivo, soporta_cuotas, planes: [{id, cuotas, recargo_cliente, monto_minimo}]}` (sin `costo_medio`), `PromocionParaVenta {id, nombre, nota, tipo, ahorro}`. Cada respuesta con `@classmethod desde(...)` como en `schemas/stock.py`.

**Tests** — `test_ventas.py` (fixture con `catalogo`, productos de 10000 / 8000 / 6000 con stock cargado por `registrar_ingreso`, un vendedor y un supervisor):
- `iniciar_venta` dos veces devuelve la misma; número `V-` + 6 dígitos; auditoría `venta.iniciar` una sola vez.
- Otro usuario operando la venta → `SinPermiso`.
- `agregar_item` por código con verificador y por `producto_id`; código inexistente 404; inactivo 409; sin stock → aviso y el ítem igual se agrega; aviso contando lo ya cargado (stock 1, segunda unidad → aviso).
- Descuento: 10% con motivo → `precio_final` encadenado y hacia abajo; tope sumando `descuento_producto` (producto con 45%, pedir 10% → 400); no en ítem en promoción (409); quitar descuento; `porcentaje_modificado`.
- Promoción automática 2x1 (3 unidades → la más barata del grupo gratis, el sobrante se cobra); elegir otra a mano y que se pierda al agregar un ítem; "Sin promoción" a mano.
- Promo exclusiva: aparece solo con el cliente asignado.
- Promo con alcance Débito: con pago en Efectivo no se aplica; con Débito sí; con Débito + Efectivo no.
- Pagos: un pago toma lo cobrable; dos pagos → el segundo es el resto; primero ≥ cobrable con 2 pagos → 400; más de 2 → 400; plan bajo el mínimo → 400; plan sin interés habilitado por motivo con `habilita_cuotas_sin_interes` bajo el mínimo → OK; recargo solo sobre la parte financiada (Efectivo 5000 + Crédito 3 cuotas 10% sobre 5000 → recargo 500, total = cobrable + 500).
- Cambio del carrito que deja inválidos los pagos → se borran.
- Precio vivo: cambiar `precio_venta` del producto (vía `editar_producto`) y `recalcular` → nuevo precio; `confirmar` con el `total_esperado` viejo → 409.
- `confirmar_venta`: descuenta stock con movimientos `venta` (uno por producto, cantidad −n, `referencia_venta_id`); stock puede quedar negativo; `costo_unitario` congelado (cambiar el costo después no lo altera); código de 4 caracteres en `ALFABETO_CODIGO`; auditoría `venta.confirmada`; sin ítems → 409; sin pagos → 409; venta ya confirmada → 409.
- Código de cambio con colisión: monkeypatch de `secrets.choice` para devolver primero un código existente → reintenta.
- `descartar_venta` borra ítems y pagos y audita; `listar_ventas` con cada filtro (número, código sin importar mayúsculas, estado, fechas, totales, vendedor, cliente).
- `costo_unitario` no aparece en `VentaResponse.model_dump()`.

`test_anulacion.py`: solo confirmadas (en curso 409, anulada 409); motivo obligatorio; reingresa stock con `anulacion_venta` por producto; sella `anulada_en`, `anulada_por_id`, `motivo_anulacion`, `turno_anulacion_id` (None hoy); pagos intactos; auditoría `venta.anular` con estado anterior y motivo; la puede anular otro usuario distinto del vendedor. (El 403 sin `venta.anular` se testea en la API, Task 5.)

- [ ] Step 1-5 como la Task 2. Commit `feat(ventas): service de ventas con recálculo, pagos, confirmación y anulación`.

---

### Task 5: Endpoints de clientes, configuración y ventas ★ (con revisor)

**Files:**
- Create: `backend/app/api/v1/clientes.py`, `backend/app/api/v1/configuracion.py`, `backend/app/api/v1/ventas.py`, `backend/tests/{test_clientes_api,test_configuracion_api,test_ventas_api}.py`
- Modify: `backend/app/api/v1/__init__.py` (incluir los tres routers)

**Interfaces:**
- Consumes: services de las Tasks 2-4; `core/seguridad.py::requiere_permiso(modulo, accion, recurso=None)`; `core/utils.py::ip_de_request`; `schemas/comunes.py::RespuestaPaginada`.
- Produces: las rutas del spec (sección "BACKEND — ENDPOINTS") más `GET /ventas/vendedores` y `POST /ventas/{id}/recalcular`. Dependencias:

```python
# clientes.py
puede_ver = requiere_permiso(Modulo.CLIENTES, "ver")
puede_crear = requiere_permiso(Modulo.CLIENTES, "crear")
puede_editar = requiere_permiso(Modulo.CLIENTES, "editar")
# configuracion.py
puede_ver = requiere_permiso(Modulo.CONFIGURACION, "ver")
puede_editar = requiere_permiso(Modulo.CONFIGURACION, "editar")
promos_ver = requiere_permiso(Modulo.CONFIGURACION, "ver", Recurso.PROMOCIONES)
promos_crear = requiere_permiso(Modulo.CONFIGURACION, "crear", Recurso.PROMOCIONES)
promos_editar = requiere_permiso(Modulo.CONFIGURACION, "editar", Recurso.PROMOCIONES)
# ventas.py
puede_ver = requiere_permiso(Modulo.VENTAS, "ver")
puede_vender = requiere_permiso(Modulo.VENTAS, "crear")
puede_descontar = requiere_permiso(Modulo.VENTAS, "crear", Recurso.VENTA_DESCUENTO)
puede_anular = requiere_permiso(Modulo.VENTAS, "eliminar", Recurso.VENTA_ANULAR)
```

- `POST /configuracion/promociones` usa `promos_crear`; `PUT` y `PATCH …/estado` usan `promos_editar` (el spec dice "editar" para POST, pero el recurso tiene la acción `crear` y el supervisor la tiene sembrada).
- `POST /ventas/{id}/descuento`: `Depends(puede_vender)` **y** `Depends(puede_descontar)`. `POST /ventas/{id}/anular`: `Depends(puede_ver)` **y** `Depends(puede_anular)` (decisión 6).
- En `ventas.py` las rutas fijas (`/en-curso`, `/opciones-descuento`, `/producto`, `/productos`, `/vendedores`) se declaran ANTES de `/{venta_id}` (comentarlo); `venta_id: int`.
- `GET /ventas/producto?codigo=` → `ProductoVenta` (404 si no existe; 409 si inactivo). `GET /ventas/productos?busqueda=&limite=8` → reusa `servicio_productos.listar_productos(db, busqueda=busqueda, activo=True, tamano=limite)` (`limite` 1..20) y mapea a `ProductoVenta`. El redondeo para `precio` se lee una vez por request.
- `GET /ventas/{id}/medios-de-pago?monto=` (`monto` opcional, `gt=0`).
- `POST /ventas/{id}/confirmar` recibe `ConfirmarVenta`.
- `GET /ventas` paginado (`tamano` ≤ `TAMANO_MAXIMO`, `pagina` ≤ 100_000 como en `stock.py`).
- `GET /clientes/{id}` → `ClienteFicha` (datos + promociones `{id, nombre, tipo, vigente}` + `compras_cantidad` + `compras_total`).
- Toda escritura: service → `db.commit()` → respuesta; `status_code=201` en altas (`POST ""` de clientes, medios, planes, motivos, promociones; `POST /ventas` devuelve 201 solo si la creó: más simple devolver 200 siempre y documentarlo en el docstring).
- `DELETE /ventas/{id}` y `DELETE /clientes/{id}/promociones/{pid}` → 204.

**Tests de API (mínimos, con `client` + `headers_de`):**
- Permisos: Vendedor sembrado puede `POST /ventas`, agregar, descontar (tiene `venta.descuento`), pagar y confirmar; NO puede anular (403); Supervisor sí anula (200) aunque no tenga `ventas eliminar`; rol sin `venta.descuento` → 403 en `/descuento`; Vendedor no ve `/configuracion/promociones` (403) y el supervisor sí; `POST /configuracion/medios-de-pago` exige CONFIGURACION editar (vendedor 403).
- Venta completa por API sin cliente: iniciar → agregar por código → pagos → confirmar con `total_esperado` → 200, `estado == "confirmada"`, `len(codigo_cambio) == 4`.
- `GET /ventas/en-curso` devuelve `null` sin venta abierta.
- `GET /ventas/{id}` y `GET /ventas` no contienen la clave `costo_unitario` (buscar recursivamente en el JSON).
- Rutas fijas antes de `/{venta_id}`: `GET /ventas/en-curso` no da 422.
- `POST /ventas/{id}/items` con producto sin stock → 200 con `aviso`.
- Clientes: alta con CUIT inválido → 400; duplicado → 409; `GET /clientes/buscar?q=` ; ficha.
- Configuración: CRUD de un medio, de un plan, de un motivo y de una promoción (happy path + una validación cada uno), `GET /promociones/catalogos`.
- Auditoría: `GET /api/v1/auditoria?accion=venta.anular` devuelve el registro después de anular.

- [ ] Step 1-5 como la Task 2. Commit `feat(ventas): API de clientes, configuración de ventas y ventas`.

---

### Task 6: Pantallas de Clientes y de los catálogos de ventas

**Files:**
- Create: `pages/clientes/listado.html` + `static/js/clientes.js`; `components/cliente_form.html` (macro con el formulario de cliente, reusada por la pantalla de venta); `pages/medios_pago/listado.html` + `static/js/medios_pago.js`; `pages/motivos_descuento/listado.html` + `static/js/motivos_descuento.js`; `pages/promociones/listado.html` + `static/js/promociones.js`; `backend/tests/test_paginas_ventas.py`
- Modify: `backend/app/api/pages.py`

**Qué hacer** (seguir `pages/motivos_baja/listado.html` + `motivos_baja.js` y `pages/proveedores/*` como modelos de ABM con filtros, modal de formulario y switch de estado):

- `pages.py`:
  - `PAGINA_CLIENTES = {"nombre": "Clientes", "url": "/clientes", "icono": "clientes", "modulo": Modulo.CLIENTES}`, en `MENU_SIDEBAR` según el orden de CLAUDE.md (Productos, Gestión de Stock, **Ventas**, **Clientes**, …). El ítem de Ventas lo agrega la Task 7: dejar el lugar comentado.
  - Tarjetas de Configuraciones registradas en bucle:

```python
# Catálogos de ventas en el hub Configuraciones (sesión 06).
_CATALOGOS_VENTAS = [
    {"nombre": "Medios de pago", "descripcion": "Formas de cobro y planes de cuotas", "url": "/medios-de-pago",
     "modulo": Modulo.CONFIGURACION, "plantilla": "pages/medios_pago/listado.html"},
    {"nombre": "Motivos de descuento", "descripcion": "Por qué se descuenta al vender y cuánto se sugiere",
     "url": "/motivos-descuento", "modulo": Modulo.CONFIGURACION,
     "plantilla": "pages/motivos_descuento/listado.html"},
    {"nombre": "Promociones", "descripcion": "2x1, 3x2 y descuentos por porcentaje", "url": "/promociones",
     "modulo": Modulo.CONFIGURACION, "recurso": Recurso.PROMOCIONES,
     "plantilla": "pages/promociones/listado.html"},
]
CONFIGURACION_SECCIONES.extend(_CATALOGOS_VENTAS)


def _registrar_catalogo(seccion: dict) -> None:
    def pagina(request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_pagina(seccion))):
        return _pagina(request, seccion["plantilla"], contexto_base(
            request, db, "/configuracion", usuario,
            puede_editar=resolver_permiso(db, usuario.id, seccion["modulo"], "editar", seccion.get("recurso")),
            puede_crear=resolver_permiso(db, usuario.id, seccion["modulo"],
                                         "crear" if seccion.get("recurso") else "editar", seccion.get("recurso")),
        ))
    router.add_api_route(seccion["url"], pagina, methods=["GET"])


for _seccion in _CATALOGOS_VENTAS:
    _registrar_catalogo(_seccion)
```

  (Verificar que `_visible` / `requiere_pagina` acepten `recurso` sin `accion` y usen "ver" por defecto; si no, pasar `"accion": "ver"`.)
  - `GET /clientes` con `requiere_pagina(PAGINA_CLIENTES, actual="/clientes")`, contexto `puede_crear`, `puede_editar`, `condiciones_iva` (lista `[(valor, etiqueta)]` definida UNA vez en `pages.py` como `CONDICIONES_IVA`, igual que `TEMPORADAS`).
- `/clientes`: filtros "Nombre, DNI o CUIT" y "Localidad" en tiempo real (debounce como `motivos_baja.js`), select "Condición IVA (todas)", switch de activos, "Limpiar filtros", contador, paginado de a 10 (macro `paginacion`). Columnas Nombre, DNI, CUIT, Condición IVA, Localidad, Teléfono, Estado; acciones Ver / Editar / activar. Formulario (macro `cliente_form`) con placeholders del spec ("Leandra Carballo", "39059158", "20390591581"), CUIT marcado obligatorio cuando la condición no es consumidor final (`x-bind:required`), errores 422 con `erroresDeCampos`. Ficha en modal: datos, cantidad y total de compras (`pesos()`), link "Ver compras" → `/ventas/resumen-ventas?cliente_id={id}`, Promociones asignadas con "Quitar" y un select + "Asignar" (solo si `puede_editar` y el usuario puede ver promociones: pasar `puede_ver_promociones` en el contexto y no pedir `/configuracion/promociones` si falta, para no generar toasts de 403).
- `/medios-de-pago`: filtros Nombre, "Cuotas (todos) / Con cuotas / Sin cuotas", estado. Columnas Nombre, marcas "Cuotas" / "Efectivo" (macro `badge`), Estado. Formulario con "Se cobra en cuotas" y "Es el efectivo de la caja". Al abrir un medio con cuotas: tabla de planes (Cuotas, Recargo al cliente, Costo del medio, Monto mínimo, Estado) con alta/edición/activar en su propio modal.
- `/motivos-descuento`: filtros Nombre, "Cuotas sin interés (todos) / Las habilita / No las habilita", estado. Columnas Nombre (con `title` = nota), % sugerido ("Lo elige quien vende" si null), Cuotas sin interés (Sí/No), Estado. Formulario: nombre ("Cumpleaños"), nota, % sugerido (select con `porcentajes_descuento`, que la página pasa en el contexto desde `services.descuentos.porcentajes_validos(db)`; no usar `GET /ventas/opciones-descuento` porque pide VENTAS ver) o "Que lo elija quien vende", "Habilita cuotas sin interés", Vigencia desde/hasta ("Sin fechas: vigencia indefinida."), Medios de pago (checkboxes; ninguno = "Todos los medios de pago").
- `/promociones`: filtros Nombre, "Tipo (todos)", "Vigencia (todas) / Rige hoy / No rige hoy", estado. Columnas Nombre (tooltip nota), Tipo, Alcance (texto armado en JS con los catálogos), Vigencia, Estado. Formulario: nombre ("2x1 Plata"), nota, tipo con los textos del spec, % (1-75) visible solo en tipo porcentaje, vigencia ("Vacío = sin límite."), alcance: Producto (combobox) / Categoría (camino completo, combobox) / "Todos los productos" / "Todas las categorías" (lista de alcances con quitar), Medios de pago (checkboxes, ninguno = todos). Catálogos desde `GET /configuracion/promociones/catalogos`.
- Tests de páginas (`test_paginas_ventas.py`): cada URL responde 200 al admin y 403 (página "sin permiso") a quien no tiene el permiso; el hub Configuraciones muestra las tres tarjetas al admin y no muestra Promociones al vendedor; el sidebar muestra "Clientes" al vendedor.

- [ ] Implementar, `node --check` de cada JS nuevo, suite completa, commit `feat(ventas): pantallas de clientes, medios de pago, motivos de descuento y promociones`.

---

### Task 7: Hub de Ventas y pantalla de venta

**Files:**
- Create: `pages/ventas/hub.html`, `pages/ventas/nueva.html`, `static/js/venta.js`, `backend/tests_js/venta.test.mjs`
- Modify: `backend/app/api/pages.py`, `backend/tests/test_paginas_ventas.py`

**Qué hacer:**

- `pages.py`: `PAGINA_VENTAS_HUB = {"nombre": "Ventas", "url": "/ventas", "icono": "ventas", "modulo": Modulo.VENTAS}` en `MENU_SIDEBAR` antes de Clientes. `SECCION_NUEVA_VENTA = {"nombre": "Nueva venta", "descripcion": "Cargar productos, aplicar descuentos y cobrar", "url": "/ventas/nueva", "modulo": Modulo.VENTAS, "accion": "crear"}`, `SECCION_RESUMEN_VENTAS = {"nombre": "Resumen de Ventas", "descripcion": "Ventas del período con subtotal, descuento, total y medio de pago", "url": "/ventas/resumen-ventas", "modulo": Modulo.VENTAS}`, `SECCIONES_VENTAS = [SECCION_NUEVA_VENTA, SECCION_RESUMEN_VENTAS]`. Cada tarjeta con `title` = su descripción. En el hub, si el usuario tiene una venta en curso (`servicios_ventas.venta_en_curso(db, usuario)`), la tarjeta "Nueva venta" dice `f"Continuar venta {venta.numero}"` (copiar el dict, no mutar la constante). `_contexto_ventas(...)` con `puede_vender`, `puede_descontar`, `puede_anular`, `puede_crear_cliente` (CLIENTES crear), `puede_ver_clientes`, `condiciones_iva`, y `actual="/ventas"`.
- `/ventas/nueva` (`requiere_pagina(SECCION_NUEVA_VENTA, actual="/ventas")`): encabezado "Nueva venta" + número si existe (macro `encabezado`, volver a "Ventas").
- **Toda la aritmética viene de la API.** El componente `window.ventaPantalla()` solo muestra `venta` (la última `VentaResponse`) y manda acciones.
- Lógica pura extraída y exportada en `window.ventaLogica` (y testeada con `node --test` como en `productos.test.mjs`):

```js
window.ventaLogica = {
  // Código de etiqueta o SKU: Enter lo agrega directo sin abrir el desplegable.
  esCodigo: (texto) => /^[A-Za-z]{2}[0-9]{3}[0-9A-Za-z]?$/.test(String(texto || '').trim()),
  // En el desplegable: sin stock y sin stock infinito → deshabilitado.
  puedeAgregar: (p) => p.stock_infinito || p.stock > 0,
  // Texto de la columna Descuento.
  textoDescuento: (item) => item.en_promocion ? 'Promo'
    : (Number(item.descuento_item) > 0 ? `${Number(item.descuento_item)}% · ${item.motivo?.nombre ?? ''}` : ''),
  puedeDescontar: (item, permiso) => permiso && !item.en_promocion,
  // Índice del desplegable con flechas (circular, -1 = ninguno).
  moverIndice: (actual, total, delta) => total === 0 ? -1 : (actual + delta + total) % total,
  // Pagos que se mandan al backend: el monto del primero solo importa si hay dos.
  pagosParaEnviar: (filas) => filas.filter((f) => f.medio_de_pago_id)
    .map((f) => ({ medio_de_pago_id: Number(f.medio_de_pago_id), monto: String(f.monto || '0.01'),
                   plan_cuotas_id: f.plan_cuotas_id ? Number(f.plan_cuotas_id) : null })),
  puedeConfirmar: (venta, hayTurno) => !!venta && venta.items.length > 0 && venta.pagos.length > 0 && hayTurno,
};
```

  (`hayTurno` es `true` hasta la sesión 07: pasarlo del contexto como `hay_turno=True` con un comentario.)
- Columna izquierda: buscador "Código, SKU o descripción" con `x-ref` y foco al cargar; `@atajo-buscar.window` lo enfoca. Enter: si `esCodigo` → `GET /ventas/producto?codigo=` y agrega; si no, abre el desplegable de `GET /ventas/productos` (debounce 300 ms con su propio `ultimaRespuesta()`, flechas/Enter/Escape con `moverIndice`), filas con foto (macro `miniatura`), código, descripción, `pesos(precio)` y stock (rojo si ≤ 0); las que no `puedeAgregar` quedan `disabled` con `aria-disabled`. Agregar: si no hay venta, `POST /ventas`, después `POST /ventas/{id}/items`; si llega `aviso` → `toast(aviso, 'error')`.
- Tabla del carrito (una fila por unidad, dentro de `overflow-x-auto`): Foto, Código, Descripción, Precio (lista tachada si `precio_lista != precio_unitario`), Descuento (`textoDescuento`), Final, acciones Descuento (si `puedeDescontar`) y Quitar (macro `botones`). Vacío: "Escaneá o buscá un producto para empezar."
- Popover de descuento: select "Elegí un motivo" (de `GET /ventas/opciones-descuento`, `title` = nota); si el motivo no tiene sugerido, select de porcentajes; "Aplicar" / "Quitar descuento" → `POST /ventas/{id}/descuento`.
- Columna derecha (tarjeta `lg:sticky`, `top` con `--header-height`): Cliente (combobox sobre `/clientes/buscar`, muestra nombre + condición IVA, "Quitar"; "+ Nuevo cliente" abre modal con la macro `cliente_form` → `POST /clientes` → `POST /ventas/{id}/cliente`; oculto si falta el permiso); Promoción (texto de la aplicada + select "Sin promoción" y las de `GET /ventas/{id}/promociones` con su ahorro → `POST /ventas/{id}/promocion`); Medios de pago (hasta 2 filas: medio, monto, plan "Un pago" + planes de `GET /ventas/{id}/medios-de-pago?monto=`; al cambiar medio/monto/plan → `POST /ventas/{id}/pagos` con `pagosParaEnviar`, secuenciado con `ultimaRespuesta()`; el monto del único pago y el del segundo se muestran de solo lectura con lo que devolvió la API; "+ Otro medio" hasta 2); Totales: Subtotal, Descuentos y promociones, Recargo por cuotas, **Total** (todo `pesos(...)` de la respuesta).
- Botones "Confirmar venta" (deshabilitado si `!puedeConfirmar`; también `@atajo-confirmar.window`) → `POST /ventas/{id}/confirmar {total_esperado: venta.total}`; si responde 409 con el mensaje de precios cambiados: toast + `POST /ventas/{id}/recalcular` y mostrar el nuevo total. "Descartar venta" (y `@atajo-cancelar.window` cuando no hay un modal/popover abierto) → `confirmar({...})` → `DELETE /ventas/{id}`.
- Modal "Venta confirmada": código de cambio grande (`text-5xl font-mono tracking-widest`), total cobrado, botones "Nueva venta" (limpia estado y enfoca el buscador) e "Ir al resumen".
- Al entrar: `GET /ventas/en-curso` y retoma.
- Layout: una columna por debajo de `lg`; `lg:grid-cols-[minmax(0,1fr)_24rem]` (o similar) desde `lg`. Botones con `min-h-toque`.
- Tests: `test_paginas_ventas.py` (hub 200 con las dos tarjetas; "Continuar venta V-…" cuando hay una en curso; `/ventas/nueva` 403 sin VENTAS crear; el sidebar muestra "Ventas"); `venta.test.mjs` para cada función de `ventaLogica`.

- [ ] Implementar, `node --check`, `node --test backend/tests_js/`, suite completa, commit `feat(ventas): hub de ventas y pantalla de venta`.

---

### Task 8: Resumen de Ventas con detalle y anulación

**Files:**
- Create: `pages/ventas/listado.html`, `static/js/ventas.js`, `backend/tests_js/ventas.test.mjs`
- Modify: `backend/app/api/pages.py`, `backend/tests/test_paginas_ventas.py`, `docs/pendientes.md`

**Qué hacer:**

- `GET /ventas/resumen-ventas` con `requiere_pagina(SECCION_RESUMEN_VENTAS, actual="/ventas")` y `_contexto_ventas`; pasar `cliente_id` inicial si viene en la query (`int | None`) — es un enlace desde la ficha del cliente, no un filtro persistido.
- Tabla de alto volumen: filtros con botón **"Buscar"** explícito y "Limpiar filtros": Número ("V-000123"), Código de cambio, Estado (Todos / En curso / Confirmada / Anulada), Fecha desde/hasta (por defecto hoy, en hora local), Vendedor (combobox sobre `GET /ventas/vendedores`, "Todos"); si viene `cliente_id`, un chip "Cliente: …" quitable. Contador "N registros encontrados". Paginado de a 10 con "Anterior"/"Siguiente" (macro `paginacion`).
- Columnas: Número, Fecha (`fechaHora`), Vendedor, Cliente, Subtotal, Descuento, Total, Medio de pago (medios unidos por " + "), Código de cambio, Estado (Anulada en rojo con el total tachado; `estadoHtml`).
- Detalle en modal (`GET /ventas/{id}`, secuenciado con `ultimaRespuesta()` y descartado si cambió el id abierto): Productos (descripción, final), "Subtotal (precios de lista)", "Descuentos y promociones", "Recargo por cuotas", Medios de pago ("Todavía sin cobrar." si no hay) y, si está anulada, "Anulada el … por … — Motivo: …".
- Si `estado === 'confirmada'` y `puede_anular`: botón rojo "Anular venta" → textarea de motivo obligatorio (1-500) → `confirmar({mensaje: 'Se devuelve el stock y el importe sale de la caja del turno actual. No se puede deshacer.'})` → `POST /ventas/{id}/anular` → toast, recarga la fila y el detalle.
- Lógica pura en `window.ventasLogica` testeada con `node --test`: `filtrosIniciales(hoyIso, clienteId)`, `queryDeFiltros(filtros, pagina)` (omite vacíos, código en mayúsculas), `textoMedios(venta)`, `puedeAnular(venta, permiso)`.
- `docs/pendientes.md`: nueva sección "Módulo 06: pendientes" con lo que quede de la revisión, y "Para la sesión 07": reemplazar `services/ventas.py::_turno_para_operar`, sumar la FK de `turno_id`/`turno_anulacion_id`, el aviso de turno en `/ventas/nueva` (`hay_turno`) y el test "confirmar sin turno → 409".
- Tests de páginas: `/ventas/resumen-ventas` 200 para el vendedor; el botón de anular solo se renderiza con `puede_anular` (buscar el flag en el HTML).

- [ ] Implementar, `node --check`, `node --test backend/tests_js/`, suite completa, commit `feat(ventas): resumen de ventas con detalle y anulación`.

---

## Después de las tareas

1. Revisión final completa con Opus sobre `git diff dev...modulo-06-ventas` (spec + CLAUDE.md + este plan).
2. Una sola tanda de correcciones (`fix(ventas): correcciones de la revisión final del módulo 06`).
3. Verificación manual en el navegador de la pantalla de venta (F2 / F10 / ESC, lector de código, 320px → 1920px).
4. Merge a `dev` (`git merge --no-ff modulo-06-ventas -m "Merge del módulo 06: clientes y ventas"`) solo cuando el usuario lo pida.
