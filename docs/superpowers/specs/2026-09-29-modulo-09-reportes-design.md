# Módulo 09 — Reportes: diseño

Base: `modulos/09_reportes.md`. Este documento registra solo lo que el spec deja
abierto y las decisiones tomadas; en todo lo demás rige el spec.

## Decisiones de producto (usuario)

1. **Anuladas en `ventas-periodo`:** cuentan en el período de su `anulada_en`
   (no en el de `confirmada_en`). Coincide con la caja: el arqueo del turno en
   que se anuló ya la descontó.
2. **`ventas-periodo` no admite `proveedor_id` ni `categoria_id`** (422): trabaja
   con ventas enteras (subtotal, descuentos, recargos, ticket). Para ver por
   proveedor o categoría están `productos-vendidos` y `rentabilidad`.
3. **`stock-valorizado`:** dos columnas en lugar de "Margen potencial":
   "Ganancia potencial" (moneda = valorizado a venta − valorizado a costo) y
   "Margen potencial %" (ganancia / valorizado a venta, mismo criterio que
   Rentabilidad; en totales, sobre los totales).
4. **Costo del medio sin plan:** se deja como está. Un pago sin
   `plan_cuotas_id` sale con costo del medio 0 (si hace falta, se carga un
   plan de 1 cuota con su `costo_medio`). No se toca el módulo 06.

## Decisiones técnicas

- **Filas de `ventas-periodo`:** una por período con ventas confirmadas o
  anuladas (unión de ambos); los períodos sin movimiento no aparecen. Una fila
  que solo tiene anuladas muestra 0 ventas y ticket promedio 0.
- **Filtros admitidos por reporte:**

  | Reporte | Filtros (además de `desde`/`hasta` salvo stock) |
  |---|---|
  | `ventas-periodo` | `agrupar` (dia/mes) |
  | `medios-pago` | `medio_de_pago_id`, `usuario_id` |
  | `vendedores` | `usuario_id` |
  | `productos-vendidos` | `agrupar` (producto/categoria), `nivel`, `orden`, `limite`, `proveedor_id`, `categoria_id` |
  | `rentabilidad` | `agrupar` (dia/mes/categoria/proveedor), `nivel`, `proveedor_id`, `categoria_id` |
  | `stock-valorizado` | `agrupar` (categoria/proveedor), `nivel`, `proveedor_id`, `categoria_id` (sin fechas) |

  Un filtro no admitido que llega con valor → 422. `categoria_id` filtra por
  toda la rama (la categoría y sus descendientes).
- **Catálogos de filtros:** `GET /api/v1/reportes/opciones` (permiso
  `reportes` ver) devuelve `{proveedores, categorias (con camino y nivel),
  vendedores, medios_de_pago}` como referencias. Vendedores = usuarios con al
  menos una venta confirmada; vendedores y medios incluyen inactivos. Evita el
  403 de pedir catálogos de otros módulos (pendiente del módulo 05) y permite
  filtrar por un vendedor ya desactivado.
- **Etiqueta del plan** en `medios-pago`: "Un pago" o "N cuotas +X%", como
  texto de grupo (igual que el nombre del vendedor o el camino de categoría);
  los importes van crudos. Costo del medio = `monto_total × costo_medio / 100`
  por pago, sumado en SQL.
- **Costo en pesos en SQL** (`stock-valorizado`): `CASE moneda USD →
  ROUND(costo × dolar_actual, 2) ELSE costo`, mismo cálculo que
  `Producto.costo_en_pesos`. Solo productos activos, `stock > 0` y sin
  `stock_infinito`.
- **Categoría de nivel N:** CTE recursiva de ancestros; cada producto se lleva
  a su ancestro de nivel N, o a su propia categoría si su rama es más corta.
  La etiqueta del grupo es el camino ("A > B").
- **Totales:** calculados en SQL sobre el mismo conjunto filtrado (no suma de
  filas en Python); ticket promedio y margen % se derivan de los totales.
  División por cero → 0.
- **Excel:** `core/excel.py` gana la escritura de libro de reporte (título,
  filtros aplicados, encabezados en negrita, formato numérico por tipo, fila de
  totales, anchos, panel congelado) reusando `_textos_como_texto`; no se
  duplica `generar_tabla`.
- **PDF:** `templates/reports/reporte.html` única, vía `reports/pdf.py`;
  A4 apaisado con más de 6 columnas.
- **Auditoría:** `reporte.exportar` (entidad `reporte`, sin `entidad_id`,
  `estado_nuevo` = `{clave, formato, filtros}`) en las exportaciones Excel y PDF.
  Consultar en pantalla no audita.
- **Sin gráficos** en esta versión.

## Estructura

```
app/reports/motor.py                 Columna, DefinicionReporte, REPORTES, exportar_excel, exportar_pdf
app/reports/definiciones/<clave>.py  consulta + columnas de cada reporte
app/reports/definiciones/_comunes.py rango de fechas, ventas que cuentan, rama/nivel de categoría
app/schemas/reportes.py              FiltrosReporte, ReporteResponse, catálogo, opciones
app/api/v1/reportes.py               "", /opciones, /{clave}, /{clave}/excel, /{clave}/pdf
app/templates/reports/reporte.html
app/templates/pages/reportes/hub.html, reporte.html
app/static/js/reporte.js
tests/test_reportes.py, tests_js/reporte.test.js
```

## Plan de trabajo (rama `modulo-09-reportes`, desde `dev`)

1. Motor, schemas, router, exportadores, `/opciones` y `stock-valorizado`,
   con tests. **Con revisor** (dinero, permisos, auditoría).
2. Los cinco reportes de ventas con sus tests. **Con revisor** (dinero).
3. Frontend: hub, pantalla genérica, sidebar, test JS de formateadores. Sin
   revisor por tarea.

Cierre: revisión completa con Opus, una tanda de correcciones, merge a `dev`.
