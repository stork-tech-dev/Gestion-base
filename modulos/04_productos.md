# SESIÓN 04 — Productos, Categorías, Códigos, Fotos y Etiquetas
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01, 02 y 03 completadas y funcionando
- `configuracion_sistema` (redondeo, descuento_maximo) y
  `proveedores` (con `moneda` y `dolar_actual`) ya existentes

## OBJETIVO DE ESTA SESIÓN
Catálogo de productos: árbol de categorías de hasta 5 niveles, productos,
generación de SKU y código de barras con dígito verificador, precio de venta en
pesos derivado del costo (en pesos o en dólares, según el proveedor) y del
margen del producto,
fotos (subida o webcam) y PDF de etiquetas para la impresora Zebra GC420t.

## CONTEXTO DE NEGOCIO
**No existen variantes.** Cada artículo vendible es un producto con su propio
código, precio, stock y fotos. Si un mismo artículo viene en dos colores o
talles, se da de alta dos veces con una descripción que los distinga (ej.
"Remera lisa roja" y "Remera lisa azul").

---

## MODELO DE DATOS

```sql
categorias (
  id          BIGSERIAL PK,
  nombre      VARCHAR(150) NOT NULL,          -- índice
  nivel       SMALLINT NOT NULL,              -- CHECK 1..5 (NIVEL_MAXIMO = 5); desnormalizado a propósito
  parent_id   BIGINT FK → categorias.id ON DELETE RESTRICT,   -- índice; NULL solo en nivel 1
  orden       SMALLINT NOT NULL DEFAULT 0,
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now(),
  CHECK ((nivel = 1 AND parent_id IS NULL) OR (nivel > 1 AND parent_id IS NOT NULL))
)
-- UNIQUE INDEX uq_categorias_hermanos (parent_id, nombre) NULLS NOT DISTINCT

-- ENUM temporada_producto: 'atemporal', 'otoño_invierno', 'primavera_verano'
-- SEQUENCE productos_sku_seq START 1   (correlativo del SKU; nunca MAX()+1)
productos (
  id                 BIGSERIAL PK,
  sku                VARCHAR(5) UNIQUE NOT NULL,     -- 'AA001'..'ZZ999', generado
  verificador        VARCHAR(1) NOT NULL,            -- módulo 11 sobre el SKU: '0'-'9' o 'X'; congelado
  sku_proveedor      VARCHAR(30),                    -- índice; opcional
  descripcion        TEXT NOT NULL,                  -- inicial en mayúscula
  categoria_id       BIGINT FK → categorias.id ON DELETE RESTRICT NOT NULL,
  proveedor_id       BIGINT FK → proveedores.id ON DELETE RESTRICT NOT NULL,
  costo              NUMERIC(10,2) NOT NULL,         -- CHECK > 0. En la moneda del proveedor
  margen             NUMERIC(6,2) NOT NULL,          -- % sobre el costo; CHECK 0..1000. Alta: default de configuracion_sistema.margen_default
  precio_venta       NUMERIC(10,2) NOT NULL,         -- CHECK >= 0. En pesos. Desnormalizado (ver abajo)
  descuento_producto NUMERIC(5,2) NOT NULL DEFAULT 0,   -- CHECK 0..100
  peso_gramos        NUMERIC(8,2),                   -- CHECK NULL o > 0
  temporada          temporada_producto NOT NULL DEFAULT 'atemporal',  -- índice
  ubicacion_deposito VARCHAR(100),                   -- dónde está guardado (texto libre)
  stock_infinito     BOOLEAN NOT NULL DEFAULT FALSE, -- no descuenta stock al vender; solo Admin
  activo             BOOLEAN NOT NULL DEFAULT TRUE,  -- índice
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now()
)
-- INDEX ix_productos_descripcion_lower ON productos (lower(descripcion))  → orden alfabético
-- UNIQUE INDEX uq_productos_descripcion_por_categoria_y_proveedor ON productos
--   (lower(translate(descripcion, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')), categoria_id, proveedor_id)
-- (En la sesión 05 se agregan `stock` y `stock_minimo`.)

producto_fotos (
  id           BIGSERIAL PK,
  producto_id  BIGINT FK → productos.id ON DELETE CASCADE NOT NULL,   -- índice
  url          VARCHAR(255) NOT NULL,
  es_principal BOOLEAN NOT NULL DEFAULT FALSE,
  orden        SMALLINT NOT NULL DEFAULT 0,           -- CHECK >= 0
  created_at   TIMESTAMP NOT NULL DEFAULT now()
)
-- UNIQUE INDEX uq_producto_fotos_principal (producto_id) WHERE es_principal
```

**Moneda del costo:** `costo` está en la moneda del proveedor
(`proveedores.moneda`). Como el proveedor de un producto no se edita y la
moneda de un proveedor con productos no se puede cambiar (sesión 03), la moneda
del costo es siempre la misma durante la vida del producto. El modelo
expone la propiedad `moneda` (la del proveedor).

**Desnormalizaciones justificadas (comentarlas en el modelo):**
- `productos.precio_venta` (siempre en pesos):
  `costo × factor × (1 + margen / 100)`, redondeado **hacia arriba** (CEIL) al
  múltiplo `configuracion_sistema.redondeo` (`redondear_hacia_arriba`), donde
  `factor` = `dolar_actual` del proveedor si es en **dólares**, o `1` si es en
  **pesos**. Se recalcula en cascada cuando cambia el dólar del proveedor y
  al editar el costo o el margen.
- `categorias.nivel`.

**Propiedades del modelo `Producto`**: `codigo_con_verificador`, `moneda`,
`foto_principal_url` (principal → primera por orden → None) y
`costo_en_pesos` (`costo × dolar_actual` si el proveedor es en dólares, o
`costo`; redondeado a 2 decimales, sin CEIL: lo congela la venta para la
rentabilidad).

---

## CÓDIGOS — `/app/core/codigos.py` (funciones puras)

- **SKU**: `codificar_sku(n)` convierte el correlativo de la SEQUENCE en 2 letras
  + 3 dígitos: 1 → `AA001`, 999 → `AA999`, 1000 → `AB001`, máximo 675.324 →
  `ZZ999`. `decodificar_sku(sku)` es el inverso. `CodigoInvalido` si se agota.
- **Dígito verificador módulo 11** `digito_verificador(codigo)`: alfabeto base36
  (dígitos = su valor, letras desde 10), ponderación por posición desde la
  derecha con pesos 2..7 cíclicos; resto 0 → '0', 10 → 'X', si no `11 - resto`.
  `codigo_es_valido(codigo_con_verificador)` valida lo tipeado/escaneado.
- El **código del producto es el SKU** (no lleva prefijo). El verificador se
  calcula una sola vez al crear el producto y nunca se recalcula. El código de
  etiqueta es `sku + verificador` (ej. `AB123` + `X` → `AB123X`).
- El **Code128** codifica `sku + verificador`; su checksum módulo
  103 lo agrega la librería `python-barcode` y no se persiste.
- **CUIT** `cuit_es_valido(cuit)`: 11 dígitos, verificador módulo 11 con pesos
  5,4,3,2,7,6,5,4,3,2 sobre los 10 primeros; `v = 11 - (suma % 11)`; si
  `v = 11` → 0; si `v = 10` → CUIT inválido; si no, `v` debe coincidir con el
  último dígito. Vive acá porque es una
  función pura de códigos; la usa Clientes (sesión 06).

---

## BACKEND — SERVICES

### `/app/services/categorias.py`
- `listar_categorias(nombre, nivel, parent_id)`, `arbol()` (una sola query,
  jerarquía en memoria, orden nivel/orden/nombre), `rama_de_ids(id)` (la
  categoría y todos sus descendientes: los filtros por categoría son por rama).
- `crear_categoria(nombre, parent_id, orden)`: nivel = padre + 1, máximo 5;
  nombre único entre hermanos.
- `editar_categoria`, `mover_categoria(nuevo_parent_id)`: no puede ser su propio
  padre ni moverse dentro de su rama; la rama entera tiene que entrar en 5 niveles.
- `eliminar_categoria`: no si tiene subcategorías ni productos.
- Auditoría `categoria.crear/editar/mover/eliminar`.

### `/app/services/productos.py`
- `calcular_precio_venta(costo, margen, proveedor)`: la fórmula de arriba
  (única definición; la usan alta, edición, recálculo, preview e importación).
- `recalcular_precios_de_proveedor(proveedor_id)`: recalcula los productos del
  proveedor (la llama el service de proveedores en cada cambio real de dólar;
  para un proveedor en pesos no hace nada).
- `crear_producto(...)`: valida categoría existente, proveedor existente y
  **activo**, descripción obligatoria (normalizada y con inicial en mayúscula
  vía `capitalizar_inicial`), descripción única por categoría y proveedor
  (sin tildes ni mayúsculas, incluye inactivos; mensaje: "Ya existe un producto
  con esa descripción en este proveedor y categoría: <SKU>[, que está inactivo y
  se puede volver a activar]. Si es el mismo artículo en otro color o talle,
  cargalo como otro producto con una descripción que lo distinga."), precio
  base > 0, peso > 0, descuento entre 0 y `descuento_maximo`, `stock_infinito`
  solo Admin (403 "El stock infinito lo define el Admin"; solo si el valor
  CAMBIA). Genera SKU y verificador, y calcula el precio de
  venta. Si llega `stock_inicial` > 0, registra un ingreso de proveedor
  (sesión 05).
- `editar_producto(...)`: SKU, verificador y proveedor NO se editan;
  recalcula el precio de venta si cambia `costo` o `margen`. Auditoría con
  costo, margen y precio de venta antes/después.
- `cambiar_estado_producto(activo)`.
- `condiciones_codigo(texto)`: ILIKE parcial sobre `sku` y, si el texto trae
  un dígito verificador válido (SKU de 5 caracteres + verificador), también
  match EXACTO sin él.
  Única definición; la reusan stock y ventas.
- `buscar_por_codigo(codigo)`: acepta la etiqueta con verificador válido o el
  código sin verificador; `NoEncontrado` si no existe.
- `listar_productos(busqueda, categoria_id (rama), proveedor_id, temporada,
  activo, stock_cero, precio_desde, precio_hasta, pagina, tamano)`: `busqueda`
  = código de etiqueta (SKU con o sin verificador, vía `condiciones_codigo`),
  SKU del proveedor o parte de la descripción; `stock_cero` (a partir de la
  sesión 05) = `stock <= 0` y no stock infinito; precio sobre `precio_venta`;
  orden por `lower(descripcion)` y SKU.
- `buscar_similares(descripcion, categoria_id, proveedor_id, limite=8)`: a partir
  de 10 caracteres; exige TODAS las palabras de 3+ letras (sin tildes, ILIKE),
  acotado a la rama de categoría y al proveedor; incluye inactivos.
- `barcode_svg(producto_id)` y `barcode_svg_para_etiqueta(producto_id)` (SVG sin
  texto, `module_width 0.2`, `module_height 4.0`, forzado a 16mm × 4.5mm).
- Auditoría `producto.crear/editar/activar/desactivar`.

### `/app/services/producto_fotos.py`
- Hasta **5 fotos por producto**.
- Máximo 5 MB; el formato se detecta por **firma de bytes** (JPG, PNG, WEBP), no
  por extensión ni Content-Type.
- Se guardan en `{UPLOADS_DIR}/productos/` con nombre `<sku>_<uuid12>.<ext>`
  y URL `/uploads/productos/...` (volumen persistente, sesión 01). Borrar la
  foto borra también el archivo.
- La primera foto queda principal; marcar una desmarca la anterior; si se
  borra la principal, la más antigua que queda toma su lugar.
- Auditoría `producto.foto_subir`, `producto.foto_principal`, `producto.foto_eliminar`.

### `/app/reports/etiquetas_pdf.py` + `templates/reports/etiquetas.html`
PDF (WeasyPrint, vía `app/reports/pdf.py::imprimir`) para Zebra GC420t que se
abre en el navegador y se imprime desde el diálogo del sistema:
- **rectangular**: plancha `@page 105mm × 10mm`, 3 etiquetas de 33mm × 10mm con
  3mm de separación, por renglón.
- **colita**: `@page 66mm × 11mm`, cola izquierda de 33mm + impresión derecha de
  33mm, una por página.
Cada etiqueta: barcode SVG + texto del código con verificador. No se guarda en disco.

---

## BACKEND — ENDPOINTS

### Categorías (`/api/v1/categorias`)
```
GET    ""                 → lista plana; filtros nombre, nivel (1-5), parent_id   [PRODUCTOS ver]
GET    /arbol             → árbol completo                                         [PRODUCTOS ver]
GET    /{id}                                                                        [PRODUCTOS ver]
POST   ""                 → alta (201)                                              [PRODUCTOS crear]
PUT    /{id}              → editar                                                  [PRODUCTOS editar]
PATCH  /{id}/mover        → {parent_id}                                             [PRODUCTOS editar]
DELETE /{id}                                                                        [PRODUCTOS eliminar]
```

### Productos (`/api/v1/productos`) — rutas fijas antes de `/{producto_id}`
```
GET    ""                          → paginado (ProductoResponse)                    [PRODUCTOS ver]
GET    /precio-preview?proveedor_id=&costo=&margen=
                                   → {moneda, dolar_proveedor | null, precio_venta}  [PRODUCTOS ver]
GET    /similares?descripcion=&categoria_id=&proveedor_id=  → [{id, sku, descripcion, activo}]  [PRODUCTOS ver]
GET    /por-codigo?codigo=         → producto (con o sin verificador); 404 si no existe  [PRODUCTOS ver]
GET    /{id}                       → detalle con fotos                              [PRODUCTOS ver]
POST   ""                          → alta (201)                                     [PRODUCTOS crear]
PUT    /{id}                       → edición                                        [PRODUCTOS editar]
PATCH  /{id}/estado                → {activo}                                       [PRODUCTOS editar]
GET    /{id}/barcode               → image/svg+xml                                  [PRODUCTOS ver]
POST   /{id}/fotos                 → multipart `archivo` (201)                      [PRODUCTOS editar]
PATCH  /fotos/{foto_id}/principal                                                   [PRODUCTOS editar]
DELETE /fotos/{foto_id}            → 204                                            [PRODUCTOS editar]
POST   /etiquetas                  → {items: [{producto_id, cantidad>0}],
                                      tipo: 'rectangular'|'colita'} → PDF inline    [PRODUCTOS ver]
```
`ProductoCrear`: categoria_id, proveedor_id, costo (>0), margen (opcional;
default `margen_default`), descripcion,
sku_proveedor, descuento_producto, peso_gramos, temporada, ubicacion_deposito,
stock_infinito, stock_inicial (entero ≥ 0). `ProductoResponse`: todos los
campos del producto + `codigo_con_verificador`, `moneda`, `categoria` (con
camino), `proveedor {id, nombre, moneda}`, `foto_url` y, desde la sesión 05,
`stock`, `stock_minimo` y `bajo_minimo`. Errores de validación 422 se muestran
marcando el campo correspondiente en el formulario.

---

## FRONTEND

Sidebar: ítem "Productos" (`/productos`, módulo PRODUCTOS).

Formato de precios: los montos en pesos con `pesos()`; el costo se
muestra con su moneda (`$ ` + `pesos()` o `US$ ` + `formatearDolar()`).

### `/productos` — Listado (`pages/productos/listado.html` + `static/js/productos.js`)
- Encabezado "Productos" con botones "Categorías" (→ `/categorias`) y "+ Crear nuevo".
- Filtros en tiempo real: texto "Código, SKU o descripción" (debounce 400 ms),
  Categoría, Proveedor y Temporada como **combobox con búsqueda**
  (`components/combobox.html`, categoría mostrada como camino completo con
  `rutaCategoria`), "Limpiar filtros", switch de estado (activos/inactivos) y
  toggle **"Stock 0"**.
- Tabla (una fila por producto, paginada de a 10): [checkbox, solo con Stock 0],
  Código (SKU + verificador, con leyenda "+ dígito verificador"),
  Foto (miniatura), Descripción, Categoría (camino), Proveedor, Stock
  (resaltado si `bajo_minimo`), Costo (con su moneda), Margen %, Precio de venta
  (pesos). Acciones: Ver, Editar, Desactivar/Activar (con confirmación).
- Con "Stock 0" activo aparecen checkboxes y el botón rojo
  **"Desactivar seleccionados"** (desactivación masiva llamando
  `PATCH /productos/{id}/estado` por cada seleccionado).
- **Ficha del producto** (modal): título, código con verificador, datos del
  producto, fotos con "Subir foto" y "Tomar foto" (webcam,
  `window.webcamCapture()`), marcar principal y borrar; stock; y
  **Imprimir etiquetas** con "Cant:" y botones "Rectangular" / "Con colita"
  (abren el PDF).

### Formulario de producto — macro `components/producto_form.html` + `static/js/producto_form.js`
`producto_form_modal(es_admin, nivel_maximo, mostrar_stock_inicial=true)`:
- **Categoría**: un select por nivel (hasta `NIVEL_MAXIMO`), cada uno aparece al
  elegir el anterior; hay que llegar al último nivel de la rama ("Elegí hasta el
  último nivel: la categoría del producto es la del final de la rama.").
- Proveedor (combobox que muestra la moneda de cada uno; no editable en la
  edición), SKU proveedor.
- Descripción con **desplegable de parecidos** (`/productos/similares`,
  debounce 300 ms, navegación con flechas/Enter/Escape, marca los inactivos);
  elegir uno adopta su nombre; aviso si hay duplicado exacto. Ayuda: "Si el
  artículo viene en varios colores o talles, cargá un producto por cada uno."
- **Costo**: la etiqueta depende de la moneda del proveedor elegido
  ("Costo en dólares (US$)" o "Costo en pesos ($)"). **Margen %** precargado
  con `margen_default`. Debajo, siempre, el preview "Precio de venta: $ …"
  (`/productos/precio-preview`, debounce 300 ms). Hasta elegir proveedor, costo
  y margen están deshabilitados.
- Peso (g), Descuento %, Temporada, Ubicación en depósito.
- "Stock infinito (no descuenta al vender)" solo visible para el Admin.
- Foto inicial (subir o webcam) y **Stock inicial** (solo enteros, `Math.trunc`)
  en el alta.
- Botones "Crear" (alta) o "Finalizar" (edición). Los errores 422 del backend
  marcan el campo. Solo se cierra con la X.

### `/categorias` — Árbol (`pages/categorias/arbol.html` + `static/js/categorias.js`)
Encabezado "Categorías" con volver a "Productos". Árbol colapsable con alta de
raíz y de hijas, edición, mover y eliminar; filtros Nombre y Nivel con
"Limpiar filtros".

---

## TESTS
`test_codigos.py` (SKU, módulo 11, código de etiqueta), `test_categorias.py`
(niveles, hermanos, mover, eliminar), `test_productos.py` (alta con código y
verificador; precio de venta con margen y CEIL para proveedor en dólares y en
pesos; recálculo por cambio de dólar, costo o margen; duplicados; stock infinito
solo Admin; búsqueda por código con verificador), `test_producto_fotos.py`
(tope de 5, firma de bytes, una sola principal).

---

## CRITERIOS DE ACEPTACIÓN
- No hay variantes: cada producto tiene un único código, precio y juego de fotos.
- SKU correlativo por SEQUENCE; SKU y verificador congelados.
- Buscar `AB123` + verificador correcto encuentra exactamente ese producto; un
  verificador incorrecto no lo resuelve por código.
- Precio de venta = costo × (dólar del proveedor, o 1 si es en pesos) ×
  (1 + margen), redondeado hacia arriba al múltiplo de redondeo.
- Cambiar el dólar de un proveedor recalcula sus productos; cambiar costo o
  margen recalcula ese producto.
- Las fotos viven en `/uploads` y sobreviven a un rebuild del contenedor.
- No se pueden cargar dos productos con la misma descripción (sin tildes ni
  mayúsculas) en el mismo proveedor y categoría.
- Descuento del producto ≤ `descuento_maximo`; stock infinito solo Admin.
- Máximo 5 fotos por producto; una sola principal.
- Las etiquetas salen en PDF con el tamaño exacto de cada tipo.
