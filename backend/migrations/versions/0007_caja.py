"""Caja: turnos, retiros de efectivo, arqueos y notificaciones.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE estado_turno AS ENUM ('abierto', 'cerrado');
        CREATE TYPE tipo_notificacion AS ENUM ('diferencia_arqueo');

        CREATE TABLE turnos (
            id                  BIGSERIAL PRIMARY KEY,
            estado              estado_turno NOT NULL DEFAULT 'abierto',
            efectivo_apertura   NUMERIC(10,2) NOT NULL,
            usuario_apertura_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            usuario_cierre_id   BIGINT REFERENCES usuarios (id) ON DELETE RESTRICT,
            fecha_apertura      TIMESTAMP NOT NULL,
            fecha_cierre        TIMESTAMP,
            notas               TEXT,
            created_at          TIMESTAMP NOT NULL DEFAULT now(),
            updated_at          TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_turnos_efectivo_apertura CHECK (efectivo_apertura >= 0),
            -- Cerrado ⇔ tiene fecha y usuario de cierre.
            CONSTRAINT ck_turnos_cierre CHECK (
                (estado = 'cerrado') = (fecha_cierre IS NOT NULL AND usuario_cierre_id IS NOT NULL))
        );
        CREATE INDEX ix_turnos_estado ON turnos (estado);
        CREATE INDEX ix_turnos_fecha_apertura ON turnos (fecha_apertura);
        -- Nunca hay dos turnos abiertos a la vez (un único punto de venta).
        CREATE UNIQUE INDEX uq_turnos_un_abierto ON turnos ((true)) WHERE estado = 'abierto';

        -- FKs pendientes de la sesión 06 (las columnas ya existen, hoy NULL).
        ALTER TABLE ventas ADD CONSTRAINT fk_ventas_turno
            FOREIGN KEY (turno_id) REFERENCES turnos (id) ON DELETE RESTRICT;
        ALTER TABLE ventas ADD CONSTRAINT fk_ventas_turno_anulacion
            FOREIGN KEY (turno_anulacion_id) REFERENCES turnos (id) ON DELETE RESTRICT;

        CREATE TABLE turno_usuarios (
            id         BIGSERIAL PRIMARY KEY,
            turno_id   BIGINT NOT NULL REFERENCES turnos (id) ON DELETE RESTRICT,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            ingreso    TIMESTAMP NOT NULL,
            CONSTRAINT uq_turno_usuarios_turno_usuario UNIQUE (turno_id, usuario_id)
        );
        CREATE INDEX ix_turno_usuarios_turno_id ON turno_usuarios (turno_id);

        CREATE TABLE retiros_efectivo (
            id         BIGSERIAL PRIMARY KEY,
            turno_id   BIGINT NOT NULL REFERENCES turnos (id) ON DELETE RESTRICT,
            monto      NUMERIC(10,2) NOT NULL,
            motivo     VARCHAR(255) NOT NULL,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            timestamp  TIMESTAMP NOT NULL,
            CONSTRAINT ck_retiros_efectivo_monto CHECK (monto > 0)
        );
        CREATE INDEX ix_retiros_efectivo_turno_id ON retiros_efectivo (turno_id);

        -- Cómo se arquea cada medio (opcional por medio; sin pantalla: seed/SQL).
        CREATE TABLE medios_pago_arqueo_config (
            id                 BIGSERIAL PRIMARY KEY,
            medio_de_pago_id   BIGINT NOT NULL UNIQUE REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
            agrupa_en_terminal BOOLEAN NOT NULL DEFAULT FALSE,
            grupo_terminal     VARCHAR(60),
            es_informativo     BOOLEAN NOT NULL DEFAULT FALSE,   -- aparece pero no suma
            updated_at         TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_medios_pago_arqueo_config_grupo CHECK (NOT agrupa_en_terminal OR grupo_terminal IS NOT NULL)
        );

        CREATE TABLE arqueos (
            id                   BIGSERIAL PRIMARY KEY,
            turno_id             BIGINT NOT NULL UNIQUE REFERENCES turnos (id) ON DELETE RESTRICT,
            usuario_id           BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            total_esperado       NUMERIC(10,2) NOT NULL,
            total_declarado      NUMERIC(10,2) NOT NULL,
            diferencia           NUMERIC(10,2) GENERATED ALWAYS AS (total_declarado - total_esperado) STORED,
            notificacion_enviada BOOLEAN NOT NULL DEFAULT FALSE,
            created_at           TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE TABLE arqueo_items (
            id               BIGSERIAL PRIMARY KEY,
            arqueo_id        BIGINT NOT NULL REFERENCES arqueos (id) ON DELETE RESTRICT,
            medio_de_pago_id BIGINT REFERENCES medios_de_pago (id) ON DELETE RESTRICT,   -- NULL si es un grupo
            grupo_terminal   VARCHAR(60),
            monto_esperado   NUMERIC(10,2) NOT NULL,
            monto_declarado  NUMERIC(10,2) NOT NULL,
            diferencia       NUMERIC(10,2) GENERATED ALWAYS AS (monto_declarado - monto_esperado) STORED,
            es_informativo   BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT ck_arqueo_items_medio_o_grupo CHECK ((medio_de_pago_id IS NULL) <> (grupo_terminal IS NULL))
        );
        CREATE INDEX ix_arqueo_items_arqueo_id ON arqueo_items (arqueo_id);

        CREATE TABLE notificaciones (
            id         BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            tipo       tipo_notificacion NOT NULL,
            titulo     VARCHAR(200) NOT NULL,
            cuerpo     TEXT NOT NULL,
            leida      BOOLEAN NOT NULL DEFAULT FALSE,
            metadata   JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_notificaciones_usuario_id ON notificaciones (usuario_id);

        -- Decisión 1 del plan: Débito y Crédito salen en un solo cierre de lote.
        INSERT INTO medios_pago_arqueo_config (medio_de_pago_id, agrupa_en_terminal, grupo_terminal)
        SELECT id, TRUE, 'Clover/Payway' FROM medios_de_pago WHERE nombre IN ('Débito', 'Tarjeta de Crédito')
        ON CONFLICT (medio_de_pago_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE notificaciones;
        DROP TABLE arqueo_items;
        DROP TABLE arqueos;
        DROP TABLE medios_pago_arqueo_config;
        DROP TABLE retiros_efectivo;
        DROP TABLE turno_usuarios;
        ALTER TABLE ventas DROP CONSTRAINT fk_ventas_turno_anulacion;
        ALTER TABLE ventas DROP CONSTRAINT fk_ventas_turno;
        DROP TABLE turnos;
        DROP TYPE tipo_notificacion;
        DROP TYPE estado_turno;
        """
    )
