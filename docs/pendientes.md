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

## Módulo 02-B: pendientes que quedaron
- Roles sin paginación; filtros de usuarios solo por nombre, rol y estado;
  para no-admins el filtro de rol muestra solo "vendedor".
- Convención única para los filtros (placeholder o label) antes de 03-09.
- El token de recuperación viaja en la URL (queda en logs de acceso):
  evaluar pasarlo como fragmento `#token`.
- Advertencia de "el rol tiene usuarios" cuenta todos y no solo los activos.

## Módulo 03: pendientes
- Zip bomb: el límite de 5 MB de `leer_tabla` es sobre el .xlsx comprimido.
  Antes del módulo 08 (importación), sumar el `file_size` de
  `ZipFile.infolist()` y limitar lo descomprimido (ej. 50 MB).
- No hay macro de botón-link: `<a class="boton ...">` se repite en ~6
  plantillas.
- `importar_dolar` hace un `db.get` por fila (N+1): aceptable a esta escala;
  si crece, precargar los proveedores con un `IN`. Hacerlo con
  `SELECT … WHERE id IN (…) ORDER BY id FOR UPDATE` resuelve además el orden
  de los locks: hoy el masivo bloquea por nombre/id y el Excel fila por fila en
  el orden del archivo, así que ambos a la vez sobre proveedores cruzados
  pueden dar un deadlock (Postgres lo corta con un 500; sin datos corruptos).
- La pantalla de cambio masivo no tiene entrada en el hub para quien solo
  tiene el permiso puntual `dolar.cambio_masivo` (se entra por URL).

## Patrones que 03-09 deben copiar (de la revisión del 02-B)
- Páginas con `Depends(requiere_pagina(ITEM))`, con el ítem definido una vez
  y compartido por sidebar, hub y página; `resolver_permiso` solo para ocultar.
- Valores del servidor a Alpine solo con `|js` y solo en atributos.
- `x-html` solo con markup armado en JS y datos pasados por `escaparHtml` /
  `estadoHtml`; preferir `x-text`.
- Escrituras solo con `pedir()`; si algún día se usan formularios HTMX,
  agregar antes un chequeo de Origin/Referer.
- Formularios que cargan datos dependientes: bloquear el envío hasta que
  carguen y mandar la escritura dependiente solo si cambió algo.
- Listados con `ultimaRespuesta()`, `erroresDeCampos()` y `confirmar()`.
- Lógica de estado no trivial en JS: extraerla y testearla con `node --test`.

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

## Módulo 04: pendientes
- Decidir si el Vendedor (quien no edita productos) debe ver costo y margen:
  hoy los ve en la API (`GET /productos`, ficha), en el listado y en la ficha.
- `categoria.camino` llega como texto `"A > B"`; evaluar `list[str]` antes de
  que lo consuman los módulos 05 y 06.
- `archivo.unlink` de una foto borrada corre antes del commit del router: si
  el commit falla, queda la fila sin archivo.
- `URL.revokeObjectURL` del PDF de etiquetas corre a los 60 s: "Descargar"
  desde el visor de Chrome después de ese minuto puede fallar (imprimir no).
- `eliminar_categoria` no toma el lock del árbol: si se borra una categoría
  justo mientras otro la edita o la mueve, el `refresh` posterior al lock da
  500 en vez de 404 (muy improbable).
- Probar en el navegador (sobre todo Safari) la cámara real y la ventana
  emergente de etiquetas.

## Módulo 04: pendientes para el 05
- El módulo 05 agrega `stock`/`stock_minimo` y completa lo que el 04 dejó
  afuera a propósito: `stock_inicial` en el alta (ingreso de proveedor vía
  `services.stock.aplicar_movimiento`), columna Stock y `bajo_minimo` en el
  listado y la ficha, toggle "Stock 0" con checkboxes y "Desactivar
  seleccionados", y `stock_cero` en `listar_productos`. El formulario ya
  expone `productoFormUtil.stockEntero`.

## Verificación manual pendiente (navegador)
- Tema claro/oscuro sin recargar, cajón del sidebar debajo de 1024px, sin
  scroll horizontal de 320px a 1920px, y botones de al menos 44px en modo
  táctil.
