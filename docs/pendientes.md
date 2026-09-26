# Pendientes técnicos

Hallazgos de las revisiones que no se resolvieron todavía, con el momento en
que conviene resolverlos. Al resolver uno, borrarlo de esta lista.

## Antes de la primera instalación real de un cliente
- **Rol de base de datos separado para la app.** Hoy la app se conecta como
  dueña de las tablas y superusuario, así que podría desactivar los triggers
  de `auditoria`. Crear un rol sin privilegios de dueño para el runtime y
  dejar al dueño solo para las migraciones.
- **Compose de producción.** Override sin `--reload` y sin montar el código
  (`./backend`), imagen sin herramientas de compilación, contenedor sin root.
- **Bloqueo de login deslizante.** Cada intento durante el bloqueo lo
  extiende 15 minutos más; decidir si se prefiere una duración fija.
- **Notas de Railway en el README:** volumen para `/uploads`, backups (el
  servicio `backup` no existe allí) y zona horaria del Postgres administrado.
- **Pin y SRI de los CDN** (Tailwind, htmx, Alpine).
- `/health/db` con mensaje genérico cuando `APP_ENV=production`.

## Para el módulo 02-B (pantallas de autenticación y usuarios)
- Página `/reset-password` (el mail de recuperación apunta ahí) con
  `Referrer-Policy: no-referrer`.
- Las páginas HTML no usan `get_current_user` tal cual (responde 401 JSON):
  necesitan su propia dependency que redirige a `/login` y manda a
  `/cambiar-password` si hay cambio pendiente. `requiere_permiso` sigue
  siendo la única barrera; las plantillas solo ocultan lo que no se puede.
- Nunca leer ni guardar en JavaScript los tokens del JSON de login: alcanza
  con las cookies HttpOnly.
- Cambios de estado solo por POST/PUT/PATCH/DELETE; si se aceptan formularios
  HTMX, agregar chequeo de Origin/Referer.
- El árbol de permisos y "Accesos permitidos" deben ofrecer solo lo que el
  autor puede otorgar y no mostrar la edición del propio usuario. Los dos
  escriben las mismas filas de `usuario_permisos`: dejar claro en la pantalla
  qué edita cada uno.

## Antes de que los módulos 03 y 04 usen mucho los componentes
- Accesibilidad del combobox (`aria-controls`, `aria-activedescendant`,
  label del buscador), foco atrapado en los modales, `:focus-visible` en
  las tarjetas de los hubs, y que el menú del usuario cierre con ESC.

## Cuando se toque el área
- Al iniciar sesión no se revoca la sesión anterior del mismo navegador
  (vence sola por inactividad).
- Las fechas de la API salen sin zona horaria (son hora del negocio,
  UTC-03:00): documentarlo en OpenAPI.
- `PUT /usuarios/{id}` con `rol_id: null` se ignora en silencio.
- El árbol y los accesos de un usuario inactivo muestran sus permisos como
  vigentes (la barrera real igual lo bloquea).
- `catalogo_accesos()` se reconstruye en cada llamada.
- `custom.css`: sombras y `.switch-perilla` con valores literales en vez de
  tokens.
- `formatearNumero` redondea si llegan más de 2 decimales (hoy la API
  siempre manda 2).
- `CAMPOS_SENSIBLES` solo filtra claves de primer nivel del snapshot.
- `mkdir(UPLOADS_DIR)` se ejecuta al importar `main.py` (falla fuera de
  Docker si `/uploads` no se puede escribir).
- Import no usado `timezone` en `tests/test_utils.py`.

## Verificación manual pendiente (navegador)
- Tema claro/oscuro sin recargar, cajón del sidebar debajo de 1024px, sin
  scroll horizontal de 320px a 1920px, y botones de al menos 44px en modo
  táctil.
