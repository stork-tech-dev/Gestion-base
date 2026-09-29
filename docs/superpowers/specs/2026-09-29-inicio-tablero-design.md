# Tablero de inicio: diseño

La página `/` hoy solo saluda. Pasa a ser un tablero de "cómo va el día" con
cuatro bloques, cada uno visible según el permiso de quien entra.

## Decisiones (usuario)

- Bloques: **Caja**, **Ventas de hoy**, **Accesos rápidos** y **Stock bajo el mínimo**.
- "Ventas de hoy" **sin** comparación con la semana anterior (queda para después).

## Decisiones técnicas

- **Sin endpoint nuevo.** La página consume APIs que ya existen:
  `GET /api/v1/turnos/activo` (CAJA ver), `GET /api/v1/reportes/ventas-periodo?desde=hoy&hasta=hoy`
  (REPORTES ver) y `GET /api/v1/stock/alertas?limite=5` (STOCK ver).
- **Visibilidad en el servidor:** `pages.py::inicio` resuelve con `resolver_permiso` qué
  bloques se renderizan (misma barrera que la API): nunca se pide una API que daría 403.
- **Cada bloque carga por su cuenta** (componente Alpine propio): si uno falla muestra
  "No se pudo cargar." y los demás se ven igual. Sin toasts de error en el inicio.

## Bloques

1. **Caja** (CAJA ver: los tres roles).
   - Turno abierto de hoy: fecha y hora de apertura, quién lo abrió, efectivo inicial
     y cantidad de participantes; link "Ir a Caja".
   - Sin turno: "No hay un turno abierto." + botón "Iniciar turno" → `/caja` (el
     formulario ya vive ahí, no se duplica).
   - Turno de un día anterior sin cerrar: aviso en rojo ("Hay un turno del dd/mm/aaaa
     sin cerrar: no se puede vender hasta cerrarlo.") + link "Cerrar turno" →
     `/caja/cerrar/{id}` solo si el usuario tiene `caja.arqueo` crear.
2. **Ventas de hoy** (REPORTES ver: Admin y Supervisor). Fila de totales del reporte
   `ventas-periodo` de hoy: total vendido, ventas, ticket promedio y anuladas
   (cantidad · monto, o "Ninguna"). Link "Ver reporte" → `/reportes/ventas-periodo`.
3. **Accesos rápidos** (links armados en el servidor, cada uno con su permiso,
   reusando las constantes del sidebar/hubs): Nueva venta (o "Continuar venta
   V-000123" si el usuario tiene una en curso, misma regla que el hub de Ventas,
   extraída a un helper), Productos, Gestión de Stock, Caja.
4. **Stock bajo el mínimo** (STOCK ver: los tres roles). Los 5 productos más por debajo
   del mínimo (código, descripción, "stock / mín."). "Ver todos" →
   `/stock?solo_bajo_minimo=1`, que abre el listado de stock con ese filtro tildado
   (la ruta `/stock` acepta el query param y lo pasa a `stockListado`). Vacío: "Todo el
   stock está por encima del mínimo."

## Layout

Saludo; accesos rápidos en grilla (2 columnas en mobile, 4 desde `sm`); tarjetas de
bloques en grilla (1 columna, 2 desde `lg`). Mobile-first, áreas de toque de 44px.
