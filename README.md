# Stork Gestión

Sistema de gestión para comercios (una instancia por cliente). Backend FastAPI
que sirve la API (`/api/v1`) y las pantallas (Jinja2 + HTMX + Alpine + Tailwind),
sobre PostgreSQL.

## Qué incluye
- **Usuarios y permisos:** login con JWT + refresh, roles Admin / Supervisor /
  Vendedor y roles personalizados con permisos por pantalla y acción.
- **Proveedores:** moneda y dólar propio de cada uno (cambio individual, masivo
  o por Excel) con recálculo de precios en cascada.
- **Productos:** categorías en árbol, SKU con dígito verificador, código de
  barras, fotos (subida o cámara), etiquetas en PDF y precio por margen o manual.
- **Stock:** ingresos, bajas con motivo y auditorías de inventario; el stock
  nunca queda negativo.
- **Ventas y clientes:** pantalla de venta con lector de código (F2/F10/ESC),
  cantidad por línea, descuentos por ítem y general, promociones, medios de
  pago con cuotas, anulación total.
- **Caja:** turnos, retiros de efectivo y arqueo por medio de pago con aviso de
  diferencias.
- **Importación desde Excel** de proveedores, clientes y productos.
- **Reportes** con gráfico, exportación a Excel y PDF, y tablero de inicio.
- **Auditoría inmutable** de toda acción sensible (la base no permite UPDATE ni
  DELETE sobre `auditoria`).

Fuera de esta versión: facturación electrónica (la hace la registradora
fiscal), multi-local, cuenta corriente, compras.

## Requisitos
- Docker 24+ con Docker Compose v2.

## Puesta en marcha
```bash
cp .env.example .env        # y ajustar valores (JWT_SECRET, puertos, APP_NAME…)
docker compose up --build
```
Al arrancar, el backend aplica las migraciones (`alembic upgrade head`) y el
seed idempotente (`migrations/seed.sql`).

- App: http://localhost:8000
- Swagger: http://localhost:8000/docs (oculto con `APP_ENV=production`)
- Healthchecks: `/api/v1/health` y `/api/v1/health/db`

### Puerto ocupado
Si 5432, 8000 u 80 están en uso, cambiar en `.env` `POSTGRES_PORT_HOST`,
`BACKEND_PORT_HOST` o `BACKEND_PORT_PROD` (el puerto interno no cambia).
`POSTGRES_PORT_HOST` solo se publica en loopback (`127.0.0.1`): la base
solo es accesible desde el propio servidor, nunca desde la red externa.

### Proxies de confianza (IP de auditoría)
`PROXIES_DE_CONFIANZA` en `.env` indica cuántos proxies inversos PROPIOS hay
delante de la app, para no confiar ciegamente en `X-Forwarded-For` (que
controla el cliente) al registrar la IP en la auditoría: `0` = conexión
directa / docker compose local (default); `1` = detrás de un proxy propio
como Railway o un nginx propio.

## Tests
```bash
docker compose exec backend pytest
```
Corren contra PostgreSQL real en la base `gestion_test` (se recrea en cada corrida).

Tests de JavaScript (lógica de los componentes Alpine, sin navegador ni red; en
el host, con Node 22+, sin dependencias):
```bash
node --test backend/tests_js/
```

## Datos de demo (solo desarrollo)
```bash
docker compose exec backend python -m scripts.datos_demo
```
Carga usuarios, proveedores, productos, clientes, promociones y 45 días de
ventas pasando por los services (mismas reglas y auditoría). Los usuarios demo
usan la contraseña `Demo1234`. Si ya se cargó una vez no hace nada. **No usar en
la base de un cliente.**

## Migraciones
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```
Las migraciones se escriben a mano en `backend/migrations/versions/` (numeradas 0001, 0002…).

## Instalar un cliente nuevo
1. Copiar el proyecto a una carpeta propia del cliente.
2. Crear su `.env` (nombre visible en `APP_NAME`, `JWT_SECRET` propio, puertos).
3. Logo: `backend/app/static/img/logo.svg` (si no existe se muestra `APP_NAME`).
   Favicon: reemplazar `favicon.svg`, `favicon-32.png` y `apple-touch-icon.png`.
4. Paleta: redefinir las variables `--color-*` en `backend/app/static/css/custom.css`.
5. `docker compose up -d --build`.

## Archivos subidos
Viven en `./uploads` (montado en `/uploads` del contenedor) y se sirven en
`/uploads/...`. No se versionan; incluirlos en los backups de archivos del servidor.

## Backups
El servicio `backup` hace un `pg_dump -Fc` diario a `./backups/gestion-AAAA-MM-DD_HHMM.dump`
y borra los que tienen más de `BACKUP_RETENCION_DIAS` días.
- Hora: `BACKUP_HORA` (hora del negocio, default 03:00).
- Backup inmediato: `BACKUP_AHORA=1` en `.env` y `docker compose up -d backup`.
- Restaurar:
  ```bash
  docker compose exec -T db pg_restore -U gestion -d gestion --clean --if-exists < backups/gestion-AAAA-MM-DD_HHMM.dump
  ```

## Credenciales iniciales
Usuario `admin`, contraseña `Admin1234!`. En el primer ingreso el sistema obliga
a cambiarla. Los demás usuarios se crean desde Configuraciones → Usuarios (o por
la API `/api/v1/usuarios`) y también cambian su contraseña al primer ingreso.

## Recuperación de contraseña
Requiere SMTP configurado (`SMTP_*` en `.env`) y que el usuario tenga email.
El enlace del mail vence en 30 minutos y sirve una sola vez. Sin SMTP, el Admin
puede asignar una contraseña nueva editando al usuario (queda obligado a
cambiarla al ingresar).

## Documentación
- `CLAUDE.md`: decisiones de producto, principios de arquitectura y design system.
- `modulos/`: spec de cada módulo (01 infraestructura → 09 reportes).
- `docs/superpowers/`: plan y diseño de cada sesión de desarrollo.
- `docs/pendientes.md`: deuda técnica y verificaciones pendientes, con el
  momento en que conviene resolverlas (incluye lo que falta antes de instalar
  el primer cliente real).
- `CHANGELOG.md`: qué entró en cada versión.
