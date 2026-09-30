# SESIÓN 05 — Control de Stock
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 a 04 completadas y funcionando
- Tablas `usuarios`, `proveedores`, `categorias`, `productos` y `motivos_baja`
  ya existentes

## OBJETIVO DE ESTA SESIÓN
Stock por producto con movimientos trazables, mínimo de reposición, ingresos,
bajas y auditorías de inventario (conteos). Hub "Gestión de Stock".

## CONTEXTO DE NEGOCIO
Hay un **único punto de venta**: el stock es un número por producto (no hay
ubicaciones, depósitos ni traslados). Nunca se modifica directamente: toda
entrada, salida o ajuste es un movimiento que actualiza el stock del producto
en la misma transacción.

---

## MODELO DE DATOS (migración de esta sesión)

```sql
-- A productos se le agregan:
--   stock          INTEGER NOT NULL DEFAULT 0   -- nunca queda negativo (tampoco por ventas)
--   stock_minimo   INTEGER NOT NULL DEFAULT 0   -- CHECK >= 0
-- Propiedad/column_property `bajo_minimo` = stock_minimo > 0 AND stock <= stock_minimo.
-- `productos.stock` SOLO lo escribe `aplicar_movimiento` (no está en ningún
-- schema de alta/edición de productos).

-- ENUM tipo_movimiento_stock: ingreso_proveedor, venta, anulacion_venta, baja, ajuste_auditoria
--   (anulacion_venta la usa la sesión 06: reingresa lo de una venta anulada)
-- ENUM estado_auditoria_inventario: en_curso, cerrada

movimientos_stock (   -- append-only en la práctica: los errores se corrigen con otro movimiento
  id                   BIGSERIAL PK,
  tipo                 tipo_movimiento_stock NOT NULL,          -- índice
  producto_id          BIGINT FK → productos.id RESTRICT NOT NULL,   -- índice
  cantidad             INTEGER NOT NULL,        -- con signo: + entra, − sale; CHECK <> 0
  stock_resultante     INTEGER NOT NULL,        -- stock del producto después del movimiento
  motivo_baja_id       BIGINT FK → motivos_baja.id RESTRICT,
  auditoria_id         BIGINT FK → auditorias_inventario.id RESTRICT,
  referencia_venta_id  BIGINT,                  -- índice; la FK a ventas se agrega en la sesión 06
  usuario_id           BIGINT FK → usuarios.id RESTRICT NOT NULL,
  timestamp            TIMESTAMP NOT NULL DEFAULT now(),        -- índice
  notas                TEXT,
  CHECK ((tipo IN ('ingreso_proveedor', 'anulacion_venta') AND cantidad > 0) OR
         (tipo IN ('venta', 'baja') AND cantidad < 0) OR
         (tipo = 'ajuste_auditoria')),
  CHECK (tipo NOT IN ('venta', 'anulacion_venta') OR referencia_venta_id IS NOT NULL),
  CHECK (tipo <> 'baja' OR motivo_baja_id IS NOT NULL),
  CHECK (tipo <> 'ajuste_auditoria' OR auditoria_id IS NOT NULL)
)

auditorias_inventario (   -- conteos físicos (distinto de la tabla `auditoria`)
  id                  BIGSERIAL PK,
  usuario_id          BIGINT FK → usuarios.id RESTRICT NOT NULL,
  estado              estado_auditoria_inventario NOT NULL DEFAULT 'en_curso',
  filtro_categoria_id BIGINT FK → categorias.id RESTRICT,   -- informativo
  fecha_inicio        TIMESTAMP NOT NULL DEFAULT now(),
  fecha_fin           TIMESTAMP,
  notas               TEXT,
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now()
)
-- UNIQUE INDEX uq_auditoria_inventario_en_curso ON auditorias_inventario ((true))
--   WHERE estado = 'en_curso'   → una sola auditoría en curso a la vez

auditoria_items (
  id                BIGSERIAL PK,
  auditoria_id      BIGINT FK → auditorias_inventario.id ON DELETE CASCADE NOT NULL,
  producto_id       BIGINT FK → productos.id RESTRICT NOT NULL,
  cantidad_sistema  INTEGER NOT NULL,   -- foto del stock AL REGISTRAR el ítem
  cantidad_contada  INTEGER NOT NULL,   -- CHECK >= 0
  diferencia        INTEGER GENERATED ALWAYS AS (cantidad_contada - cantidad_sistema) STORED,
  UNIQUE (auditoria_id, producto_id)
)
```

**Permisos** (seed de la sesión 02, módulo `stock`): Admin todo; Supervisor y
Vendedor `stock` ver + recursos `stock.baja` crear y `stock.auditoria` crear.
Los ingresos y los mínimos quedan para quien tenga `stock` crear/editar
general (Admin, o un rol personalizado).

---

## BACKEND — SERVICES

### `/app/services/stock.py`
- **`aplicar_movimiento(db, autor, *, tipo, producto_id, cantidad, motivo_baja_id=None,
  auditoria_id=None, referencia_venta_id=None, notas=None, ip_origen=None)`** —
  ÚNICO camino por el que cambia `productos.stock`:
  - `cantidad` con signo y ≠ 0; el signo tiene que ser coherente con el tipo
    (el CHECK de la base lo refuerza).
  - Bloquea la fila del producto (`SELECT … FOR UPDATE`) antes de calcular.
  - Si el producto tiene `stock_infinito`, registra el movimiento pero no toca
    el stock (`stock_resultante` = stock actual).
  - Si el movimiento resta y el stock no alcanza → 409 "No hay stock suficiente
    de '<descripción>': hay N y se piden M" (ningún tipo, tampoco una venta,
    puede dejarlo negativo).
  - Guarda `stock_resultante`. No hace commit.
  - Audita `stock.<tipo>`.
- `registrar_ingreso(autor, producto_id, cantidad, notas)`: cantidad entera > 0;
  movimiento `ingreso_proveedor`. (También lo usa el `stock_inicial` del alta de
  productos.)
- `definir_minimo(producto_id, stock_minimo)` (≥ 0), audita `stock.minimo`.
- `listar_stock(busqueda (código con/sin verificador vía `condiciones_codigo`,
  SKU, descripción), categoria_id (rama), proveedor_id, solo_bajo_minimo,
  incluir_sin_stock, pagina, tamano)`: solo productos activos; excluye los de
  stock infinito salvo que se busquen por código.
- `alertas(limite)`: productos activos con `bajo_minimo`.
- `resumen()`: cantidad de productos con stock, unidades totales, valorizado a
  precio de venta (`SUM(stock × precio_venta)` con stock > 0) y cantidad bajo
  mínimo. (El valorizado a costo vive en Reportes, sesión 09.)
- `listar_movimientos(producto_id, tipo, desde, hasta, pagina, tamano)`.

### `/app/services/bajas_stock.py`
- CRUD de `motivos_baja` (nombre único, obligatorio). Auditoría
  `motivo_baja.crear/editar`.
- `registrar_baja(autor, producto_id, cantidad, motivo_baja_id, notas)`:
  cantidad entera > 0 (se guarda en negativo), motivo activo; movimiento `baja`.

### `/app/services/auditoria_inventario.py`
- `iniciar(autor, filtro_categoria_id, notas)`: una sola auditoría `en_curso` a
  la vez (409 "Ya hay un conteo en curso."). Audita `auditoria_inventario.iniciar`.
- `registrar_items(id, items[{producto_id, cantidad_contada}])`: solo en curso;
  `cantidad_sistema` se captura AL REGISTRAR; registrar de nuevo el mismo
  producto sobreescribe.
- `editar_item` / `eliminar_item` (solo en curso).
- `finalizar(autor, id)`: exige al menos un ítem; genera un `ajuste_auditoria`
  por cada ítem con diferencia ≠ 0 (cantidad = diferencia) y pasa a `cerrada`
  (no hay instancia de aprobación). Audita `auditoria_inventario.cerrar`.
- `listar(estado, desde, hasta, pagina, tamano)`.
- Reportes: `reports/auditoria_pdf.py::generar_pdf_auditoria` (planilla PDF) y
  `generar_xls_auditoria` (Excel).

---

## BACKEND — ENDPOINTS

### Stock (`/api/v1/stock`)
```
GET   ""                          → paginado StockResponse; filtros categoria_id, proveedor_id,
                                    busqueda, solo_bajo_minimo, incluir_sin_stock      [STOCK ver]
GET   /alertas?limite=            → lo que hay que reponer                            [STOCK ver]
GET   /resumen                    → números de encabezado                             [STOCK ver]
GET   /movimientos                → historial; filtros producto_id, tipo, desde, hasta  [STOCK ver]
GET   /motivos-baja?activo=&nombre=                                                   [STOCK ver]
POST  /motivos-baja                                                 [STOCK editar + stock.motivos_baja]
PUT   /motivos-baja/{id}                                            [STOCK editar + stock.motivos_baja]
POST  /ingresos                   → {producto_id, cantidad, notas}                    [STOCK crear]
POST  /bajas                      → {producto_id, cantidad, motivo_baja_id, notas}  [STOCK crear + stock.baja]
PUT   /minimos/{producto_id}      → {stock_minimo}                                    [STOCK editar]
```
`StockResponse`: producto_id, codigo (con verificador), descripcion, categoria,
proveedor, stock, stock_minimo, bajo_minimo, stock_infinito, foto_url.

### Auditorías de inventario (`/api/v1/auditorias-inventario`)
```
GET    ""                         → paginado                                    [STOCK ver]
POST   ""                         → iniciar conteo                              [STOCK crear + stock.auditoria]
GET    /{id}                      → detalle con diferencias                     [STOCK ver]
GET    /{id}/pdf                  → planilla PDF                                [STOCK ver]
GET    /{id}/xls                  → planilla Excel                              [STOCK ver]
POST   /{id}/items                → registrar lo contado                        [STOCK crear + stock.auditoria]
PATCH  /{id}/items/{item_id}      → corregir cantidad contada                   [idem]
DELETE /{id}/items/{item_id}      → quitar ítem                                 [idem]
PATCH  /{id}/finalizar            → cerrar y ajustar stock                      [idem]
```

---

## FRONTEND

Sidebar: "Gestión de Stock" (`/gestion-de-stock`, módulo STOCK). Todas las
pantallas pasan `ruta_activa="/gestion-de-stock"` y tienen "volver" al hub.
Contexto común `_contexto_stock(...)` con los flags `puede_ingresar`,
`puede_minimos`, `puede_baja`, `puede_motivos` y `puede_auditar`.

### Hub `/gestion-de-stock` (`pages/stock/hub.html`, macro `hub`)
`SECCIONES_STOCK` (filtradas con `_visible`):
| Tarjeta | Descripción | URL | Permiso |
|---|---|---|---|
| Stock | Lo que hay de cada producto, ingresos, mínimos y bajas | /stock | STOCK |
| Auditorías de Stock | Conteos de inventario y sus diferencias | /auditorias-inventario | STOCK |

### `/stock` — Stock (`pages/stock/listado.html` + `static/js/stock.js`)
- Encabezado con los números de `/stock/resumen` (productos con stock,
  unidades, valorizado, bajo mínimo) y botón "Motivos de baja"
  (→ `/motivos-baja`, si `puede_motivos`).
- Filtros: "Código, SKU o descripción", Categoría, Proveedor, switch
  "Solo bajo mínimo", "Limpiar filtros". Paginado de a 10.
- Tabla: Código, Foto, Descripción, Stock (en rojo si es negativo), Mínimo
  (+ "Reponer" si bajo mínimo); acciones:
  - **"Ingreso"** (si `puede_ingresar`): modal con cantidad y nota.
  - **"Mínimo"** (si `puede_minimos`): modal "Mínimo de reposición".
  - **"Baja"** (si `puede_baja`): modal con cantidad, motivo y nota "Qué pasó".
  - **"Movimientos"**: modal con el historial del producto (Fecha, Tipo,
    Cantidad con signo, Stock resultante, Usuario, Nota), paginado.

### `/motivos-baja` (`pages/motivos_baja/listado.html` + `static/js/motivos_baja.js`)
ABM simple: filtro Nombre y estado, alta/edición (placeholder "Rotura"),
activar/desactivar.

### `/auditorias-inventario` — Auditorías de Stock (`pages/auditorias/listado.html` + `static/js/auditorias.js`)
- "Iniciar conteo" (categoría opcional, notas); deshabilitado con el aviso
  "Ya hay un conteo en curso" si existe uno.
- Listado: Iniciada, Usuario, Estado, Ítems, acciones (continuar, PDF, Excel).
- Pantalla de conteo: buscador "Escaneá o tipeá el código" con "Código" y
  "Contadas" en la misma línea; tabla Código | Descripción | Sistema | Contado |
  Dif. con edición y eliminación de ítems; "Cerrar" con confirmación (ajusta el
  stock).

---

## TESTS (`tests/test_stock.py`, `test_bajas_stock.py`, `test_auditoria_inventario.py`)
- `productos.stock` solo cambia vía `aplicar_movimiento`; `stock_resultante`
  correcto; stock infinito no se toca.
- Baja, ajuste o venta sin stock suficiente → 409 (ningún tipo deja el stock
  negativo).
- CHECKs de signo por tipo en `movimientos_stock`.
- Una sola auditoría en curso; al cerrar genera un ajuste por diferencia ≠ 0.

---

## CRITERIOS DE ACEPTACIÓN
- `productos.stock` solo cambia vía `aplicar_movimiento`; si algo falla no queda
  ni movimiento ni cambio.
- Cada movimiento guarda el stock resultante y queda trazado con usuario y fecha.
- Una auditoría cerrada genera un `ajuste_auditoria` por cada diferencia ≠ 0;
  una sola auditoría en curso a la vez; `diferencia` es columna generada.
- El stock nunca queda negativo (tampoco por ventas).
