# SESIÓN 09 — Reportes
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 a 08 completadas y funcionando
- `ventas` (con estados `confirmada`/`anulada`), `venta_items` (con
  `costo_unitario`), `venta_pagos`, `planes_cuotas` (con `costo_medio`) y
  `productos` (con `stock`, `costo`) ya existentes
- `app/reports/pdf.py::imprimir` (WeasyPrint) ya implementado (sesión 04)

## OBJETIVO DE ESTA SESIÓN
Módulo de **Reportes** de solo lectura con seis reportes, cada uno consultable
en pantalla y exportable a **Excel** y **PDF**, construidos sobre un motor
único (definición del reporte → JSON, Excel y PDF sin código repetido).

## REGLAS COMUNES
- **Venta que cuenta** = estado `confirmada`, filtrada por `confirmada_en`.
  Las `anuladas` no suman en ningún reporte (el reporte de ventas por período
  las informa aparte). Las `en_curso` nunca aparecen.
- Fechas en hora del negocio; `desde`/`hasta` inclusivos (día completo).
  Default: **del primer día del mes actual a hoy**. Rango máximo: 366 días
  (409 si se excede).
- Importe vendido de una unidad = `venta_items.precio_final` (ya con
  descuentos y promociones). Los **recargos por cuotas** son financieros: se
  informan en su columna pero no entran en la rentabilidad.
- Costo de una unidad = `venta_items.costo_unitario` (congelado al vender).
- Toda agregación se hace en SQL (`GROUP BY`), nunca trayendo filas a Python.
- La API devuelve números crudos (Decimal como string en JSON, fechas ISO);
  el formato lo pone el frontend, el Excel o el PDF.

---

## LOS REPORTES

| Clave | Nombre | Agrupar por | Columnas |
|---|---|---|---|
| `ventas-periodo` | Ventas por período | `dia` \| `mes` | Período, Ventas, Unidades, Subtotal, Descuentos, Recargos, Total, Ticket promedio, Anuladas (cant.), Anuladas ($) |
| `medios-pago` | Ventas por medio de pago | medio + plan | Medio, Plan ("Un pago" / "N cuotas +X%"), Pagos, Monto, Recargo, Total cobrado, Costo del medio (estimado = total × `costo_medio`), Neto |
| `vendedores` | Ventas por vendedor | usuario | Vendedor, Ventas, Unidades, Total, Ticket promedio, Descuentos otorgados |
| `productos-vendidos` | Productos más vendidos | `producto` \| `categoria` (+ `nivel` 1-5) | Código, Descripción / Categoría (camino), Unidades, Importe vendido, % del total; orden por `unidades` \| `importe`; `limite` (default 50, máx 500) |
| `rentabilidad` | Rentabilidad | `dia` \| `mes` \| `categoria` (+ `nivel`) \| `proveedor` | Grupo, Unidades, Importe vendido, Costo, Ganancia bruta, Margen % (ganancia / importe) |
| `stock-valorizado` | Stock valorizado | `categoria` (+ `nivel`) \| `proveedor` | Grupo, Productos, Unidades, Valorizado a costo (`costo_en_pesos × stock`), Valorizado a venta (`precio_venta × stock`), Margen potencial |

Notas:
- `stock-valorizado` es una foto actual: no usa fechas. Solo productos
  activos, `stock > 0` y sin stock infinito.
- Agrupar por categoría con `nivel` N lleva cada producto al ancestro de
  nivel N de su rama (los de ramas más cortas quedan en su propia categoría).
- Todos los reportes admiten además `proveedor_id` y `categoria_id` (rama)
  como filtros opcionales, salvo `medios-pago` y `vendedores`, que admiten
  `usuario_id` / `medio_de_pago_id`.
- Cada reporte devuelve una fila de **totales** (en `margen %` y `ticket
  promedio` es el cálculo sobre los totales, no el promedio de las filas).

---

## BACKEND

### Motor — `/app/reports/motor.py`
- `Columna(clave, titulo, tipo)` con `tipo` ∈ `texto | entero | moneda |
  porcentaje | fecha | mes`.
- `DefinicionReporte(clave, nombre, descripcion, columnas, filtros_admitidos,
  consulta)`: `consulta(db, filtros) -> (filas, totales)`.
- Registro único `REPORTES = {clave: DefinicionReporte}`; cada reporte vive en
  `/app/reports/definiciones/<clave>.py` y solo aporta su consulta y sus
  columnas.
- `exportar_excel(definicion, filtros, filas, totales) -> bytes` (openpyxl:
  título, filtros aplicados, encabezados en negrita, formatos numéricos por
  `tipo`, fila de totales, anchos ajustados, panel congelado).
- `exportar_pdf(definicion, …) -> bytes` vía `templates/reports/reporte.html`
  (una sola plantilla para todos: marca del sistema, título, filtros, tabla,
  totales, fecha de emisión; A4 apaisado si hay más de 6 columnas).
- Schemas: `FiltrosReporte` (desde, hasta, agrupar, nivel, orden, limite,
  proveedor_id, categoria_id, usuario_id, medio_de_pago_id; cada reporte
  valida los que admite y rechaza con 422 los que no), `ReporteResponse`
  (`{clave, nombre, filtros, columnas, filas, totales, generado_en}`).

### Endpoints (`/api/v1/reportes`)
```
GET  ""                      → catálogo [{clave, nombre, descripcion, filtros_admitidos}]  [REPORTES ver]
GET  /{clave}                → ReporteResponse (JSON)                                      [REPORTES ver]
GET  /{clave}/excel          → reporte-<clave>-<desde>_<hasta>.xlsx (attachment)           [REPORTES ver]
GET  /{clave}/pdf            → PDF inline                                                  [REPORTES ver]
```
Los tres formatos reciben los mismos query params y usan la misma consulta.
Clave inexistente → 404. Auditoría: solo las exportaciones (`reporte.exportar`
con clave, formato y filtros); consultar en pantalla no audita.

Permisos (sesión 02): Admin y Supervisor `reportes` ver. El Vendedor no ve
reportes (la rentabilidad expone costos).

---

## FRONTEND

Sidebar: ítem **"Reportes"** (`/reportes`, módulo REPORTES ver), entre Caja y
Configuraciones.

### Hub `/reportes` (`pages/reportes/hub.html`, macro `hub`)
Una tarjeta por reporte del catálogo (nombre + descripción).

### `/reportes/{clave}` (`pages/reportes/reporte.html` + `static/js/reporte.js`)
**Una sola pantalla genérica** para los seis reportes, armada con las
`columnas` y `filtros_admitidos` que devuelve la API:
- Encabezado con el nombre del reporte y volver a "Reportes"; a la derecha
  botones **"Excel"** y **"PDF"** (con los filtros actuales).
- Filtros (tabla de alto volumen → botón **"Buscar"** explícito y "Limpiar
  filtros"): Desde/Hasta (default mes actual), "Agrupar por", Nivel de
  categoría, Orden/Límite, Proveedor y Categoría (combobox), Vendedor o Medio
  según el reporte. Solo se muestran los que el reporte admite.
- Tabla en tarjeta con formato por tipo de columna (`pesos()`, porcentaje con
  1 decimal, fechas dd/mm/aaaa, mes "mm/aaaa"), números alineados a la
  derecha, **fila de totales** fija al pie. Sin paginación (los reportes son
  agregados; `productos-vendidos` se acota con `limite`); scroll horizontal
  solo dentro de la tarjeta en pantallas chicas.
- Estado vacío: "No hay datos para los filtros elegidos."

---

## TESTS (`tests/test_reportes.py`)
Con un set de ventas armado en el test (confirmadas, anuladas, en curso, con
descuentos, promos y cuotas, de dos proveedores, uno en dólares):
- Las anuladas y en curso no suman; `ventas-periodo` informa las anuladas aparte.
- Rentabilidad = Σ precio_final − Σ costo_unitario; cambiar el costo o el dólar
  después de vender no cambia el reporte.
- Recargos fuera de la rentabilidad; costo del medio = total × `costo_medio`.
- Agrupar por categoría de nivel N suma las ramas correctamente.
- Totales calculados sobre totales (margen y ticket promedio).
- Excel y PDF se generan para cada reporte y el Excel tiene los mismos
  totales que el JSON.
- Rango > 366 días → 409; filtro no admitido → 422; sin `reportes` ver → 403.

---

## CRITERIOS DE ACEPTACIÓN
- Seis reportes consultables en pantalla y exportables a Excel y PDF.
- Un solo motor: agregar un reporte nuevo es escribir su consulta y sus
  columnas, sin tocar plantillas, exportadores ni pantalla.
- Solo cuentan ventas confirmadas; la rentabilidad usa el costo congelado de
  cada unidad vendida.
- Todas las agregaciones se resuelven en la base.
- El Vendedor no tiene acceso a Reportes por defecto.
