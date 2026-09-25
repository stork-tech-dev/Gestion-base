-- Datos iniciales del sistema. IDEMPOTENTE: se puede ejecutar N veces.
-- No usar el carácter de porcentaje en este archivo (lo ejecuta también psycopg2 en los tests).

-- Configuración del sistema (fila única).
INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta)
SELECT 1000.00, 100.00, 30.00, 50.00
WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema);
