"""Stock de productos, movimientos y auditorías de inventario.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE productos
            ADD COLUMN stock        INTEGER NOT NULL DEFAULT 0,   -- solo lo escribe services.stock.aplicar_movimiento
            ADD COLUMN stock_minimo INTEGER NOT NULL DEFAULT 0,
            ADD CONSTRAINT ck_productos_stock_minimo CHECK (stock_minimo >= 0);

        CREATE TYPE tipo_movimiento_stock AS ENUM ('ingreso_proveedor', 'venta', 'anulacion_venta', 'baja', 'ajuste_auditoria');
        CREATE TYPE estado_auditoria_inventario AS ENUM ('en_curso', 'cerrada');

        CREATE TABLE auditorias_inventario (
            id                  BIGSERIAL PRIMARY KEY,
            usuario_id          BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            estado              estado_auditoria_inventario NOT NULL DEFAULT 'en_curso',
            filtro_categoria_id BIGINT REFERENCES categorias (id) ON DELETE RESTRICT,   -- informativo
            fecha_inicio        TIMESTAMP NOT NULL DEFAULT now(),
            fecha_fin           TIMESTAMP,
            notas               TEXT,
            created_at          TIMESTAMP NOT NULL DEFAULT now(),
            updated_at          TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_auditorias_inventario_estado ON auditorias_inventario (estado);
        CREATE INDEX ix_auditorias_inventario_fecha_inicio ON auditorias_inventario (fecha_inicio);
        -- Una sola auditoría en curso a la vez.
        CREATE UNIQUE INDEX uq_auditoria_inventario_en_curso ON auditorias_inventario ((true)) WHERE estado = 'en_curso';

        CREATE TABLE auditoria_items (
            id               BIGSERIAL PRIMARY KEY,
            auditoria_id     BIGINT NOT NULL REFERENCES auditorias_inventario (id) ON DELETE CASCADE,
            producto_id      BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
            cantidad_sistema INTEGER NOT NULL,        -- foto del stock AL REGISTRAR el ítem
            cantidad_contada INTEGER NOT NULL,
            diferencia       INTEGER GENERATED ALWAYS AS (cantidad_contada - cantidad_sistema) STORED,
            CONSTRAINT ck_auditoria_items_contada CHECK (cantidad_contada >= 0),
            CONSTRAINT uq_auditoria_items_producto UNIQUE (auditoria_id, producto_id)
        );
        CREATE INDEX ix_auditoria_items_producto_id ON auditoria_items (producto_id);

        -- Append-only en la práctica: los errores se corrigen con otro movimiento.
        CREATE TABLE movimientos_stock (
            id                  BIGSERIAL PRIMARY KEY,
            tipo                tipo_movimiento_stock NOT NULL,
            producto_id         BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
            cantidad            INTEGER NOT NULL,
            stock_resultante    INTEGER NOT NULL,
            motivo_baja_id      BIGINT REFERENCES motivos_baja (id) ON DELETE RESTRICT,
            auditoria_id        BIGINT REFERENCES auditorias_inventario (id) ON DELETE RESTRICT,
            referencia_venta_id BIGINT,                 -- la FK a ventas se agrega en la sesión 06
            usuario_id          BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            timestamp           TIMESTAMP NOT NULL DEFAULT now(),
            notas               TEXT,
            CONSTRAINT ck_movimientos_cantidad CHECK (cantidad <> 0),
            CONSTRAINT ck_movimientos_signo CHECK (
                (tipo IN ('ingreso_proveedor', 'anulacion_venta') AND cantidad > 0) OR
                (tipo IN ('venta', 'baja') AND cantidad < 0) OR
                (tipo = 'ajuste_auditoria')
            ),
            CONSTRAINT ck_movimientos_venta CHECK (tipo NOT IN ('venta', 'anulacion_venta') OR referencia_venta_id IS NOT NULL),
            CONSTRAINT ck_movimientos_baja CHECK (tipo <> 'baja' OR motivo_baja_id IS NOT NULL),
            CONSTRAINT ck_movimientos_ajuste CHECK (tipo <> 'ajuste_auditoria' OR auditoria_id IS NOT NULL)
        );
        CREATE INDEX ix_movimientos_stock_tipo ON movimientos_stock (tipo);
        CREATE INDEX ix_movimientos_stock_producto_id ON movimientos_stock (producto_id);
        CREATE INDEX ix_movimientos_stock_referencia_venta_id ON movimientos_stock (referencia_venta_id);
        CREATE INDEX ix_movimientos_stock_timestamp ON movimientos_stock (timestamp);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE movimientos_stock;
        DROP TABLE auditoria_items;
        DROP TABLE auditorias_inventario;
        DROP TYPE estado_auditoria_inventario;
        DROP TYPE tipo_movimiento_stock;
        ALTER TABLE productos
            DROP CONSTRAINT ck_productos_stock_minimo,
            DROP COLUMN stock_minimo,
            DROP COLUMN stock;
        """
    )
