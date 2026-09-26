-- Datos iniciales del sistema. IDEMPOTENTE: se puede ejecutar N veces.
-- Cada sesión agrega su bloque al final. Los bloques que dependen de tablas
-- de sesiones posteriores se protegen con to_regclass(...) IS NULL → RETURN.
-- No usar el carácter de porcentaje en este archivo (lo ejecuta también psycopg2 en los tests).

-- ===== Sesión 01 =====

-- Configuración del sistema (fila única).
INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta)
SELECT 1000.00, 100.00, 30.00, 50.00
WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema);

-- Motivos de baja de stock.
INSERT INTO motivos_baja (nombre) VALUES ('Rotura'), ('Robo'), ('Muestra'), ('Merma')
ON CONFLICT (nombre) DO NOTHING;

-- Marca de que el seed corrió (una sola vez).
INSERT INTO auditoria (usuario_id, accion, entidad, estado_nuevo)
SELECT NULL, 'sistema.seed', 'sistema', jsonb_build_object('sesion', '01')
WHERE NOT EXISTS (SELECT 1 FROM auditoria WHERE accion = 'sistema.seed');
