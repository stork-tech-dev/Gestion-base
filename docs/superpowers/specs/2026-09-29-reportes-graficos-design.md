# Gráficos en reportes: diseño

Cada reporte de `/reportes/{clave}` muestra un gráfico arriba de la tabla, dibujado
con los mismos datos que ya devuelve la API.

## Decisiones (usuario)

- **Chart.js por CDN** (versión fija, solo en la pantalla de reportes).
- **Solo en pantalla:** el Excel y el PDF no cambian.
- **Gráfico arriba, tabla abajo**, siempre visibles los dos.

## Decisiones técnicas

- `DefinicionReporte` suma `grafico(filtros) -> Grafico` (opcional). `Grafico(tipo,
  etiquetas, valor, titulo)`: `tipo` "linea" | "barras"; `etiquetas` = columnas que forman
  el nombre de cada punto/barra (se unen con " · "); `valor` = columna numérica;
  `titulo` = texto del encabezado del gráfico (como el `titulo` de las columnas).
- `ReporteResponse` suma `grafico: {tipo, etiquetas, valor, titulo} | null`. Los números
  salen de `filas`: no se duplican datos. Excel, PDF y endpoints no cambian.
- Una serie y un eje por gráfico (nunca doble eje); un solo color (`--color-primary`
  del tema), redibujado al cambiar claro/oscuro.
- Barras horizontales: las 10 primeras filas en el orden del reporte ("Top 10" si hay
  más; la tabla muestra todas). Línea: todos los puntos.
- Sin filas → sin gráfico. Tooltip con el mismo formato que la tabla. `<canvas
  role="img" aria-label=título>`; la tabla es la vista accesible.

## Gráfico de cada reporte

| Reporte | Tipo | Etiquetas | Valor | Título |
|---|---|---|---|---|
| ventas-periodo | línea | periodo | total | Total vendido por día / mes |
| medios-pago | barras | medio + plan | total_cobrado | Total cobrado por medio de pago |
| vendedores | barras | vendedor | total | Total vendido por vendedor |
| productos-vendidos | barras | descripcion / categoria | unidades o importe (según `orden`) | Unidades vendidas / Importe vendido por producto / categoría |
| rentabilidad | línea (día, mes) / barras (categoría, proveedor) | grupo | ganancia | Ganancia bruta por día / mes / categoría / proveedor |
| stock-valorizado | barras | grupo | valorizado_costo | Valorizado a costo por categoría / proveedor |
