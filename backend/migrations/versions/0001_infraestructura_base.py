"""Infraestructura base: auditoría inmutable, configuración del sistema y motivos de baja.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auditoria (
            id              BIGSERIAL PRIMARY KEY,
            usuario_id      BIGINT,                 -- NULL = sistema. Sin FK: el registro sobrevive al usuario
            accion          VARCHAR(100) NOT NULL,  -- "<entidad>.<verbo>"
            entidad         VARCHAR(100) NOT NULL,
            entidad_id      BIGINT,
            estado_anterior JSONB,
            estado_nuevo    JSONB,
            ip_origen       VARCHAR(45),
            timestamp       TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);
        CREATE INDEX ix_auditoria_accion ON auditoria (accion);
        CREATE INDEX ix_auditoria_entidad ON auditoria (entidad);
        CREATE INDEX ix_auditoria_timestamp ON auditoria (timestamp);
        CREATE INDEX ix_auditoria_entidad_entidad_id ON auditoria (entidad, entidad_id);

        -- Inmutabilidad (capa 1): triggers a nivel sentencia.
        CREATE FUNCTION auditoria_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla auditoria es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_auditoria_no_update BEFORE UPDATE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();
        CREATE TRIGGER trg_auditoria_no_delete BEFORE DELETE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();
        CREATE TRIGGER trg_auditoria_no_truncate BEFORE TRUNCATE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();

        -- Inmutabilidad (capa 2): defensa en profundidad. Si el rol es
        -- superusuario, lo que cuenta es el trigger.
        REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM CURRENT_USER;

        CREATE TABLE configuracion_sistema (
            id                   BIGSERIAL PRIMARY KEY,
            redondeo             NUMERIC(10,2) NOT NULL CHECK (redondeo >= 0),
            margen_default       NUMERIC(6,2)  NOT NULL CHECK (margen_default BETWEEN 0 AND 1000),
            descuento_maximo     NUMERIC(5,2)  NOT NULL CHECK (descuento_maximo BETWEEN 0 AND 100),
            tope_descuento_venta NUMERIC(5,2)  NOT NULL CHECK (tope_descuento_venta BETWEEN 0 AND 100),
            updated_at           TIMESTAMP NOT NULL DEFAULT now(),
            updated_by           BIGINT      -- FK a usuarios en la migración 0002
        );
        -- Fila única garantizada en la base.
        CREATE UNIQUE INDEX uq_configuracion_sistema_fila_unica ON configuracion_sistema ((true));

        CREATE TABLE motivos_baja (
            id     BIGSERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL UNIQUE,
            activo BOOLEAN NOT NULL DEFAULT TRUE
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE motivos_baja;
        DROP TABLE configuracion_sistema;
        DROP TABLE auditoria;
        DROP FUNCTION auditoria_bloquear_modificacion();
        """
    )
