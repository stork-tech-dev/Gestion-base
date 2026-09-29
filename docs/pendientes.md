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

## Módulo 05: pendientes
- Catálogos (árbol de categorías, proveedores) que dan 403 en `/stock` y en
  los conteos para un rol con STOCK ver pero sin PRODUCTOS ver (se ven dos
  toasts de error, uno por catálogo): agregar un flag `puede_ver_productos`
  al contexto de esas páginas y no pedir esas rutas cuando falta.
- Tests de concurrencia reales (dos `finalizar` o dos `iniciar` en paralelo,
  con conexiones/hilos separados) y tests JS (`node --test`) de `stock.js` y
  `auditorias.js`: hoy ninguno de los dos módulos tiene cobertura JS propia.

## Módulo 06: pendientes
- **`venta.descuento` se hereda del permiso general `ventas crear`**
  (`resolver_permiso` del módulo 02): quien puede vender también puede
  descontar; la casilla "Descuentos en ventas" del rol solo importa para
  roles sin `VENTAS crear`. Decisión del usuario: se deja así.
- El filtro Vendedor de `/ventas/resumen-ventas` sale de `GET /ventas/vendedores`
  (solo usuarios activos): la venta de un vendedor después desactivado sigue
  apareciendo en la tabla pero ya no se puede filtrar por él.
- Verificar a mano en el navegador la pantalla de venta (columna fija, selects
  de pagos, flujo de dos medios, F2/F10/ESC con lector de código).
- **Precio con descuento:** se redondea hacia abajo a múltiplos de $10
  (`services/descuentos.py::REDONDEO_DESCUENTO`), no al `redondeo` configurado,
  que sigue valiendo solo para los precios de lista. Decisión 13 del plan.
- `medios_pago.editar_plan` / `cambiar_estado_plan` no validan `medio.soporta_cuotas` (sin efecto en dinero: `planes_disponibles` devuelve [] y `registrar_pagos` rechaza).
- `schemas/clientes.py`: el fallback de `EmailStr` con try/except es código muerto; borrarlo cuando se toque el archivo.
- Faltan tests de `editar_plan` y del estado de un plan, de las auditorías de medios de pago, del email del cliente, de los filtros de `listar_clientes` y de los límites de `/clientes/buscar`.
- `test_clientes.py`: el filtro por localidad tiene una aserción débil (`total >= 1`); pasarla a `== 1` y verificar el nombre.
- `test_productos_alcanzados_solo_medio_de_pago_es_none` tiene mal el nombre (el alcance también tiene "todos los productos").
- Rendimiento de promociones: la ganadora se simula dos veces en `_recalcular` y `rama_de_ids` carga todas las categorías (con pocas promociones no se nota).
- `schemas/promociones.py`: la lista de alcances no tiene `max_length` (poner `max_length=200`).
- Quitar un descuento que no existía audita un no-op, y el porcentaje se ignora en silencio si `motivo_id` es None.
- `promociones_para_venta` puede mostrar un ahorro viejo (solo afecta lo que se muestra: `total_esperado` protege el cobro).
- `ventas.a_productos_venta` usa `rutas[p.categoria_id]`, con un KeyError teórico: pasar a `.get(…, "")`.
- `_campo` (schemas de ventas) acepta dicts y float solo para los tests.
- `compras_total` del cliente sale "0" en vez de "0.00" (cosmético: el JS formatea).
- Faltan tests de API de `/ventas/producto`, `/ventas/productos`, `/ventas/vendedores`, `/ventas/{id}/recalcular`, DELETE de ítem y de venta, etc.
- `GET /configuracion/promociones/catalogos` no tiene `response_model` (Principio 1, documentación de OpenAPI).
- DRY: `PAGINA_MAXIMA` repetida en 5 routers (y ahora también en `api/v1/turnos.py`, sesión 07; llevarla a `schemas/comunes.py`); `_validar_fechas` idéntica en `services/descuentos.py` y `services/promociones.py` (llevarla a `core/utils.py::validar_rango_fechas`); `textoONull` en 4 JS (pasar a `window.textoONull` en `app.js`); `celdaEstado` en 5 JS y `celdaNombre` en 2 (helpers globales `estadoActivoHtml` / `nombreConNotaHtml`); `CLASES_BADGE` de `app.js` duplica `FONDOS_BADGE` de `components/badge.html`.
- Ids de path mayores que BIGINT dan 500 (afecta a todo el proyecto, ya venía de antes).
- Comentarios imprecisos sobre el orden de rutas en `api/v1/ventas.py` y `api/v1/clientes.py:31`.
- Asignar una promoción general a un cliente (ficha del cliente) la vuelve exclusiva para todos sin avisar: pedir `confirmar()` antes y mostrar "Exclusiva" en el listado de promociones.
- `services/ventas.py::agregar_item` y `ProductoVenta.stock` leen `producto.stock` directo (igual que los módulos 04 y 05): sumar `services.stock.stock_de(producto)` como único accesor para multi-local.
- `elegir_promocion` acepta una promoción aplicable que no ahorra nada (la venta dice "elegida a mano" y no cambia nada).
- En la pantalla de venta, un monto con coma decimal ("5000,50") da un 422 genérico (hoy `type="number"` lo evita en la mayoría de los navegadores).

## Verificación manual pendiente (navegador)
- Tema claro/oscuro sin recargar, cajón del sidebar debajo de 1024px, sin
  scroll horizontal de 320px a 1920px, y botones de al menos 44px en modo
  táctil.

## Módulo 07 — fuera de alcance / para después
- Pantalla de configuración del arqueo por medio de pago (agrupación en
  terminal, informativos): hoy solo se edita por SQL directo
  (`medios_pago_arqueo_config`).
- Panel completo de notificaciones: hoy la campanita del header solo muestra
  las últimas 20 (lo que devuelve `GET /api/v1/notificaciones`), sin un
  listado propio ni filtros.
- `turno_para_operar` lee el id sin lock: si T1 se cierra y T2 se abre justo
  en el medio → 409 falso (reintentar alcanza).
- Rama savepoint + IntegrityError de `abrir_turno` sin test (necesita dos
  sesiones).
- Test de auditoría `turno.abierto` no verifica ip_origen/estado_nuevo.
- Diferencias por medio que se compensan (total 0) no notifican: coincide
  con el spec; decisión de producto a revisar.
- Grupo de terminal que mezcla medios informativos y no informativos: el
  flag sale del primer medio iterado (no determinístico). Validar
  consistencia cuando haya pantalla de configuración.
- La tabla Medio | Esperado | Declarado | Diferencia está armada a mano en
  `caja/index.html` y `caja/cerrar_turno.html`: candidata a macro.
- Comentario de orden de rutas innecesario en `api/v1/notificaciones.py`.
- Listado de turnos pagina de a 20 (lo pide el spec) mientras la regla
  general de UX es de a 10.

## Módulo 08: pendientes
- Mientras corre una importación o validación de productos (≈34 s con 5000
  filas) quedan bloqueados el árbol de categorías y los proveedores tocados:
  altas/ediciones manuales de productos y categorías y cambios de dólar
  esperan. Aceptable para la puesta en marcha; revisar si se usa en operación.
- `importacion.js`: si una importación confirmada se considerara "vieja" (cambio
  de pestaña o archivo en el medio), no se mostraría el toast de éxito. Hoy es
  inalcanzable porque las pestañas y el archivo se deshabilitan mientras corre.
- Falta un test con una celda float 2.5 en `stock_inicial` (el texto "2,5" sí
  está cubierto; el código la rechaza igual).
- Una categoría cuyo nombre contiene ">" no se puede referenciar por camino
  (la plantilla lo aclara).
- La zona de subida + tabla de errores se parece a la de
  `proveedores/dolar_masivo.html`: extraer macro si aparece un tercer uso.
- El primer commit del módulo (2df420b) tiene el trailer `Co-Authored-By`
  con otro modelo (no se enmendó).
