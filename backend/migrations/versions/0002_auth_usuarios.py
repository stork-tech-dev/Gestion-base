"""Autenticación y usuarios: roles, usuarios, permisos, historial de accesos y sesiones.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE roles (
            id          BIGSERIAL PRIMARY KEY,
            nombre      VARCHAR(50) NOT NULL UNIQUE,
            descripcion VARCHAR(255),
            es_sistema  BOOLEAN NOT NULL DEFAULT FALSE,   -- admin/supervisor/vendedor: no se borran ni renombran
            activo      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT now(),
            updated_at  TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE TABLE usuarios (
            id               BIGSERIAL PRIMARY KEY,
            username         VARCHAR(50) NOT NULL UNIQUE,
            email            VARCHAR(255) UNIQUE,
            password_hash    VARCHAR(255) NOT NULL,
            nombre           VARCHAR(150) NOT NULL,
            rol_id           BIGINT NOT NULL REFERENCES roles (id) ON DELETE RESTRICT,
            activo           BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_nacimiento DATE,
            celular          VARCHAR(20),
            created_at       TIMESTAMP NOT NULL DEFAULT now(),
            updated_at       TIMESTAMP NOT NULL DEFAULT now(),
            ultimo_acceso    TIMESTAMP              -- NULL = debe cambiar la contraseña
        );
        CREATE INDEX ix_usuarios_rol_id ON usuarios (rol_id);

        ALTER TABLE configuracion_sistema
            ADD CONSTRAINT fk_configuracion_sistema_updated_by
            FOREIGN KEY (updated_by) REFERENCES usuarios (id) ON DELETE SET NULL;

        -- NULLS NOT DISTINCT (PG15): sin él, las filas con recurso NULL se duplican
        -- y el ON CONFLICT del seed no hace nada.
        CREATE TABLE rol_permisos (
            id             BIGSERIAL PRIMARY KEY,
            rol_id         BIGINT NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
            modulo         VARCHAR(50) NOT NULL,
            recurso        VARCHAR(100),            -- NULL = módulo completo
            puede_ver      BOOLEAN NOT NULL DEFAULT FALSE,
            puede_crear    BOOLEAN NOT NULL DEFAULT FALSE,
            puede_editar   BOOLEAN NOT NULL DEFAULT FALSE,
            puede_eliminar BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_rol_permisos_rol_modulo_recurso UNIQUE NULLS NOT DISTINCT (rol_id, modulo, recurso)
        );

        -- Overrides individuales: siempre aditivos (OR con el rol).
        CREATE TABLE usuario_permisos (
            id             BIGSERIAL PRIMARY KEY,
            usuario_id     BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            modulo         VARCHAR(50) NOT NULL,
            recurso        VARCHAR(100),
            puede_ver      BOOLEAN NOT NULL DEFAULT FALSE,
            puede_crear    BOOLEAN NOT NULL DEFAULT FALSE,
            puede_editar   BOOLEAN NOT NULL DEFAULT FALSE,
            puede_eliminar BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_usuario_permisos_usuario_modulo_recurso UNIQUE NULLS NOT DISTINCT (usuario_id, modulo, recurso)
        );

        CREATE TYPE resultado_acceso AS ENUM ('exitoso', 'fallido');

        -- Append-only. Los usuarios nunca se borran (solo se desactivan), así que
        -- el ON DELETE CASCADE no choca con el trigger que bloquea DELETE.
        CREATE TABLE historial_accesos (
            id         BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            timestamp  TIMESTAMP NOT NULL DEFAULT now(),
            ip_origen  VARCHAR(45),
            resultado  resultado_acceso NOT NULL,
            detalle    VARCHAR(255)          -- motivo del fallo
        );
        CREATE INDEX ix_historial_accesos_usuario_timestamp ON historial_accesos (usuario_id, timestamp);

        CREATE FUNCTION historial_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla historial_accesos es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_historial_no_update BEFORE UPDATE ON historial_accesos
            FOR EACH STATEMENT EXECUTE FUNCTION historial_bloquear_modificacion();
        CREATE TRIGGER trg_historial_no_delete BEFORE DELETE ON historial_accesos
            FOR EACH STATEMENT EXECUTE FUNCTION historial_bloquear_modificacion();

        -- Refresh tokens emitidos: se guarda solo el jti.
        CREATE TABLE sesiones (
            id         BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            jti        VARCHAR(64) NOT NULL UNIQUE,
            creada_en  TIMESTAMP NOT NULL DEFAULT now(),
            expira_en  TIMESTAMP NOT NULL,   -- ventana de INACTIVIDAD deslizante, no el vencimiento del JWT
            revocada   BOOLEAN NOT NULL DEFAULT FALSE,
            ip_origen  VARCHAR(45)
        );
        CREATE INDEX ix_sesiones_usuario_id ON sesiones (usuario_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE sesiones;
        DROP TABLE historial_accesos;
        DROP FUNCTION historial_bloquear_modificacion();
        DROP TYPE resultado_acceso;
        DROP TABLE usuario_permisos;
        DROP TABLE rol_permisos;
        ALTER TABLE configuracion_sistema DROP CONSTRAINT fk_configuracion_sistema_updated_by;
        DROP TABLE usuarios;
        DROP TABLE roles;
        """
    )
