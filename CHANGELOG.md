# Changelog

Cambios de Stork Gestión por versión. El detalle de cada módulo está en
`modulos/` y el plan de cada sesión en `docs/superpowers/`.

## [0.1.0] — 2026-10-08

Primera versión completa: los nueve módulos del spec más el tablero de inicio,
los gráficos de reportes y las mejoras de venta y productos.

### Infraestructura (01)
- Docker Compose con PostgreSQL 15, backend FastAPI y servicio `backup`
  (`pg_dump` diario con retención configurable).
- Migraciones Alembic escritas a mano y seed idempotente al arrancar.
- Auditoría append-only con triggers que bloquean UPDATE y DELETE.
- Layout responsive (sidebar fijo desde `lg`, cajón por debajo), modo oscuro y
  marca/paleta personalizables por cliente.

### Usuarios y permisos (02)
- Login con JWT + refresh token en cookies, cierre por inactividad, bloqueo
  por intentos fallidos y cambio de contraseña obligatorio al primer ingreso.
- Recuperación de contraseña por email (SMTP opcional).
- Roles Admin, Supervisor y Vendedor + roles personalizados con árbol de
  permisos; historial de accesos.

### Proveedores (03)
- ABM con moneda (pesos o dólares) y dólar propio de cada proveedor.
- Cambio de dólar individual, masivo y por Excel, con recálculo de precios.

### Productos (04)
- Categorías en árbol (hasta 5 niveles), SKU correlativo con dígito
  verificador y código de barras.
- Hasta 5 fotos por producto (subida o cámara) y etiquetas en PDF para Zebra.
- Precio por margen con redondeo hacia arriba, o precio de venta cargado a
  mano (exacto, el margen se calcula); leyenda del redondeo en el formulario.
- Fotos editables también desde "Editar".

### Stock (05)
- Ingresos, bajas con motivo y auditorías de inventario con ajuste automático.
- Todo movimiento pasa por `services.stock.aplicar_movimiento`; el stock nunca
  queda negativo, tampoco por ventas.

### Ventas y clientes (06)
- Clientes con condición IVA y CUIT validado.
- Pantalla de venta con lector de código y atajos F2 / F10 / ESC.
- Carrito por líneas con cantidad editable y tope de stock bloqueante.
- Descuentos por ítem con motivo, descuento general por % o total final, y
  promociones (2x1, 3x2, porcentaje; generales o exclusivas por cliente).
- Medios de pago con planes de cuotas y recargo; hasta 2 medios por venta.
- Anulación total con motivo; código de cambio de 4 caracteres.

### Caja (07)
- Turnos de caja (confirmar o anular una venta exige un turno abierto de hoy).
- Retiros de efectivo y arqueo por medio de pago al cerrar el turno.
- Notificación a los Admin cuando el arqueo da diferencias (campanita).

### Importación (08)
- Importación desde Excel de proveedores, clientes y productos (con
  categorías, stock inicial y mínimo), con validación previa y plantillas.

### Reportes (09)
- Ventas por período, medios de pago, vendedores, productos vendidos,
  rentabilidad y stock valorizado, cada uno con gráfico.
- Exportación a Excel y PDF.
- Tablero de inicio con estado de la caja, ventas de hoy, accesos rápidos y
  productos bajo el mínimo.

### Pendiente antes de la primera instalación real
Ver `docs/pendientes.md` → "Antes de la primera instalación real de un
cliente" (rol de base de datos separado, compose de producción, pin de los CDN,
entre otros).
