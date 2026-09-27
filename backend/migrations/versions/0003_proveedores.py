"""Proveedores (en pesos o en dólares) e historial inmutable del dólar.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE estado_proveedor AS ENUM ('activo', 'desactivado', 'inhabilitado');
        CREATE TYPE moneda AS ENUM ('ars', 'usd');
        CREATE TYPE origen_cambio_dolar AS ENUM ('manual', 'masivo_valor', 'masivo_porcentaje', 'importacion_excel');

        CREATE TABLE proveedores (
            id           BIGSERIAL PRIMARY KEY,
            nombre       VARCHAR(200) NOT NULL,
            pais         VARCHAR(200),
            provincia    VARCHAR(255),
            telefono     VARCHAR(50),
            email        VARCHAR(255),
            notas        TEXT,
            estado       estado_proveedor NOT NULL DEFAULT 'activo',
            moneda       moneda NOT NULL DEFAULT 'ars',
            dolar_actual NUMERIC(10,2),          -- solo proveedores en dólares
            created_at   TIMESTAMP NOT NULL DEFAULT now(),
            updated_at   TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_proveedores_moneda_dolar CHECK (
                (moneda = 'ars' AND dolar_actual IS NULL) OR
                (moneda = 'usd' AND dolar_actual IS NOT NULL AND dolar_actual > 0)
            )
        );
        CREATE INDEX ix_proveedores_nombre ON proveedores (nombre);
        CREATE INDEX ix_proveedores_estado ON proveedores (estado);
        CREATE INDEX ix_proveedores_moneda ON proveedores (moneda);
        -- Nombre único sin distinguir mayúsculas ni tildes (la importación
        -- del módulo 08 identifica proveedores por nombre).
        CREATE UNIQUE INDEX uq_proveedores_nombre
            ON proveedores (lower(translate(nombre, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')));

        CREATE TABLE proveedor_dolar_historial (
            id             BIGSERIAL PRIMARY KEY,
            proveedor_id   BIGINT NOT NULL REFERENCES proveedores (id) ON DELETE CASCADE,
            valor_anterior NUMERIC(10,2) NOT NULL,
            valor_nuevo    NUMERIC(10,2) NOT NULL,
            usuario_id     BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            origen         origen_cambio_dolar NOT NULL,
            timestamp      TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_proveedor_dolar_historial_proveedor_id ON proveedor_dolar_historial (proveedor_id);
        CREATE INDEX ix_proveedor_dolar_historial_timestamp ON proveedor_dolar_historial (timestamp);

        -- Append-only (los proveedores nunca se borran: baja lógica).
        CREATE FUNCTION proveedor_dolar_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla proveedor_dolar_historial es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_proveedor_dolar_no_update BEFORE UPDATE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        CREATE TRIGGER trg_proveedor_dolar_no_delete BEFORE DELETE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        CREATE TRIGGER trg_proveedor_dolar_no_truncate BEFORE TRUNCATE ON proveedor_dolar_historial
            FOR EACH STATEMENT EXECUTE FUNCTION proveedor_dolar_bloquear_modificacion();
        REVOKE UPDATE, DELETE, TRUNCATE ON proveedor_dolar_historial FROM CURRENT_USER;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE proveedor_dolar_historial;
        DROP FUNCTION proveedor_dolar_bloquear_modificacion();
        DROP TABLE proveedores;
        DROP TYPE origen_cambio_dolar;
        DROP TYPE moneda;
        DROP TYPE estado_proveedor;
        """
    )
