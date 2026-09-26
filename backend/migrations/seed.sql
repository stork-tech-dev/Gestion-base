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

-- ===== Sesión 02: roles de sistema, usuario admin y permisos =====
DO $seed02$
BEGIN
    IF to_regclass('public.roles') IS NULL THEN
        RAISE NOTICE 'Sin tabla roles: se saltea el bloque de la sesión 02';
        RETURN;
    END IF;

    INSERT INTO roles (nombre, descripcion, es_sistema) VALUES
        ('admin', 'Acceso total al sistema', TRUE),
        ('supervisor', 'Gestión del local: ventas, clientes, caja y vendedores', TRUE),
        ('vendedor', 'Ventas y consulta de productos y stock', TRUE)
    ON CONFLICT (nombre) DO NOTHING;

    -- Contraseña inicial Admin1234! (bcrypt costo 12). ultimo_acceso NULL obliga a cambiarla.
    INSERT INTO usuarios (username, password_hash, nombre, rol_id)
    SELECT 'admin', '$2b$12$mi4/vU9mVGM0LXSk8uQ.hea/EX4edBSZ83NjqocvyD8paS5pus5I2', 'Administrador', r.id
    FROM roles r WHERE r.nombre = 'admin'
    ON CONFLICT (username) DO NOTHING;

    -- Permisos generales por módulo (recurso NULL): ver, crear, editar, eliminar.
    INSERT INTO rol_permisos (rol_id, modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar)
    SELECT r.id, p.modulo, NULL, p.v, p.c, p.e, p.x
    FROM (VALUES
        ('admin', 'clientes', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'proveedores', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'productos', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'stock', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'ventas', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'caja', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'configuracion', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'usuarios', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'auditoria', TRUE, FALSE, FALSE, FALSE),
        ('admin', 'importacion', FALSE, TRUE, FALSE, FALSE),
        ('admin', 'reportes', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'clientes', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'proveedores', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'productos', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'stock', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'ventas', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'caja', TRUE, TRUE, FALSE, FALSE),
        ('supervisor', 'usuarios', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'reportes', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'clientes', TRUE, TRUE, FALSE, FALSE),
        ('vendedor', 'productos', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'stock', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'ventas', TRUE, TRUE, FALSE, FALSE),
        ('vendedor', 'caja', TRUE, FALSE, FALSE, FALSE)
    ) AS p (rol, modulo, v, c, e, x)
    JOIN roles r ON r.nombre = p.rol
    ON CONFLICT (rol_id, modulo, recurso) DO NOTHING;

    -- Permisos por recurso puntual.
    INSERT INTO rol_permisos (rol_id, modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar)
    SELECT r.id, p.modulo, p.recurso, p.v, p.c, p.e, p.x
    FROM (VALUES
        ('supervisor', 'ventas', 'venta.descuento', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'ventas', 'venta.anular', FALSE, FALSE, FALSE, TRUE),
        ('supervisor', 'stock', 'stock.baja', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'stock', 'stock.auditoria', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'configuracion', 'configuracion.promociones', TRUE, TRUE, TRUE, FALSE),
        ('vendedor', 'ventas', 'venta.descuento', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'stock', 'stock.baja', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'stock', 'stock.auditoria', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'caja', 'caja.arqueo', FALSE, TRUE, FALSE, FALSE)
    ) AS p (rol, modulo, recurso, v, c, e, x)
    JOIN roles r ON r.nombre = p.rol
    ON CONFLICT (rol_id, modulo, recurso) DO NOTHING;
END
$seed02$;
