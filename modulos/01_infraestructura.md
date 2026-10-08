# SESIÓN 01 — Infraestructura Base
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## ALCANCE DEL SISTEMA

Sistema de gestión simple para **un único punto de venta** (no existe el
concepto de locales, sucursales, depósitos ni dispositivos): Clientes,
Proveedores, Productos, Stock, Ventas, Caja, Importación desde Excel y
Reportes. Se despliega **una instancia por cliente** (single-tenant: su propio
`docker compose` y su propia base). Roles del sistema: **Admin**,
**Supervisor** y **Vendedor**. Toda la interfaz es de escritorio y responsive
(no hay pantallas mobile-first ni layouts distintos según el rol).

## OBJETIVO DE ESTA SESIÓN

Crear la base técnica del proyecto. No implementar lógica de negocio.
El resultado debe ser un entorno que levante con `docker compose up` y
donde cualquier módulo posterior pueda agregarse sin tocar la estructura.

---

## ENTREGABLES ESPERADOS

### 1. Estructura de carpetas completa

```
/docker-compose.yml
/.env.example
/README.md
/uploads                      → bind mount / volumen: fotos de productos (fuera de git)
/backups                      → pg_dump diarios (fuera de git)
/backup
  backup.sh                   → loop diario de pg_dump con rotación
/backend
  Dockerfile
  entrypoint.sh
  requirements.txt
  alembic.ini
  pytest.ini
  main.py
  config.py
  /migrations
    env.py, script.py.mako, seed.sql
    /versions                 → migraciones numeradas 0001, 0002, …
  /app
    /api
      pages.py                → rutas HTML (Jinja2), include_in_schema=False
      /v1                     → un router por módulo + __init__.py agregador
    /core                     → database, auditoria, utils, templates, permisos…
    /middleware
    /models
    /schemas                  → comunes.py (RespuestaPaginada, MensajeResponse)
    /services
    /repositories
    /reports                  → PDF (WeasyPrint) y Excel (openpyxl)
    /templates
      base.html
      /auth
      /components
      /pages
      /reports                → plantillas HTML que WeasyPrint convierte a PDF
    /static
      /css/custom.css
      /js/app.js
      /img                    → favicon y logo (reemplazables)
  /tests
    conftest.py
```

Con `__init__.py` en todos los paquetes Python.

### 2. docker-compose.yml

- `name: gestion` fijado explícitamente (así renombrar la carpeta no cambia el
  nombre del volumen y la base no "desaparece").
- Servicio `db`: `postgres:15`, `container_name: gestion_db`, volumen
  persistente `postgres_data`, `TZ` y `PGTZ` = `America/Argentina/Buenos_Aires`,
  credenciales desde `.env` con defaults `gestion/gestion/gestion`, puerto del host
  configurable `${POSTGRES_PORT_HOST:-5432}:5432`, healthcheck con `pg_isready`.
- Servicio `backend`: build desde `./backend`, `container_name: gestion_backend`,
  `env_file: .env`, `POSTGRES_HOST=db`, depende de `db` sano, bind mount
  `./backend:/app` y comando `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`.
  Puertos del host configurables: `${BACKEND_PORT_HOST:-8000}:8000` (desarrollo)
  y `${BACKEND_PORT_PROD:-80}:8000` (producción). Healthcheck con
  `curl -fsS http://localhost:8000/api/v1/health`. Monta además
  `./uploads:/uploads` (`UPLOADS_DIR=/uploads`): los archivos subidos nunca
  viven dentro del código ni del contenedor, así sobreviven a rebuilds y deploys.
- Servicio `backup`: imagen `postgres:15`, `container_name: gestion_backup`,
  depende de `db` sano, monta `./backups:/backups` y `./backup/backup.sh`.
  El script corre en loop: a la hora `BACKUP_HORA` (default `03:00`, hora del
  negocio) hace `pg_dump -Fc` a `/backups/gestion-YYYY-MM-DD_HHMM.dump` y borra
  los dumps con más de `BACKUP_RETENCION_DIAS` (default 14). Loguea cada
  resultado; un fallo no detiene el loop. Con `BACKUP_AHORA=1` hace además un
  dump inmediato al arrancar (para probarlo o antes de una actualización).
- No existe servicio `frontend`: FastAPI sirve el HTML. Sin nginx, sin build.

### 3. Dockerfile y entrypoint

- `python:3.12-slim`, `TZ=America/Argentina/Buenos_Aires`.
- Paquetes de sistema: `build-essential`, `libpq-dev`, `postgresql-client`
  (psql para el seed), `tzdata`, `curl`, y las librerías de WeasyPrint
  (`libpango-1.0-0`, `libpangoft2-1.0-0`, `libcairo2`, `libgdk-pixbuf-2.0-0`,
  `libffi-dev`, `shared-mime-info`, `fonts-dejavu-core`).
- Copiar `requirements.txt` antes que el código (cache de capas).
- `CMD ["./entrypoint.sh"]`. El `entrypoint.sh` (pensado para PaaS tipo Railway):
  1. `alembic upgrade head`
  2. si hay `DATABASE_URL`, aplica `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/seed.sql`
     (el seed es idempotente)
  3. `exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"`
  En desarrollo docker-compose sobreescribe el comando con `--reload`.

### 4. requirements.txt

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.20
pydantic==2.10.4
pydantic-settings==2.7.0
email-validator==2.2.0
sqlalchemy==2.0.36
psycopg2-binary==2.9.10
alembic==1.14.0
pyjwt==2.10.1
passlib[bcrypt]==1.7.4
bcrypt==4.2.1
jinja2==3.1.5
python-barcode==0.15.1        # Code128 en SVG (módulo 04)
weasyprint==63.1
openpyxl==3.1.5
markdown==3.7
python-dateutil==2.9.0.post0
pytest==8.3.4
httpx==0.28.1
```

### 5. FastAPI base

**`config.py`** — `Settings(BaseSettings)` con `pydantic-settings`, leído de
`.env`, `extra="ignore"`, instancia única cacheada `settings`. Ningún módulo lee
`os.environ` directamente. Variables:

- Aplicación: `APP_NAME="Sistema de Gestión"` (nombre visible del sistema, se cambia por `.env`), `APP_ENV` (development|production),
  `DEBUG`, `API_V1_PREFIX="/api/v1"`, `APP_URL` (para links de emails).
- `TIMEZONE="America/Argentina/Buenos_Aires"` + propiedad `TZ` (ZoneInfo).
- Base: `POSTGRES_USER/PASSWORD/DB/HOST/PORT`; `DATABASE_URL` como override
  opcional (alias `DATABASE_URL`) y propiedad computada `DATABASE_URL`
  (`postgresql+psycopg2://…`).
- JWT: `JWT_SECRET`, `JWT_ALGORITHM="HS256"`, `JWT_ACCESS_TOKEN_MINUTES=30`,
  `JWT_REFRESH_TOKEN_DAYS=7`, `SESION_INACTIVIDAD_MINUTOS=30` (constante APARTE
  de la vida del access token; debe ser ≥ a ella), `JWT_COOKIE_NAME="access_token"`,
  `JWT_REFRESH_COOKIE_NAME="refresh_token"`, `COOKIE_SECURE=False`.
- `CORS_ORIGINS` (lista separada por comas) + propiedad `CORS_ORIGINS_LIST`.
- SMTP: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM="no-reply@example.com"`, `SMTP_TLS=True`.
- Archivos: `UPLOADS_DIR="/uploads"` (en tests, un directorio temporal).
- Backups (los lee solo el servicio `backup`, pero se documentan en
  `.env.example`): `BACKUP_HORA="03:00"`, `BACKUP_RETENCION_DIAS=14`.

**`main.py`**:
- `lifespan` que importa `app.models` para registrar todos los modelos.
- Swagger/ReDoc/openapi.json **deshabilitados cuando `APP_ENV == "production"`**.
- `CORSMiddleware` con `allow_credentials=True`.
- Middleware `AuthRefreshMiddleware` (se crea en la sesión 02; en esta sesión
  dejar el punto de montaje).
- `app.mount("/static", StaticFiles(directory="app/static"))` y
  `app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR))` (crea el
  directorio si no existe).
- `app.include_router(api_router, prefix=settings.API_V1_PREFIX)` y **al final**
  `app.include_router(pages_router)` para que la API tenga prioridad.

**`app/api/v1/__init__.py`**: único `api_router` que agrega los routers de cada
módulo; `main.py` solo monta ese.

**Healthcheck** (`app/api/v1/health.py`):
- `GET /api/v1/health` → `{"status": "ok"}` (no toca la base).
- `GET /api/v1/health/db` → `{"status": "ok", "database": "ok"}` o
  `{"status": "degraded", "database": "error", "detalle": "..."}`.

**`app/core/database.py`**: `engine` con `pool_pre_ping=True` (echo solo en
desarrollo con DEBUG), `SessionLocal` (`autoflush=False`, `expire_on_commit=False`),
`class Base(DeclarativeBase)` y dependency `get_db()`.

**`app/core/utils.py`** (utilidades transversales, Principio 2):
- `ahora()` → datetime con tz del negocio (para cálculos y JWT).
- `ahora_db()` → datetime del negocio **sin tzinfo**: todas las columnas son
  `TIMESTAMP` sin zona y guardan hora local UTC-03:00.
- `ip_de_request(request)` respetando `X-Forwarded-For`.
- `redondear(valor, decimales=2)` half-up.
- `redondear_hacia_arriba(valor, multiplo)` (CEIL al múltiplo; múltiplo ≤ 0 no redondea).
- `redondear_hacia_abajo(valor, multiplo)` (FLOOR al múltiplo; se usa para precios con descuento).
- `normalizar_texto()` (colapsa espacios, vacío → None).
- `capitalizar_inicial()` (solo la primera letra en mayúscula, sin tocar el resto).
- `sin_tildes()` y `sin_tildes_sql(columna)` — misma tabla de reemplazo
  `áéíóúüñÁÉÍÓÚÜÑ → aeiouunAEIOUUN`; la versión SQL usa `translate()` de Postgres
  (no la extensión `unaccent`, que exige superusuario).

**`app/core/templates.py`**: instancia única de `Jinja2Templates` con globals
`APP_NAME`, `APP_ENV` y `estatico(path)`, que devuelve `/static/<path>?v=<mtime>`
para romper la caché del navegador (StaticFiles no manda Cache-Control). Los
templates usan `estatico('/js/app.js')` en lugar de `url_for('static', …)`.

**`app/schemas/comunes.py`**: `RespuestaPaginada[T]` (`total`, `pagina`, `tamano`,
`resultados`) — envoltorio estándar de todos los listados — y `MensajeResponse`.

### 6. Tabla de auditoría (infraestructura transversal)

Migración `0001_infraestructura_base`:

```sql
auditoria (
  id              BIGSERIAL PK,
  usuario_id      BIGINT,              -- NULL = sistema. SIN FK a usuarios (debe sobrevivir)
  accion          VARCHAR(100) NOT NULL,  -- "<entidad>.<verbo>", ej: "producto.editar"
  entidad         VARCHAR(100) NOT NULL,
  entidad_id      BIGINT,
  estado_anterior JSONB,
  estado_nuevo    JSONB,
  ip_origen       VARCHAR(45),
  timestamp       TIMESTAMP NOT NULL DEFAULT now()
)
-- índices: usuario_id, accion, entidad, timestamp, (entidad, entidad_id)
```

Inmutabilidad en la base, en dos capas:
1. Función `auditoria_bloquear_modificacion()` que hace `RAISE EXCEPTION ... USING
   ERRCODE = 'insufficient_privilege'` y triggers **a nivel sentencia**
   `trg_auditoria_no_update`, `trg_auditoria_no_delete`, `trg_auditoria_no_truncate`.
2. `REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM current_user` (defensa en
   profundidad; si el rol es superusuario el trigger es lo que cuenta).

`app/core/auditoria.py` — única vía de escritura:
- `registrar_auditoria(db, *, accion, entidad, usuario_id=None, entidad_id=None,
  estado_anterior=None, estado_nuevo=None, ip_origen=None, request=None)`:
  hace `db.add` + `db.flush()`, **nunca commit** (misma transacción que la acción).
- `snapshot(obj, campos=None)`: modelo o dict → dict JSON-safe (Enum → value,
  Decimal → str, fechas → isoformat, UUID → str), filtrando `CAMPOS_SENSIBLES`
  (`password`, `password_hash`, `clave_especial(_hash)`, `pin(_hash)`, `token`,
  `access_token`, `refresh_token`).

Consulta (solo lectura): `GET /api/v1/auditoria` con filtros `usuario_id`,
`accion` (ILIKE parcial, ej. `venta.`), `entidad` (ILIKE), `entidad_id`, `desde`,
`hasta` (fecha), `pagina`, `tamano` (default 50, máx 200), orden por timestamp
desc. Respuesta `RespuestaPaginada[AuditoriaResponse]`. Exige
`requiere_permiso(Modulo.AUDITORIA, "ver")` (se implementa en la sesión 02;
en esta sesión dejar el service `services/auditoria.py::listar_auditoria`).
No hay pantalla HTML de auditoría: el ítem de menú existe pero está oculto.

### 7. Tabla configuracion_sistema (fila única)

```sql
configuracion_sistema (
  id                    BIGSERIAL PK,
  redondeo              NUMERIC(10,2) NOT NULL,  -- múltiplo del redondeo de precios (CEIL al calcular
                                                 -- el precio de venta, FLOOR al aplicar descuentos)
  margen_default        NUMERIC(6,2) NOT NULL,   -- % que propone el alta de producto; CHECK 0..1000
  descuento_maximo      NUMERIC(5,2) NOT NULL,   -- tope del descuento PROPIO del producto; CHECK 0..100
  tope_descuento_venta  NUMERIC(5,2) NOT NULL,   -- tope de producto + descuento de venta (suma directa); CHECK 0..100
  updated_at            TIMESTAMP NOT NULL DEFAULT now(),
  updated_by            BIGINT                   -- FK a usuarios se agrega en 0002 (ON DELETE SET NULL)
)
```

Los descuentos siempre se calculan **encadenados** (no hay configuración de
método). Por ahora no hay pantalla para editar esta tabla (se cambia por SQL o
por una sesión futura de "Ajustes"); los services la leen con
`services/configuracion.py::obtener_configuracion(db)`, única vía de lectura.

La misma migración 0001 crea también el catálogo `motivos_baja`
(`id`, `nombre VARCHAR(100) UNIQUE`, `activo BOOLEAN DEFAULT true`) porque lo
necesita el seed.

### 8. Frontend base — HTMX + Alpine.js + Jinja2

Todo por CDN, sin npm ni build:

```html
<script src="https://cdn.tailwindcss.com"></script>
{% include "components/_tailwind_config.html" %}
<link rel="stylesheet" href="{{ estatico('/css/custom.css') }}">
<script src="https://unpkg.com/htmx.org@2.0/dist/htmx.min.js"></script>
<script src="{{ estatico('/js/app.js') }}" defer></script>   {# antes de Alpine #}
<script src="https://unpkg.com/alpinejs@3.x/dist/cdn.min.js" defer></script>
```
(Sin atributos `integrity` en los CDN: decisión tomada.)

**Tokens de diseño — `static/css/custom.css`** (única fuente de colores, tipografía
y geometría). **Los valores concretos los define el nuevo diseño**, que todavía no
está cerrado: en esta sesión se crea la estructura con valores neutros
provisorios (grises y un único color primario), de modo que cambiar el diseño
sea solo editar este archivo y `_tailwind_config.html`, sin tocar templates.
- `:root` con las variables `--color-primary`, `--color-primary-hover`,
  `--color-accent`, `--color-welcome`, `--color-bg`, `--color-surface`,
  `--color-surface-alt`, `--color-border`, `--color-text`, `--color-text-muted`,
  `--color-text-disabled`, `--color-text-header`, `--color-text-invert`,
  `--color-input-border`, `--color-danger`, `--color-success`,
  `--color-sidebar-bg`, `--color-sidebar-text`, `--color-sidebar-active`,
  `--color-check-borde`, y `--font-sans` (tipografía; provisoriamente la pila
  de fuentes del sistema).
- Geometría: `--radius-input`, `--radius-pill`, `--radius-search`,
  `--sidebar-width`, `--header-height`, `--layout-max`.
- Alturas de control: `--alto-control`, `--alto-boton`, `--toque-min`; bajo
  `@media (pointer: coarse)` suben a un mínimo de 2.75rem (44px) para pantallas
  táctiles.
- **Modo oscuro** con `.dark` redefiniendo las variables de color.
- `html, body { overflow-x: hidden }`, `img, svg, video, canvas { max-width: 100% }`,
  fuerza de color en inputs/selects/textarea (modo oscuro), clases
  `.campo-linea`, `.nav-activo` (ítem activo del sidebar), `.acceso-check`,
  `.tarjeta`, `.tarjeta-enlace`, `[x-cloak]`, `.htmx-indicator`, `@media print`
  (oculta `.no-print`).

**`components/_tailwind_config.html`** (única config de Tailwind, incluida en
`base.html` y `auth/base_auth.html`):
- `darkMode: 'class'`.
- `screens` **reemplaza** la escala: `sm 640px`, `lg 1024px`, `xl 1280px` (sin `md` ni `2xl`).
- Colores mapeados a las variables con `color-mix(in srgb, var(--x) calc(<alpha-value> * 100%), transparent)`
  para que funcionen los modificadores de opacidad (`bg-danger/15`): `primary`,
  `primary-hover`, `accent`, `welcome`, `bg`, `surface`, `surface-alt`, `borde`,
  `borde-campo`, `texto`, `texto-muted`, `texto-disabled`, `texto-header`,
  `texto-invert`, `danger`, `success`, `sidebar-bg`, `sidebar-text`.
- `fontFamily.sans: var(--font-sans)`; escala `fontSize` en rem (`xs`, `sm`,
  `base`, `lg`, `xl`, `2xl`, `titulo`) con valores provisorios estándar.
- `borderRadius`: `input`, `pill`, `search` desde las variables.
- `spacing.sidebar/header` desde las variables; `maxWidth.layout 90rem`;
  `height.control/boton`, `width.control`, `minHeight/minWidth.toque` desde variables.

**`base.html`** (layout principal):
- `<html x-data="temaApp()" x-init="aplicar()" :class="{dark}">`
  y script inline que aplica `dark` desde `localStorage` antes de montar Alpine.
- Favicon único (`components/_favicon.html`, archivos en `static/img/`:
  `favicon.svg`, `favicon-32.png`, `apple-touch-icon.png`; provisorios, se
  reemplazan con el diseño nuevo).
- Sidebar `w-sidebar` fijo desde `lg`; por debajo es un cajón deslizable con
  overlay y botón hamburguesa en el header (`x-data="{ nav: false }"`, ESC cierra).
  Cabecera del sidebar: marca del sistema (`components/marca.html`: muestra
  `static/img/logo.svg` si existe y, si no, `APP_NAME` en texto) y el nombre del
  usuario debajo. Ítems desde la variable `menu` y pie
  desde `menu_pie` (`components/_sidebar_item.html`).
- Header `h-header`: botón de menú (mobile), toggle claro/oscuro (☾/☀),
  campanita de notificaciones **deshabilitada** (reservada), badge del usuario
  (`bg-accent rounded-pill`) con menú: rol, "Cambiar contraseña", "Cerrar sesión".
  El buscador global queda comentado en el markup (con `id="buscador-global"`).
- `<main id="contenido">` con `{% block contenido %}`.
- Contenedor global de toasts y modal "Tu sesión está por vencer" (Alpine
  `avisoSesion(inactividad_minutos)`, botón "Seguir trabajando").
- Bloques `titulo`, `head_extra`, `scripts`.

**`static/js/app.js`** (globales):
- `temaApp()` (toggle de tema persistido en `localStorage.theme`).
- `window.formatearDolar(v)` y `window.pesos(v)` (formato es-AR; decimales solo si
  existen — nunca redondear en el frontend).
- `window.toast(mensaje, tipo, duracion)` vía evento `toast`; el backend puede
  dispararlo con `HX-Trigger: {"toast": {...}}`.
- `window.pedir(url, opciones)` (fetch JSON que lanza `Error(detail)`).
- `normalizarTexto` (NFD sin diacríticos), `window.rutaDeIds`, `window.rutaCategoria`
  (camino de categoría), `window.combobox(...)` (select con búsqueda),
  `window.cerrarSesion()`, `window.webcamCapture()` (captura de fotos).
- Wrapper de `window.fetch`: emite `sesion:actividad` y ante 401 (salvo en
  `/api/v1/auth/`) muestra "Tu sesión venció" y va a `/login`.
- `htmx:afterRequest` cuenta como actividad; `htmx:responseError` muestra el
  `detail` en un toast; `htmx:sendError` → "Sin conexión con el servidor.".
- `window.avisoSesion(minutos)`: avisa 2 minutos antes del vencimiento por
  inactividad; "Seguir trabajando" hace `POST /api/v1/auth/refresh`.
- Atajos globales: F2 → `atajo-buscar`, F10 → `atajo-confirmar`, ESC → `atajo-cancelar`.

**Macros reutilizables en `templates/components/`**:
| Archivo | Macros |
|---|---|
| `badge.html` | `badge(texto, variante)`, `estado_texto(texto, variante)` |
| `botones.html` | `accion(variante, texto, href, atributos, icono_nombre, enlace)`, `acciones()`, `volver(url, texto)` |
| `combobox.html` | `combobox(id, opciones, texto, modelo, etiqueta, placeholder, …)` |
| `encabezado.html` | `encabezado(titulo, volver_url, volver_texto)` (call-block con acciones a la derecha) |
| `form_field.html` | `campo`, `campo_select`, `campo_booleano`, `campo_rango`, `boton` |
| `hub.html` | `hub(secciones, vacio)` — grilla de tarjetas para páginas de menú |
| `icons.html` | `icono(nombre, clases)` — set de íconos SVG inline |
| `marca.html` | `marca(clases)` — logo del sistema o `APP_NAME` en texto |
| `miniatura.html` | `miniatura(src, tamano)` — foto de producto con placeholder |
| `modal.html` | `modal_confirmacion(id)`, `modal(titulo, id)` (solo se cierran con la X) |
| `modal_confirmacion.html` | `modal_confirmacion(estado, accion, advertencia, …)` |
| `paginacion.html` | `paginacion(pagina, total, tamano)` (Alpine) |
| `switch_activos.html` | `switch_activos(modelo, al_cambiar, id)` — "solo activos" |
| `switch_estado.html` | `switch_estado(modelo, al_cambiar, id)` |
| `table.html` | `barra_filtros(...)`, `tabla(columnas, filas, acciones, url_base, vacio)`, `paginacion(...)` |
| `toast.html` | `contenedor_toasts()` |

(Los macros `permisos_tree.html`, `producto_form.html`, `fotos_producto.html` y
`cliente_form.html` se crean en las sesiones posteriores.)

**Páginas base** (`app/api/pages.py`, router HTML sin esquema OpenAPI):
- `GET /` → `pages/index.html`: solo el saludo "Bienvenido, <primer nombre>"
  en `text-2xl font-black text-welcome`. Sin tarjetas ni demos.
- `pages/pendiente.html`: plantilla para módulos no construidos ("Este módulo
  todavía no está disponible."). Hoy solo la usa `/ajustes`.
- `contexto_base(request, db, actual, **extra)` arma el contexto común de todas
  las páginas: `menu`, `menu_pie`, `usuario_actual`, `es_admin`,
  `inactividad_minutos`.
- El sidebar se define en Python (`MENU_SIDEBAR`, `MENU_SIDEBAR_PIE`) y se
  filtra por permisos (se completa en la sesión 02). Menú final, a medida que
  cada sesión agrega su ítem: Inicio, Productos (04), Gestión de Stock (05),
  Ventas (06), Clientes (06), Caja (07), Reportes (09) y Configuraciones (03).

### 9. Script de datos iniciales — `migrations/seed.sql`

Idempotente (cada INSERT con `WHERE NOT EXISTS` / `ON CONFLICT DO NOTHING`);
los bloques que dependen de tablas de sesiones posteriores se protegen con
`to_regclass(...) IS NULL → RAISE NOTICE; RETURN`, para poder re-ejecutarlo al
avanzar. Contenido de esta sesión:
- `configuracion_sistema`: `redondeo 1000.00`, `margen_default 100.00`,
  `descuento_maximo 30.00`, `tope_descuento_venta 50.00`.
- `motivos_baja`: Rotura, Robo, Muestra, Merma.
- Registro de auditoría `sistema.seed` (usuario NULL) una sola vez.
(Roles, usuario Admin y permisos se agregan al seed en la sesión 02.)

### 10. Tests

- `pytest.ini` con `pythonpath = .`, `testpaths = tests`.
- `tests/conftest.py`: los tests corren contra PostgreSQL real, en la base
  `gestion_test` (se hace `DROP DATABASE … WITH (FORCE)` / `CREATE DATABASE` y
  `alembic upgrade head` al inicio de la sesión). Cada test corre en una
  transacción con `join_transaction_mode="create_savepoint"` que se revierte al
  final. Así se prueban triggers y UNIQUE.
- Tests de la sesión: auditoría inmutable (UPDATE/DELETE fallan), tokens
  (`test_tokens.py`: todas las variables definidas en claro y oscuro), macros
  (`test_componentes.py`), marca con y sin logo (`test_marca.py`).

### 11. README y `.env.example`

`.env.example` con todas las variables (incluidas `POSTGRES_PORT_HOST`,
`BACKEND_PORT_HOST`, `BACKEND_PORT_PROD`). README con: requisitos (Docker 24,
Compose v2), `cp .env.example .env`, `docker compose up --build`, qué hacer si
un puerto está ocupado, migraciones y seed, URLs (app, `/docs`), credenciales
iniciales, **cómo instalar un cliente nuevo** (copiar la carpeta, `.env`
propio, logo en `static/img/`, paleta en `custom.css`) y **backups**: dónde
quedan, cómo cambiar hora/retención y cómo restaurar
(`pg_restore --clean --if-exists -d ...`). `uploads/` y `backups/` van al
`.gitignore`.

---

## CRITERIOS DE ACEPTACIÓN

- `docker compose up` levanta `db`, `backend` y `backup` sin errores.
- El servicio `backup` genera un dump restaurable y respeta la retención
  (se prueba forzando una corrida con `BACKUP_AHORA=1`).
- Un archivo en `/uploads` se sirve en `/uploads/...` y sobrevive a
  `docker compose down && up --build`.
- `GET /api/v1/health` y `GET /api/v1/health/db` responden 200.
- Swagger disponible en `http://localhost:8000/docs` (y oculto en producción).
- `alembic upgrade head` crea las tablas sin errores.
- La tabla `auditoria` rechaza UPDATE, DELETE y TRUNCATE.
- `GET /` renderiza el layout con sidebar, header y saludo.
- El toggle claro/oscuro funciona sin recargar; 
- Por debajo de 1024px el sidebar es un cajón con overlay; sin scroll horizontal.
- El seed es re-ejecutable sin duplicar datos.
