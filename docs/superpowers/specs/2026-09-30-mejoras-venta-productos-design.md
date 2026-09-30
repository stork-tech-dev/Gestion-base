# Mejoras de venta y productos: diseño

Cinco mejoras pedidas juntas. Rama `mejoras-venta-productos` desde `dev`.

## Decisiones (usuario)

- **A. Cantidad en la venta:** cantidad editable en el carrito (`[−] N [+]`, también se
  escribe). El descuento por producto se aplica a toda la fila. **Tope = stock, bloqueante**:
  no se puede superar el stock en ningún caso (ni con +, ni escribiendo, ni escaneando otra
  vez); los productos de stock infinito no tienen tope. Cambia la regla del módulo 06: una
  venta ya no puede dejar el stock en negativo.
- **B. Descuento general de la venta:** por % o por "total final" (ej. 83 → 80); **sin
  motivo**; tope = `tope_descuento_venta` % del total (configuración).
- **C. Precio de venta manual:** se puede cargar el precio en vez del margen; el precio
  manual **se respeta exacto** (sin redondeo) y se calcula el margen.
- **D. Redondeo visible:** junto al precio calculado, "Redondeado hacia arriba a múltiplos
  de $X" (el "bug" de que el precio no cambiaba al editar el costo era el redondeo de $1.000
  de la configuración, no un error de código).
- **E. Fotos al editar un producto:** agregar, tomar, marcar principal y borrar también
  desde "Editar".

## Decisiones técnicas

### A. Cantidad
- El modelo NO cambia: `venta_items` sigue siendo una fila por unidad (promos 3x2, costo
  congelado, reportes).
- **Línea** = unidades del mismo producto con el mismo descuento (`producto_id`,
  `descuento_item`, `motivo_descuento_id`). La respuesta de la venta suma `lineas`
  (en el orden de su primera unidad); `items` sigue igual.
- `PUT /ventas/{id}/items/{item_id}/cantidad {cantidad}` fija la cantidad de la línea del
  ítem: sube agregando unidades con el mismo descuento, baja quitando las últimas, 0 = quita
  la línea. Tope de sanidad 999 por pedido (stock infinito).
- Agregar (buscar/escanear) suma 1 unidad sin descuento: cae en la línea sin descuento del
  producto si existe.
- Stock: al agregar o subir la cantidad, 409 si las unidades del producto en la venta
  superan el stock ("Solo quedan N unidades de 'X'." / "No hay stock de 'X'."). Al confirmar,
  `aplicar_movimiento` sin `permitir_faltante`: con el producto bloqueado, 409 si otro vendió
  en el medio. Desaparece el aviso "Sin stock de…" (`aviso` se va de la respuesta de agregar).
- Descuento por línea: `POST /ventas/{id}/descuento` con el `item_id` de la línea descuenta
  todas sus unidades; 409 si alguna está en promoción. Líneas que quedan iguales se unen solas
  (misma clave).

### B. Descuento general
- Columna nueva `ventas.descuento_general NUMERIC(10,2) NOT NULL DEFAULT 0` (migración 0008):
  el MONTO, no el %.
- `_recalcular` lo reparte entre las unidades en proporción a su `precio_final` (después de
  promos y descuentos por ítem, antes del recargo), al centavo (resto al de mayor fracción).
  `precio_final` ya lo incluye: reportes, rentabilidad y `descuento_total` quedan bien sin
  tocarlos.
- `POST /ventas/{id}/descuento-general {porcentaje | total | ninguno (= quitar)}`, permiso
  `venta.descuento`, auditado (`venta.descuento_general`). Validaciones: total > 0 y ≤ al total
  actual; descuento ≤ `tope_descuento_venta` % del total sin descuento general.
- Se borra (vuelve a 0) al cambiar el carrito: agregar, quitar, cambiar cantidad, descuento
  por ítem, cliente o promoción elegida. Red de seguridad en `_recalcular`: si el monto queda
  mayor al tope o al total (ej. cambió una promo por medio de pago), vuelve a 0.
- La respuesta suma `descuento_general`.

### C/D. Precio manual y redondeo
- Alta y edición aceptan `margen` O `precio_venta` (uno de los dos; en el alta, ninguno =
  margen por defecto). Con `precio_venta`: el precio se guarda exacto y el margen =
  `(precio / costo_en_pesos − 1) × 100` con 2 decimales; 400 si el precio es menor al costo
  (margen negativo) o el margen supera 1000 %.
- Un cambio posterior de dólar o de costo recalcula el precio con ese margen y el redondeo
  (como cualquier producto).
- `GET /productos/precio-preview` acepta `margen` O `precio_venta` y devuelve además `margen`,
  `redondeo` y `redondeado` (true si el precio salió de la fórmula con redondeo).
- Formulario: "Margen %" y "Precio de venta" editables y vinculados (el último que se tocó
  manda); leyenda del redondeo cuando corresponde.

### E. Fotos
- El bloque de fotos de la ficha se extrae a una macro (`components/fotos_producto.html`) y un
  componente Alpine (`static/js/fotos_producto.js`) que usan la ficha y el modal de edición.
  En la edición las fotos se guardan al instante (se aclara en pantalla). Sin cambios de API.

## Fuera de alcance
- Cantidad en el campo de búsqueda (antes de agregar) o "3*código".
- Descuento por unidad dentro de una línea.
