# SESIÓN 03 — Proveedores, Valor del Dólar y Hub de Configuraciones
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 y 02 completadas y funcionando
- Tabla `usuarios` y sistema de permisos (`resolver_permiso`) ya existentes

## OBJETIVO DE ESTA SESIÓN
1. Módulo completo de proveedores, cada uno con su **moneda** (pesos o
   dólares). Para los proveedores en dólares: valor del dólar propio, su
   historial y el cambio masivo (por valor, porcentaje o Excel).
2. **Hub de Configuraciones** (página de tarjetas).

Es prerequisito de Productos: el precio de venta se calcula a partir de la
moneda del proveedor.

## CONTEXTO DE NEGOCIO
Cada producto se compra a un proveedor. Un proveedor vende **en pesos** o
**en dólares**:
- **Pesos (`ars`)**: los costos de sus productos se cargan en pesos. No tiene
  valor de dólar.
- **Dólares (`usd`)**: los costos de sus productos se cargan en dólares y se
  pasan a pesos con el valor de dólar propio de ese proveedor (y después se
  les aplica el margen: ver sesión 04).

Si ningún proveedor vende en dólares, el sistema funciona íntegramente en pesos
y toda la interfaz del dólar queda oculta (ver Frontend).

---

## PARTE 1 — PROVEEDORES

### Modelo de datos

```sql
-- ENUM estado_proveedor: 'activo', 'desactivado', 'inhabilitado'
--   (3 estados en lugar de un booleano: 'desactivado' se reactiva libremente,
--    'inhabilitado' solo con Admin)
-- ENUM moneda: 'ars', 'usd'
-- ENUM origen_cambio_dolar: 'manual', 'masivo_valor', 'masivo_porcentaje', 'importacion_excel'

proveedores (
  id            BIGSERIAL PK,
  nombre        VARCHAR(200) NOT NULL,           -- índice ix_proveedores_nombre
  pais          VARCHAR(200),
  provincia     VARCHAR(255),
  telefono      VARCHAR(50),
  email         VARCHAR(255),
  notas         TEXT,
  estado        estado_proveedor NOT NULL DEFAULT 'activo',   -- índice
  moneda        moneda NOT NULL DEFAULT 'ars',   -- índice
  dolar_actual  NUMERIC(10,2),                   -- solo proveedores en dólares
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now(),
  CONSTRAINT ck_proveedores_moneda_dolar CHECK (
    (moneda = 'ars' AND dolar_actual IS NULL) OR
    (moneda = 'usd' AND dolar_actual IS NOT NULL AND dolar_actual > 0)
  )
)
-- El modelo expone las propiedades `activo` = (estado == 'activo') y
-- `en_dolares` = (moneda == 'usd').

-- Append-only: triggers trg_proveedor_dolar_no_update / trg_proveedor_dolar_no_delete
-- (función proveedor_dolar_bloquear_modificacion()).
proveedor_dolar_historial (
  id              BIGSERIAL PK,
  proveedor_id    BIGINT FK → proveedores.id ON DELETE CASCADE NOT NULL,  -- índice
  valor_anterior  NUMERIC(10,2) NOT NULL,
  valor_nuevo     NUMERIC(10,2) NOT NULL,
  usuario_id      BIGINT FK → usuarios.id ON DELETE RESTRICT NOT NULL,
  origen          origen_cambio_dolar NOT NULL,
  timestamp       TIMESTAMP NOT NULL DEFAULT now()                         -- índice
)
```

No hay CUIT, dirección ni contacto: los datos del proveedor son nombre, país,
provincia, teléfono, email, notas y moneda.

### Services (`/app/services/proveedores.py`)

**Listado** `listar_proveedores(nombre, email, telefono, provincia, pais, estado,
moneda, dolar_desde, dolar_hasta)`: tabla chica, **sin paginación**, orden por
nombre. `nombre`, `email`, `telefono` con ILIKE; `provincia` y `pais` con ILIKE
**insensible a tildes** (`sin_tildes_sql(col).ilike(sin_tildes(valor))`).
Los filtros de dólar solo alcanzan a proveedores en dólares.

`hay_proveedores_en_dolares()` → bool (existe al menos un proveedor **activo**
con `moneda = 'usd'`). Lo usa el frontend para mostrar u ocultar la interfaz
del dólar.

**Alta / edición**
- Nombre obligatorio; moneda obligatoria (default `ars`).
- Alta en `usd`: exige `dolar_actual` > 0. Alta en `ars`: `dolar_actual` se
  ignora y queda NULL.
- La edición NO toca el valor del dólar (tiene su endpoint propio).
- **Cambio de moneda** en la edición: solo si el proveedor **no tiene
  productos** (activos o inactivos; la tabla `productos` se consulta solo si
  existe, con `to_regclass`, porque llega en la sesión 04). Si tiene → 409
  "No se puede cambiar la moneda de un proveedor con productos cargados."
  Pasar a `usd` exige `dolar_actual` > 0 en el mismo request; pasar a `ars`
  deja `dolar_actual` en NULL. El cambio de moneda no genera historial de dólar.
- Auditoría `proveedor.crear` / `proveedor.editar`.

**Cambio de estado** `cambiar_estado(autor, id, nuevo_estado, confirmar_con_productos)`
- Baja siempre lógica (nunca DELETE).
- Reactivar un `inhabilitado` exige rol `admin` → si no, 403
  "Reactivar un proveedor inhabilitado requiere Admin".
- Dar de baja con productos activos: 409 "El proveedor tiene N producto(s)
  activo(s). Reasignarlos o confirmar la baja explícitamente." salvo
  `confirmar_con_productos = true`. El conteo consulta `productos` solo si la
  tabla ya existe (`to_regclass`).
- Auditoría `proveedor.reactivar` / `proveedor.desactivar` / `proveedor.inhabilitar`.

**Cambio de dólar — núcleo único `_aplicar_cambio_dolar`** (lo usan el cambio
individual, el masivo y el Excel):
- El proveedor tiene que estar en `usd`; si está en `ars` → 409
  "El proveedor trabaja en pesos: no tiene valor de dólar."
- Valor > 0 (redondeado a 2 decimales).
- **Si el valor nuevo es igual al actual no hace nada** (ni historial, ni
  auditoría, ni recálculo).
- Inserta en `proveedor_dolar_historial`, actualiza `dolar_actual`, audita
  `dolar.cambio` con `{dolar_actual}` antes/después y el origen.
- Recalcula en la misma transacción el precio de venta de los productos del
  proveedor (`services.productos.recalcular_precios_de_proveedor`, sesión 04;
  import local para no acoplar módulos).

**Cambio masivo** (solo proveedores **activos en `usd`**)
- `proveedor_ids` opcional (None = todos los activos en dólares). Si alguno de
  los ids está en pesos o inactivo se ignora; si no queda ninguno → 409.
- Modalidad `valor` (absoluto igual para todos) o `porcentaje` (sobre el dólar
  de cada uno, redondeado a 2 decimales).
- `preview_masivo(...)` calcula sin aplicar → `[{proveedor_id, nombre, valor_actual, valor_nuevo}]`.
- Un registro de historial y de auditoría por proveedor afectado.

**Plantilla Excel** `generar_plantilla_dolar()`: hoja "Dolar" con columnas
`proveedor_id | nombre | dolar_nuevo`, solo proveedores **activos en dólares**,
con `dolar_nuevo` precargado con el valor actual; segunda hoja "Instrucciones"
(las filas sin modificar se saltean; no cambiar encabezados; todo o nada).

**Importación Excel** `importar_dolar(contenido)` (openpyxl):
- La lectura va por `core/excel.py::leer_tabla(contenido, requeridas, opcionales)`
  (se crea en esta sesión y la reutiliza la importación de la sesión 08; la
  plantilla usa `generar_plantilla`): ubica las columnas `proveedor_id` y
  `dolar_nuevo` por nombre (cualquier orden, ignora columnas extra), saltea
  filas totalmente vacías.
- Errores por fila: id inválido o vacío, id repetido en el archivo, proveedor
  inexistente, inactivo o **en pesos**, `dolar_nuevo` inválido/vacío/≤ 0.
- Todo-o-nada: si hay errores devuelve la lista y **no aplica nada**.
- Respuesta `{aplicados, sin_cambios, errores: [{fila, error}]}` (status 200
  aunque haya errores; el router hace rollback). Archivo no-xlsx, vacío o sin
  columnas → 409.

### Endpoints (`/api/v1/proveedores`)

```
GET    /dolar/en-uso                 → {hay_proveedores_en_dolares: bool}  [PROVEEDORES ver]
POST   /dolar/masivo/preview         → preview del cambio masivo      [PROVEEDORES editar + dolar.cambio_masivo]
POST   /dolar/masivo                 → aplicar cambio masivo           [idem]
GET    /dolar/plantilla              → descarga dolar-proveedores-YYYY-MM-DD.xlsx   [idem]
POST   /dolar/importar               → multipart `archivo` .xlsx       [idem]
GET    ""                            → listado (lista, sin paginar) con filtros
                                       nombre, email, telefono, provincia, pais,
                                       estado, moneda, dolar_desde, dolar_hasta  [PROVEEDORES ver]
GET    /{id}                         → ficha                           [PROVEEDORES ver]
POST   ""                            → alta (201) {…, moneda, dolar_actual?}  [PROVEEDORES crear]
PUT    /{id}                         → edición (incluye moneda, con la regla de arriba)  [PROVEEDORES editar]
PATCH  /{id}/estado                  → {estado, confirmar_con_productos}  [PROVEEDORES editar]
PATCH  /{id}/dolar                   → {valor_nuevo}                   [PROVEEDORES editar]
GET    /{id}/dolar/historial         → historial (más reciente primero) [PROVEEDORES ver]
```
Las rutas `/dolar/...` se declaran ANTES de `/{proveedor_id}`.
Errores: `NoEncontrado` → 404, `SinPermiso` → 403, `ReglaDeNegocio` → 409.

Permisos (seed de la sesión 02): Admin CRUD completo; Supervisor solo ver.
El recurso `dolar.cambio_masivo` lo tienen quienes tengan editar general del
módulo.

### Frontend

Proveedores vive dentro del hub **Configuraciones** (tarjeta "Proveedores —
Datos de proveedores nacionales e internacionales").

La página recibe en el contexto `usa_dolar` (= `hay_proveedores_en_dolares()`).
Con `usa_dolar = false` se ocultan: el botón "Cambio masivo del dólar", los
filtros Dólar desde/hasta y la columna Dólar. La moneda siempre se puede
elegir en el alta, así que el primer proveedor en dólares vuelve a mostrar todo.

#### `/proveedores` — Listado (`pages/proveedores/listado.html` + `static/js/proveedores.js`)
- Encabezado "Proveedores" con volver a "Configuraciones"; a la derecha
  botón "Cambio masivo del dólar" (→ `/proveedores/dolar-masivo`, solo si
  `usa_dolar`) y "+ Crear nuevo".
- Filtros en tiempo real (debounce): Nombre, País, Provincia, Estado
  ("Estado (todos)" / Activo / Desactivado / Inhabilitado), Moneda
  ("Moneda (todas)" / Pesos / Dólares), Dólar desde/hasta (si `usa_dolar`);
  "Limpiar filtros"; contador "N proveedores encontrados".
- Tabla: Nombre, Contacto (email y teléfono en dos líneas), Provincia, País,
  Moneda ("Pesos" / "Dólares"), Dólar (`US$ ` + `formatearDolar`, alineado a la
  derecha; "—" para proveedores en pesos; columna visible solo si `usa_dolar`),
  Estado (texto coloreado); acciones Ver, Editar, Dar de baja (papelera) /
  Reactivar.
- Modales (parciales `_modal_ficha.html`, `_modal_form.html`, `_modal_baja.html`):
  - **Ficha**: País, Provincia, Teléfono, Email, Notas, Moneda y, si es en
    dólares, "Valor actual del dólar".
  - **Alta/edición**: Nombre*, País, Provincia, Teléfono, Email, Notas,
    **Moneda*** (radio "Pesos" / "Dólares", default Pesos). Si se elige
    Dólares en el alta, aparece "Valor actual del dólar" (> 0, "Debe ser mayor
    a cero."). En la edición la moneda solo es editable si el proveedor no
    tiene productos (si el backend responde 409 se muestra el mensaje). Para un
    proveedor en dólares, la edición muestra el recuadro con el dólar actual,
    input "Nuevo" y botón para aplicar el cambio individual
    (`PATCH /{id}/dolar`), y la tabla **"Historial del dólar"** (Fecha,
    Anterior, Nuevo, Origen).
  - **Dar de baja**: elegir "Desactivar" ("Se puede reactivar libremente.") o
    "Inhabilitar" ("Solo Admin puede reactivarlo."). Si el backend responde
    409 por productos activos, muestra la advertencia y permite confirmar
    reenviando con `confirmar_con_productos: true`.
  - Los modales solo se cierran con la X / Cancelar.

#### `/proveedores/dolar-masivo` — Cambio masivo (`dolar_masivo.html` + `static/js/dolar_masivo.js`)
Si no hay proveedores activos en dólares, la página muestra "No hay
proveedores que trabajen en dólares." con volver a "Proveedores".
- Encabezado "Cambio masivo" con volver a "Proveedores".
- Bloque **"Por valor o porcentaje"**: lista de "Proveedores en dólares" con
  checkboxes (todos o selección), modalidad "Valor fijo" / "Porcentaje", valor,
  botón "Vista previa" que muestra tabla Proveedor | Actual | Nuevo, y
  confirmación obligatoria antes de aplicar.
- Bloque **"Importar desde Excel"**: botón "Descargar Excel"
  (`/api/v1/proveedores/dolar/plantilla`), texto de ayuda (descargá, cambiá,
  subí; columnas `proveedor_id` y `dolar_nuevo`), zona para subir el `.xlsx`,
  resultado con aplicados/sin cambios y, si hay errores, tabla
  "Errores encontrados (no se aplicó nada):" Fila | Error.
- `window.formatearDolar` (app.js) se comparte entre ambas pantallas.

---

## PARTE 2 — HUB DE CONFIGURACIONES

- `GET /configuracion` → `pages/configuracion/index.html` con
  `encabezado('Configuraciones')` y el macro `components/hub.html::hub(secciones)`:
  grilla de tarjetas (1 columna en mobile, 2 desde `sm`), cada tarjeta es un
  enlace con nombre, descripción, tooltip opcional (`title`) y chevron.
- Las secciones viven en `CONFIGURACION_SECCIONES` (en `api/pages.py`) y se
  filtran con `_visible()`. Lista final (cada sesión agrega la suya):

| Tarjeta | Descripción | URL | Visibilidad |
|---|---|---|---|
| Proveedores | Datos de proveedores nacionales e internacionales | /proveedores | PROVEEDORES ver |
| Importar desde Excel | Carga inicial de proveedores, clientes y productos | /importacion | IMPORTACION crear (sesión 08) |
| Usuarios | Altas, permisos e historial de accesos | /usuarios | USUARIOS ver |
| Roles | Perfiles de permisos y su alcance por módulo | /roles | solo Admin |
| Medios de pago | Con qué se cobra y los planes de cuotas de cada uno | /medios-de-pago | CONFIGURACION ver (sesión 06) |
| Motivos de descuento | Por qué se descuenta y qué porcentaje se sugiere | /motivos-descuento | CONFIGURACION ver (sesión 06) |
| Promociones | 2x1 y 3x2, sobre qué productos y hasta cuándo | /promociones | recurso `configuracion.promociones` (sesión 06) |

- El ítem "Configuraciones" del sidebar (`hub_configuracion: True`) se muestra si
  el usuario ve al menos una tarjeta. Las pantallas de cada sección pasan
  `ruta_activa="/configuracion"` para que el sidebar siga marcando el hub, y
  su encabezado tiene "volver a Configuraciones".

---

## TESTS (`tests/test_proveedores.py`, `tests/test_configuracion_hub.py`)
- Alta en pesos sin dólar; alta en dólares exige dólar > 0; el CHECK de la base
  rechaza `ars` con dólar y `usd` sin dólar.
- Cambio de moneda permitido sin productos y rechazado (409) con productos.
- Cambio de dólar sobre un proveedor en pesos → 409; al mismo valor no genera nada.
- Masivo, plantilla e importación ignoran/rechazan proveedores en pesos.
- `hay_proveedores_en_dolares()` refleja solo proveedores activos en `usd`.
- Hub: cada tarjeta respeta su visibilidad.

---

## CRITERIOS DE ACEPTACIÓN

- No existe DELETE de proveedores en la API.
- Cada proveedor es en pesos o en dólares; solo los de dólares tienen valor de
  dólar, historial y participan del cambio masivo y del Excel.
- Sin proveedores activos en dólares, ninguna pantalla muestra controles del dólar.
- Cada cambio real de dólar (individual, masivo o Excel) genera un registro en
  `proveedor_dolar_historial` y en `auditoria`; un "cambio" al mismo valor no
  genera nada.
- `proveedor_dolar_historial` rechaza UPDATE y DELETE.
- La importación Excel no aplica nada si hay errores en alguna fila y devuelve
  la lista detallada; la plantilla descargada se puede volver a subir tal cual.
- El dólar de un proveedor en dólares no puede quedar en cero ni negativo
  (CHECK en la base + validación).
- La moneda de un proveedor con productos no se puede cambiar.
- Un proveedor inhabilitado no se reactiva sin Admin.
- Buscar "cordoba" encuentra "Córdoba" en provincia.
