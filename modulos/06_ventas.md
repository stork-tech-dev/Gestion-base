# SESIÓN 06 — Clientes y Ventas
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 a 05 completadas y funcionando
- Tablas `usuarios`, `productos` (con `stock`, `costo`, `margen`) y
  `movimientos_stock` ya existentes
- `resolver_permiso`, `services.productos.buscar_por_codigo` y
  `services.stock.aplicar_movimiento` ya implementados

## OBJETIVO DE ESTA SESIÓN
Clientes (con datos fiscales para una futura facturación), configuración de
medios de pago con planes de cuotas, motivos de descuento, promociones, la
**pantalla de venta de escritorio**, la **anulación de ventas** y el hub de
Ventas con el listado "Resumen de Ventas".

## CONTEXTO DE NEGOCIO
Hay un **único punto de venta**. La venta se hace desde una PC (o cualquier
equipo con navegador) con la sesión del usuario que vende. La interfaz es de
escritorio y responsive: se usa igual sea quien sea el que vende (no hay una
versión distinta para el Vendedor). El sistema registra la venta para stock,
caja y reportes, pero **no emite comprobantes fiscales** (eso lo hace la
registradora fiscal, aparte).

Fuera de alcance (decisión de producto): **señas, puntos de cliente, cuenta
corriente, gift cards, cambios y devoluciones parciales**. Lo único que se
aplica al vender son descuentos (motivos) y promociones. Una venta confirmada
solo se puede **anular completa**.

> El turno de caja se implementa en la sesión 07. Desde entonces **confirmar
> y anular exigen un turno abierto de hoy**; mientras el módulo no exista, esa
> verificación se omite.

---

## MODELO DE DATOS (migración de esta sesión)

```sql
-- SEQUENCE ventas_numero_seq START 1
-- ENUM condicion_iva: consumidor_final, responsable_inscripto, monotributista, exento
-- ENUM tipo_promocion: dos_x_uno, tres_x_dos, porcentaje
-- ENUM tipo_alcance_promocion: producto, categoria, todos_productos, todos_categorias,
--                              medio_de_pago
-- ENUM estado_venta: en_curso, confirmada, anulada

clientes (
  id BIGSERIAL PK,
  nombre        VARCHAR(150) NOT NULL,         -- nombre o razón social
  dni           VARCHAR(15) UNIQUE,            -- índice; se guarda solo con dígitos
  cuit          VARCHAR(11) UNIQUE,            -- solo dígitos; validado con su dígito verificador
  condicion_iva condicion_iva NOT NULL DEFAULT 'consumidor_final',
  domicilio     VARCHAR(200), codigo_postal VARCHAR(10), localidad VARCHAR(100),
  telefono      VARCHAR(30),  email VARCHAR(150),
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now(),
  CHECK (condicion_iva = 'consumidor_final' OR cuit IS NOT NULL)
)
-- cuit y condicion_iva no se usan hoy en ningún cálculo: quedan cargados para
-- la futura facturación electrónica.

medios_de_pago (
  id BIGSERIAL PK,
  nombre          VARCHAR(60) UNIQUE NOT NULL,
  soporta_cuotas  BOOLEAN NOT NULL DEFAULT FALSE,
  es_efectivo     BOOLEAN NOT NULL DEFAULT FALSE,   -- el medio "efectivo" (uno solo); el arqueo lo busca por esta marca, nunca por nombre
  activo          BOOLEAN NOT NULL DEFAULT TRUE,
  created_at, updated_at,
  CHECK (NOT (es_efectivo AND soporta_cuotas))
)
-- UNIQUE INDEX uq_medios_de_pago_efectivo ON medios_de_pago ((true)) WHERE es_efectivo

planes_cuotas (
  id BIGSERIAL PK,
  medio_de_pago_id BIGINT FK → medios_de_pago.id NOT NULL,
  cuotas           SMALLINT NOT NULL,                  -- CHECK >= 1
  recargo_cliente  NUMERIC(5,2) NOT NULL DEFAULT 0,    -- % que paga el cliente (0 = sin interés), CHECK 0..100
  costo_medio      NUMERIC(5,2) NOT NULL DEFAULT 0,    -- % que cobra la terminal; SOLO reportes, CHECK 0..100
  monto_minimo     NUMERIC(10,2) NOT NULL DEFAULT 0,   -- CHECK >= 0
  activo           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at, updated_at,
  UNIQUE (medio_de_pago_id, cuotas, recargo_cliente)
)
-- PlanCuotas.disponible_para(monto): activo AND monto_minimo <= monto; .sin_interes: recargo_cliente = 0

motivos_descuento (
  id BIGSERIAL PK,
  nombre                      VARCHAR(100) UNIQUE NOT NULL,
  nota                        VARCHAR(500),            -- se muestra como tooltip
  porcentaje_sugerido         NUMERIC(5,2),            -- NULL = quien vende elige; CHECK NULL o 0<x<=100
  habilita_cuotas_sin_interes BOOLEAN NOT NULL DEFAULT FALSE,
  activo                      BOOLEAN NOT NULL DEFAULT TRUE,
  fecha_inicio DATE, fecha_fin DATE,                   -- vigencia opcional; CHECK inicio <= fin
  created_at, updated_at
)
motivo_medios_pago (   -- medios de pago en los que rige el motivo (vacío = todos)
  id BIGSERIAL PK,
  motivo_id        BIGINT FK → motivos_descuento.id ON DELETE CASCADE NOT NULL,
  medio_de_pago_id BIGINT FK → medios_de_pago.id NOT NULL,
  UNIQUE (motivo_id, medio_de_pago_id)
)

promociones (
  id BIGSERIAL PK,
  nombre               VARCHAR(100) UNIQUE NOT NULL,
  nota                 VARCHAR(500),
  tipo                 tipo_promocion NOT NULL,
  activo               BOOLEAN NOT NULL DEFAULT TRUE,
  porcentaje_descuento INTEGER,                        -- solo tipo 'porcentaje'; CHECK NULL o 1..75
  fecha_inicio DATE, fecha_fin DATE,                   -- NULL = sin límite; CHECK inicio <= fin
  created_at, updated_at
)
-- TAMANO_GRUPO = {dos_x_uno: 2, tres_x_dos: 3}; PAGAS_POR_GRUPO = {dos_x_uno: 1, tres_x_dos: 2}
-- Promocion.vigente_el(dia): activo y dentro de fechas

promocion_alcance (
  id BIGSERIAL PK,
  promocion_id  BIGINT FK → promociones.id ON DELETE CASCADE NOT NULL,
  tipo_alcance  tipo_alcance_promocion NOT NULL,
  referencia_id BIGINT NOT NULL,   -- producto/categoría/medio; 0 = "todos" en todos_* / medio
  UNIQUE (promocion_id, tipo_alcance, referencia_id)
)

cliente_promociones (   -- promociones exclusivas de ciertos clientes
  id BIGSERIAL PK,
  cliente_id   BIGINT FK → clientes.id NOT NULL,
  promocion_id BIGINT FK → promociones.id NOT NULL,
  UNIQUE (cliente_id, promocion_id)
)

ventas (
  id BIGSERIAL PK,
  numero              VARCHAR(12) UNIQUE NOT NULL,    -- 'V-000001' desde la SEQUENCE, al INICIAR
  cliente_id          BIGINT FK → clientes.id,        -- NULL = sin cliente (caso normal)
  usuario_id          BIGINT FK → usuarios.id NOT NULL,   -- índice; quien vende
  estado              estado_venta NOT NULL DEFAULT 'en_curso',   -- índice
  subtotal            NUMERIC(10,2) NOT NULL DEFAULT 0,   -- suma de precios de lista
  descuento_total     NUMERIC(10,2) NOT NULL DEFAULT 0,
  recargo_total       NUMERIC(10,2) NOT NULL DEFAULT 0,
  total               NUMERIC(10,2) NOT NULL DEFAULT 0,   -- lo que paga el cliente
  codigo_cambio       VARCHAR(8) UNIQUE,                  -- 4 caracteres, se genera al CONFIRMAR
  promocion_id        BIGINT FK → promociones.id,
  confirmada_en       TIMESTAMP,                          -- índice; NULL mientras está en_curso
  turno_id            BIGINT,                             -- índice; turno en el que se cobró (FK a turnos en la sesión 07)
  -- Anulación (una venta se anula completa, una sola vez)
  anulada_en          TIMESTAMP,
  anulada_por_id      BIGINT FK → usuarios.id,
  motivo_anulacion    VARCHAR(500),
  turno_anulacion_id  BIGINT,                             -- índice; turno que devuelve el dinero (FK en la sesión 07)
  created_at, updated_at,
  CHECK subtotal, descuento_total, recargo_total, total >= 0,
  CHECK ((estado='en_curso'   AND codigo_cambio IS NULL AND confirmada_en IS NULL AND anulada_en IS NULL) OR
         (estado='confirmada' AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL AND anulada_en IS NULL) OR
         (estado='anulada'    AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL
                              AND anulada_en IS NOT NULL AND anulada_por_id IS NOT NULL
                              AND motivo_anulacion IS NOT NULL))
)
-- Desnormalización justificada: los importes son la foto del cierre; se
-- recalculan mientras está en_curso y se congelan al confirmar.
-- turno_id / turno_anulacion_id: la caja se arquea por turno (no por franja
-- horaria), así una anulación de una venta vieja impacta en el turno actual
-- sin tocar arqueos ya cerrados.

venta_items (   -- una fila por UNIDAD (sin campo cantidad)
  id BIGSERIAL PK,
  venta_id              BIGINT FK → ventas.id ON DELETE CASCADE NOT NULL,
  producto_id           BIGINT FK → productos.id NOT NULL,
  precio_unitario       NUMERIC(10,2) NOT NULL,   -- lista con el descuento del producto
  precio_lista          NUMERIC(10,2) NOT NULL,   -- precio de venta del producto al momento de la venta
  costo_unitario        NUMERIC(12,2) NOT NULL,   -- costo EN PESOS al momento de la venta (costo × dólar del proveedor, o costo si es en pesos); para rentabilidad
  descuento_item        NUMERIC(5,2) NOT NULL DEFAULT 0,   -- % de descuento de venta
  motivo_descuento_id   BIGINT FK → motivos_descuento.id,
  porcentaje_modificado BOOLEAN NOT NULL DEFAULT FALSE,
  precio_final          NUMERIC(10,2) NOT NULL,   -- $0 si es el gratis de una promo de grupo
  en_promocion          BOOLEAN NOT NULL DEFAULT FALSE,
  orden                 SMALLINT NOT NULL,        -- orden de carga (desempate de promociones)
  CHECK precios y costo >= 0, CHECK descuento_item 0..100,
  CHECK (descuento_item = 0 OR motivo_descuento_id IS NOT NULL),
  CHECK (NOT (en_promocion AND descuento_item > 0))
)
-- Desnormalización justificada: precio_lista, precio_unitario y costo_unitario
-- son la foto del momento de la venta (el precio, el costo y el dólar cambian).

venta_pagos (
  id BIGSERIAL PK,
  venta_id          BIGINT FK → ventas.id ON DELETE CASCADE NOT NULL,
  medio_de_pago_id  BIGINT FK → medios_de_pago.id NOT NULL,
  plan_cuotas_id    BIGINT FK → planes_cuotas.id,
  monto             NUMERIC(10,2) NOT NULL,      -- CHECK > 0; antes del recargo
  recargo           NUMERIC(10,2) NOT NULL DEFAULT 0,
  monto_total       NUMERIC(10,2) NOT NULL       -- CHECK = monto + recargo
)
```

Además, en la migración:
- Se agrega la FK `fk_movimientos_stock_referencia_venta` (movimientos_stock → ventas).
- Seed de medios de pago: Efectivo (`es_efectivo`), Débito, Tarjeta de Crédito
  (con cuotas), Transferencia.
- Permisos: supervisor → `configuracion.promociones` ver/crear/editar y
  `venta.anular` eliminar.

---

## BACKEND — SERVICES

### `/app/services/clientes.py`
- `listar_clientes(...)` paginado; `buscar(texto, limite=10)`: activos, nombre
  sin tildes, DNI o CUIT por prefijo (desplegable de la pantalla de venta).
- `crear_cliente` / `editar_cliente`: nombre obligatorio; DNI y CUIT limpiados
  a dígitos y únicos ("El DNI … ya está cargado en el cliente '…'"); CUIT de
  11 dígitos con **dígito verificador válido** (`core/codigos.py::cuit_es_valido`,
  módulo 11 con pesos 5,4,3,2,7,6,5,4,3,2); si la condición IVA no es
  consumidor final, el CUIT es obligatorio.
- `cambiar_estado`.
- `ficha(cliente_id)`: datos, promociones asignadas y cantidad/total de compras
  confirmadas (no anuladas).
- Auditoría `cliente.crear/editar/activar/desactivar`.

### `/app/services/medios_pago.py`
- CRUD de medios (nombre único; un solo medio `es_efectivo`; el efectivo no
  admite cuotas) y de planes (plan único por medio + cuotas + recargo).
- `medio_efectivo()`: el medio con `es_efectivo` (lo usa la caja).
- `planes_disponibles(medio_id, monto, habilita_sin_interes)`: planes con
  `monto_minimo <= monto`; si un motivo de descuento de la venta
  `habilita_cuotas_sin_interes`, también los planes **sin interés** aunque no
  lleguen al mínimo.
- `calcular_recargo(monto, plan)` = `monto × recargo_cliente / 100` sobre la
  parte financiada, nunca sobre el total. `costo_medio` jamás entra en un cálculo
  de precio (solo en reportes).

### `/app/services/descuentos.py`
- `PORCENTAJES_VALIDOS = (5, 10, …, 50)` (de 5 en 5, sin pasar el tope).
- Tope = `configuracion_sistema.tope_descuento_venta` (seed 50), leído con
  `obtener_configuracion`; nunca un literal en el código.
- `validar_porcentaje(p)`: solo valores de la lista y ≤ tope.
- `validar_tope(desc_producto, desc_venta)`: la **suma directa** no puede pasar
  del tope ("El descuento total no puede superar el N% por producto: …").
- `calcular_descuento_total` (efectivo encadenado, para mostrar).
- `aplicar_descuentos(precio_lista, desc_producto, desc_venta, redondeo)`:
  `precio_lista × (1-dp) × (1-dv)` **encadenado**, redondeado **hacia abajo**
  (`redondear_hacia_abajo`) al múltiplo de redondeo; nunca queda en 0.
- `resolver_porcentaje(motivo, porcentaje)`: motivo activo; sin porcentaje usa el
  sugerido (si no tiene sugerido → error: hay que elegir); devuelve
  `(elegido, porcentaje_modificado)`.
- CRUD de motivos con `nota`, vigencia y medios de pago (`_sincronizar_medios`).
  **Hoy la vigencia y los medios de pago se guardan y muestran, pero no se
  validan al aplicar el descuento en una venta.**

### `/app/services/promociones.py`
- `unidades_gratis(cantidad, promo)`: solo grupos completos.
- `elegir_unidades_gratis(items, promo)`: ordena por precio unitario DESC y
  `orden` como desempate; en cada grupo completo quedan gratis las más baratas
  **del grupo** (ej. 2x1 con [100,90,80,70,60] → gratis 90 y 70).
- `productos_alcanzados(promo)`: set de producto_id (categoría incluye su rama)
  o `None` si es `todos_productos`/`todos_categorias`.
- `aplica_con_medio(promo, medio_de_pago_id)`: alcance por medio de pago (sin
  alcance de medio o 0 = todos); un medio desconocido (todavía sin pagos) no
  bloquea.
- `promociones_aplicables(cliente_id, dia)`: activas y vigentes; las
  **asignadas a algún cliente** son exclusivas: solo se ofrecen a esos clientes.
- CRUD con validación de alcances existentes, nombre único, porcentaje 1-75
  obligatorio solo para tipo `porcentaje`, fechas coherentes, alcances sin
  repetidos. `asignar_a_cliente`, `quitar_de_cliente`, `promociones_de_cliente`.

### `/app/services/ventas.py`
Constantes: número `V-{nextval:06d}`; código de cambio de **4 caracteres**
aleatorios (`secrets`) sobre el alfabeto A-Z0-9 **sin I, O, 0, 1**, con
reintento ante colisión (se anota en el ticket para identificar la venta);
`MAX_MEDIOS_DE_PAGO = 2`.

**Flujo (la venta se persiste desde que se inicia; el carrito es la venta `en_curso`):**
1. `iniciar_venta(autor)`: si el usuario ya tiene una `en_curso`, la devuelve
   (nunca dos abiertas por usuario). Audita `venta.iniciar`.
2. `agregar_item(venta, codigo | producto_id)`: una unidad por fila; el código
   se resuelve con `productos.buscar_por_codigo` (con o sin verificador; 404 si
   no existe); producto activo; si no queda stock (contando lo ya cargado en el
   carrito) devuelve un **aviso** "Sin stock de '…': controlá bien el código
   antes de continuar." **sin bloquear** (el backend no bloquea).
   `precio_lista` = `precio_venta` del producto; `precio_unitario` = lista con
   el `descuento_producto`; `costo_unitario` = costo en pesos del producto
   (`productos.costo_en_pesos`, única definición).
3. `quitar_item`, `asociar_cliente(cliente_id | None)` (cliente activo).
4. `aplicar_descuento_item(item_id, motivo_id | None, porcentaje)`: sin motivo
   = quitar descuento; no se permite en ítems en promoción; porcentaje de la
   lista; tope sumando el del producto; registra `porcentaje_modificado`.
   Audita `venta.descuento`.
5. `_recalcular(venta)` (después de cada cambio): limpia promociones, recalcula
   cada ítem, **elige automáticamente la mejor promoción** (`_mejor_promocion`:
   la de mayor ahorro entre las aplicables; empate → menor id; ninguna si no
   ahorra), aplica: grupos → ítems gratis en $0; `porcentaje` → los ítems
   alcanzados con ese % (redondeo hacia abajo). Los ítems con descuento manual
   quedan fuera de toda promoción. Calcula subtotal, descuento_total, recargo y
   total; si los pagos cargados ya no cubren el total, los borra.
   `elegir_promocion(promocion_id | None)` fija otra a mano **hasta el próximo
   cambio del carrito**.
6. `registrar_pagos(pagos[{medio_de_pago_id, monto, plan_cuotas_id?}])`:
   hasta 2; los montos deben sumar **exactamente** lo cobrable (sin recargos);
   cada monto > 0; medio activo; plan válido para ese monto (revalidado en el
   backend). El recargo se calcula por pago y se suma al total.
7. `confirmar_venta(venta)`: **exige turno abierto de hoy**
   (`services.turnos.turno_para_operar()`, sesión 07: 409 con el mensaje del
   bloqueo o "No hay un turno de caja abierto."; si el módulo todavía no
   existe, se omite), exige ítems y pagos que cubran; movimiento `venta` por
   producto (cantidad negativa; el producto queda bloqueado mientras se
   aplica y 409 si el stock ya no alcanza — la venta nunca lo deja negativo);
   genera `codigo_cambio`; sella `confirmada_en` y `turno_id`; estado
   `confirmada`. Todo en una transacción. Audita `venta.confirmada`.
8. `descartar_venta(venta)`: borra una venta `en_curso`. Audita `venta.descartar`.
9. `anular_venta(autor, venta_id, motivo)`: solo ventas `confirmada` (409 si
   está en curso o ya anulada); motivo obligatorio (1-500); **exige turno
   abierto de hoy** (igual que confirmar). En una transacción: un movimiento
   `anulacion_venta` por producto (cantidad positiva = unidades de la venta,
   `referencia_venta_id`); sella `anulada_en`, `anulada_por_id`,
   `motivo_anulacion`, `turno_anulacion_id`; estado `anulada`. Los pagos NO se
   borran: la caja los resta del turno de anulación (sesión 07). Audita
   `venta.anular` con el estado anterior y el motivo.

Solo el usuario que inició una venta `en_curso` puede operarla (403 si no).
La anulación la puede hacer cualquiera con `venta.anular`.

`listar_ventas(cliente_id, usuario_id, estado, numero, codigo_cambio,
total_desde, total_hasta, fecha_desde, fecha_hasta, …)`: carga cliente, usuario
y pagos con medio. Las fechas filtran por `confirmada_en` (o `created_at` para
las `en_curso`). `codigo_cambio` exacto, sin importar mayúsculas.

---

## BACKEND — ENDPOINTS

### Clientes (`/api/v1/clientes`)
```
GET    ""                         → paginado; filtros busqueda (nombre, DNI o CUIT), localidad,
                                    condicion_iva, activo                          [CLIENTES ver]
GET    /buscar?q=&limite=10       → sugerencias (nombre, DNI o CUIT)                [CLIENTES ver]
GET    /{id}                      → ficha: datos, promociones, resumen de compras   [CLIENTES ver]
POST   ""                                                                        [CLIENTES crear]
PUT    /{id}                                                                     [CLIENTES editar]
PATCH  /{id}/estado                                                              [CLIENTES editar]
POST   /{id}/promociones          → {promocion_id} asignar                       [CLIENTES editar]
DELETE /{id}/promociones/{promocion_id}                                          [CLIENTES editar]
```

### Configuración (`/api/v1/configuracion`)
```
GET    /medios-de-pago                         [CONFIGURACION ver]
POST   /medios-de-pago                         [CONFIGURACION editar]
PUT    /medios-de-pago/{id}                    [CONFIGURACION editar]
PATCH  /medios-de-pago/{id}/estado             [CONFIGURACION editar]
GET    /medios-de-pago/{id}/planes             [CONFIGURACION ver]
POST   /medios-de-pago/{id}/planes             [CONFIGURACION editar]
PUT    /planes-cuotas/{id}                     [CONFIGURACION editar]
PATCH  /planes-cuotas/{id}/estado              [CONFIGURACION editar]
GET    /motivos-descuento                      [CONFIGURACION ver]
POST   /motivos-descuento                      [CONFIGURACION editar]
PUT    /motivos-descuento/{id}                 [CONFIGURACION editar]
PATCH  /motivos-descuento/{id}/estado          [CONFIGURACION editar]
GET    /promociones/catalogos                  → productos, categorías, medios  [configuracion.promociones ver]
GET    /promociones                            [configuracion.promociones ver]
POST   /promociones                            [configuracion.promociones editar]
PUT    /promociones/{id}                       [configuracion.promociones editar]
PATCH  /promociones/{id}/estado                [configuracion.promociones editar]
```

### Ventas (`/api/v1/ventas`) — rutas fijas antes de `/{venta_id}`
```
GET    ""                         → paginado VentaResumen; filtros cliente_id, usuario_id, estado,
                                    numero, codigo_cambio, total_desde/hasta, fecha_desde/hasta  [VENTAS ver]
GET    /en-curso                  → {venta | null} del usuario logueado                    [VENTAS ver]
GET    /opciones-descuento        → {motivos activos, porcentajes, tope}                   [VENTAS ver]
GET    /producto?codigo=          → producto por código (id, codigo, descripcion, categoria,
                                    precio, precio_lista, stock, stock_infinito, foto)     [VENTAS ver]
GET    /productos?busqueda=&limite=8 → búsqueda por código, SKU o descripción para el
                                    desplegable de la pantalla de venta (activos; mismos
                                    campos que /producto)                                  [VENTAS ver]
GET    /{id}                      → detalle                                                [VENTAS ver]
GET    /{id}/medios-de-pago       → medios activos con los planes que habilita este monto  [VENTAS ver]
GET    /{id}/promociones          → promociones aplicables                                [VENTAS ver]
POST   ""                         → iniciar (o devolver la abierta)                       [VENTAS crear]
POST   /{id}/items                → {codigo | producto_id} → {venta, aviso}                [VENTAS crear]
DELETE /{id}/items/{item_id}                                                               [VENTAS crear]
POST   /{id}/cliente              → {cliente_id | null}                                    [VENTAS crear]
POST   /{id}/descuento            → {item_id, motivo_id | null, porcentaje?}  [VENTAS crear + venta.descuento]
POST   /{id}/promocion            → {promocion_id | null}                                  [VENTAS crear]
POST   /{id}/pagos                → {pagos: [...]}                                         [VENTAS crear]
POST   /{id}/confirmar                                                                     [VENTAS crear]
POST   /{id}/anular               → {motivo}                           [VENTAS eliminar + venta.anular]
DELETE /{id}                      → descartar venta en curso                               [VENTAS crear]
```
`VentaResumen` incluye número, fecha (`confirmada_en` o `created_at`), usuario,
cliente, subtotal, descuento_total, total, código de cambio, estado, los
medios de pago usados y, si está anulada, `anulada_en`, quién y el motivo.
`costo_unitario` **no** se expone en la pantalla de venta (solo en Reportes).

---

## FRONTEND

Todo es de escritorio y responsive (breakpoints `sm`/`lg`/`xl` de la sesión 01),
dentro del layout `base.html` con sidebar y header. No hay layout mobile propio
ni routing distinto según el rol o el equipo.

### Hub `/ventas` (`pages/ventas/hub.html`, macro `hub`)
Sidebar "Ventas" (módulo VENTAS). Tarjetas `SECCIONES_VENTAS` con `title`
explicativo:
- **Nueva venta** — "Cargar productos, aplicar descuentos y cobrar" →
  `/ventas/nueva` (requiere VENTAS crear). Si el usuario tiene una venta
  `en_curso`, la tarjeta dice "Continuar venta V-000123".
- **Resumen de Ventas** — "Ventas del período con subtotal, descuento, total y
  medio de pago" → `/ventas/resumen-ventas`.

### `/ventas/nueva` — Pantalla de venta (`pages/ventas/nueva.html` + `static/js/venta.js`)
Encabezado "Nueva venta" (con el número si ya existe) y volver a "Ventas".
Al entrar consulta `GET /ventas/en-curso` y retoma la venta abierta si la hay.
Aviso arriba (sesión 07) si hay un turno bloqueante (mensaje del backend) o si
no hay turno abierto ("No hay un turno de caja abierto: no vas a poder
confirmar la venta." con link a `/caja`). Se puede armar el carrito igual;
el botón "Confirmar venta" queda deshabilitado mientras no haya turno.

Layout en dos columnas desde `lg` (una sola columna, apiladas, por debajo):

**Columna izquierda — Productos**
- Buscador "Código, SKU o descripción" con foco automático (**F2** lo enfoca
  desde cualquier lugar). Enter con un código de etiqueta (lector o tipeo)
  agrega directo; texto libre abre un desplegable (`/ventas/productos`,
  debounce 300 ms, navegación con flechas/Enter/Escape) con foto, código,
  descripción, precio y stock (en rojo si es 0). **Sin stock (y sin stock
  infinito) el producto aparece deshabilitado** y no se puede agregar desde la
  pantalla; el aviso del backend, si llega, se muestra como toast.
  Al agregar, inicia la venta si hace falta (`POST /ventas`) y hace
  `POST /ventas/{id}/items`.
- Tabla del carrito (una fila por unidad): Foto, Código, Descripción, Precio
  (lista tachada si cambió), Descuento ("X% · Motivo" o "Promo"), Final,
  acciones Descuento (si `puede_descontar` y el ítem no está en promoción) y
  Quitar. Carrito vacío: "Escaneá o buscá un producto para empezar."
- Descuento por ítem en un popover: "Elegí un motivo" y, solo si el motivo no
  tiene sugerido, lista de porcentajes; "Aplicar" / "Quitar descuento".

**Columna derecha — Cobro** (tarjeta fija al hacer scroll desde `lg`)
- **Cliente** opcional: "DNI, CUIT o nombre" (`/clientes/buscar`), muestra
  nombre y condición IVA; "Quitar". Link "+ Nuevo cliente" que abre el alta
  rápida (mismo formulario de `/clientes`) y lo asocia al guardar.
- **Promoción**: la aplicada automáticamente y un select para elegir otra de
  las aplicables o "Sin promoción".
- **Medios de pago** (hasta 2): "Elegí un medio", Monto (el segundo se completa
  con el resto), "Plan de cuotas" con los planes que habilita el monto o "Un
  pago".
- Totales: Subtotal, Descuentos y promociones, Recargo por cuotas, **Total**.
- Botones **"Confirmar venta"** (**F10**; hace `POST /pagos` + `POST /confirmar`)
  y "Descartar venta" (**ESC** pide confirmación con `modal_confirmacion`).

**Venta confirmada**: modal con el **Código de cambio** (grande, para anotar en
el ticket) y el Total cobrado; botón "Nueva venta" (limpia la pantalla y
enfoca el buscador) y "Ir al resumen".

### `/ventas/resumen-ventas` — Listado (`pages/ventas/listado.html` + `static/js/ventas.js`)
Tabla de alto volumen: filtros con botón **"Buscar"** explícito y "Limpiar
filtros": Número ("V-000123"), Código de cambio, Estado (Todos / En curso /
Confirmada / Anulada), Fecha desde/hasta (**por defecto, el día actual**),
Vendedor (combobox "Todos"). Paginado de a 10 ("Anterior"/"Siguiente").
Columnas: Número, Fecha, Vendedor, Cliente, Subtotal, Descuento, Total, Medio de
pago, Código de cambio, Estado (Anulada en rojo, con el total tachado).
Detalle en modal: Productos, "Subtotal (precios de lista)", "Descuentos y
promociones", "Recargo por cuotas", Medios de pago ("Todavía sin cobrar." si no
hay) y, si está anulada, "Anulada el … por … — Motivo: …".
Si la venta está confirmada y el usuario tiene `venta.anular`, botón rojo
**"Anular venta"**: pide el motivo (obligatorio) y confirma con
`modal_confirmacion` ("Se devuelve el stock y el importe sale de la caja del
turno actual. No se puede deshacer.").

### Catálogos de configuración (registrados en bucle `_CATALOGOS_VENTAS`, dentro del hub Configuraciones)
- **`/medios-de-pago`** (`medios_pago/listado.html` + `medios_pago.js`): filtros
  Nombre y "Cuotas (todos) / Con cuotas / Sin cuotas"; medios con marcas
  "Cuotas" / "Efectivo"; formulario con "Se cobra en cuotas" y "Es el
  efectivo de la caja"; planes por medio con columnas Cuotas, Recargo al
  cliente, Costo del medio, Monto mínimo, Estado.
- **`/motivos-descuento`** (`motivos_descuento/listado.html` + `motivos_descuento.js`):
  filtros Nombre, "Cuotas sin interés (todos) / Las habilita / No las habilita",
  estado. Columnas Nombre (con tooltip de la nota), % sugerido, Cuotas sin
  interés, Estado. Formulario: nombre ("Cumpleaños"), nota, % sugerido o "Que lo
  elija quien vende", "Habilita cuotas sin interés", Vigencia desde/hasta ("Sin
  fechas: vigencia indefinida.") y Medios de pago ("Todos los medios de pago").
- **`/promociones`** (`promociones/listado.html` + `promociones.js`, recurso
  `configuracion.promociones`): filtros Nombre, "Tipo (todos)", "Vigencia (todas) /
  Rige hoy / No rige hoy", estado. Columnas Nombre (tooltip de nota), Tipo,
  Alcance, Vigencia, Estado. Formulario: nombre ("2x1 Plata"), nota, tipo ("2x1 —
  por cada 2, la más barata es $0", "3x2 — …", "% Porcentaje — descuento fijo
  sobre precio", 1–75 %), vigencia ("Vacío = sin límite."), alcance: Producto /
  Categoría (camino completo) / "Todos los productos" / "Todas las categorías",
  y Medios de pago ("Todos los medios de pago").

### `/clientes` (`clientes/listado.html` + `static/js/clientes.js`) — ítem propio del sidebar
Filtros "Nombre, DNI o CUIT" y Localidad (tiempo real), Condición IVA, estado,
"Limpiar filtros"; paginado. Columnas Nombre, DNI, CUIT, Condición IVA,
Localidad, Teléfono, Estado. Formulario: Nombre o razón social ("Leandra
Carballo"), DNI ("39059158"), Condición IVA (default Consumidor final), CUIT
("20390591581"; obligatorio si no es consumidor final), Domicilio, Código
postal, Localidad, Teléfono, Email. Ficha: datos, cantidad y total de compras,
link "Ver compras" (→ resumen de ventas filtrado por el cliente) y
Promociones asignadas (asignar/quitar).

---

## TESTS (`test_clientes.py`, `test_medios_pago.py`, `test_descuentos.py`,
`test_promociones.py`, `test_ventas.py`, `test_anulacion.py`)
- CUIT: dígito verificador, obligatorio fuera de consumidor final, único.
- Un solo medio `es_efectivo`; el efectivo no admite cuotas.
- Descuentos encadenados con FLOOR; tope leído de `configuracion_sistema`.
- Promociones 2x1/3x2 (grupos completos, la más barata del grupo), mejor
  promoción automática, exclusivas por cliente.
- Venta completa sin cliente; nunca dos `en_curso` por usuario; pagos que
  suman exacto; recargo solo sobre lo financiado; `costo_unitario` congelado.
- Confirmar sin turno abierto de hoy → 409 (una vez existe la sesión 07).
- Anular: solo confirmadas, motivo obligatorio, reingresa stock con
  `anulacion_venta`, sella `turno_anulacion_id`, no se anula dos veces, 403 sin
  `venta.anular`.

---

## CRITERIOS DE ACEPTACIÓN
- Una venta sin cliente se completa sin errores; nunca hay dos ventas `en_curso`
  del mismo usuario.
- La pantalla de venta funciona igual para Admin, Supervisor y Vendedor (solo
  cambian los permisos, p. ej. descontar).
- Agregar un producto o subir su cantidad nunca puede superar el stock
  (bloqueante, 409 en la API); la pantalla no ofrece agregarlo desde el
  buscador si ya no queda stock.
- Descuentos: solo de la lista (5 en 5 hasta el tope), con motivo; tope
  (`tope_descuento_venta`) sumando el del producto; cálculo encadenado con
  redondeo hacia abajo; `porcentaje_modificado` registrado; nunca sobre ítems
  en promoción.
- 2x1/3x2 regalan la más barata de cada grupo completo; el sobrante se cobra; se
  aplica sola la promoción de mayor ahorro; las exclusivas solo para sus clientes.
- Recargo solo sobre la parte financiada; `costo_medio` nunca afecta el precio.
- Los pagos deben sumar exactamente lo cobrable; máximo 2 medios.
- Confirmar exige turno abierto de hoy, descuenta stock (nunca lo deja
  negativo: 409 si otro vendió en el medio), congela el costo de cada unidad
  y genera un código de cambio único de 4 caracteres sin I/O/0/1, todo atómico.
- Anular devuelve el stock, deja la venta `anulada` con motivo y usuario, y su
  importe se resta en la caja del turno en que se anuló; los arqueos cerrados
  no cambian.
- No existen señas ni puntos en ninguna tabla, endpoint ni pantalla.
- F2, F10 y ESC funcionan en la pantalla de venta.
