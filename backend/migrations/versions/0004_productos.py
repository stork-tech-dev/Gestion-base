"""Categorías (árbol de 5 niveles), productos y sus fotos.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE categorias (
            id         BIGSERIAL PRIMARY KEY,
            nombre     VARCHAR(150) NOT NULL,
            nivel      SMALLINT NOT NULL,           -- desnormalizado a propósito (ver modelo)
            parent_id  BIGINT REFERENCES categorias (id) ON DELETE RESTRICT,
            orden      SMALLINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_categorias_nivel CHECK (nivel BETWEEN 1 AND 5),
            CONSTRAINT ck_categorias_padre CHECK (
                (nivel = 1 AND parent_id IS NULL) OR (nivel > 1 AND parent_id IS NOT NULL)
            )
        );
        CREATE INDEX ix_categorias_nombre ON categorias (nombre);
        CREATE INDEX ix_categorias_parent_id ON categorias (parent_id);
        CREATE UNIQUE INDEX uq_categorias_hermanos ON categorias (parent_id, nombre) NULLS NOT DISTINCT;

        CREATE TYPE temporada_producto AS ENUM ('atemporal', 'otoño_invierno', 'primavera_verano');
        -- Correlativo del SKU: nunca MAX()+1 (dos altas simultáneas chocarían).
        CREATE SEQUENCE productos_sku_seq START 1;

        CREATE TABLE productos (
            id                 BIGSERIAL PRIMARY KEY,
            sku                VARCHAR(5) NOT NULL,
            verificador        VARCHAR(1) NOT NULL,
            sku_proveedor      VARCHAR(30),
            descripcion        TEXT NOT NULL,
            categoria_id       BIGINT NOT NULL REFERENCES categorias (id) ON DELETE RESTRICT,
            proveedor_id       BIGINT NOT NULL REFERENCES proveedores (id) ON DELETE RESTRICT,
            costo              NUMERIC(10,2) NOT NULL,   -- en la moneda del proveedor
            margen             NUMERIC(6,2) NOT NULL,
            precio_venta       NUMERIC(10,2) NOT NULL,   -- en pesos; desnormalizado (ver modelo)
            descuento_producto NUMERIC(5,2) NOT NULL DEFAULT 0,
            peso_gramos        NUMERIC(8,2),
            temporada          temporada_producto NOT NULL DEFAULT 'atemporal',
            ubicacion_deposito VARCHAR(100),
            stock_infinito     BOOLEAN NOT NULL DEFAULT FALSE,
            activo             BOOLEAN NOT NULL DEFAULT TRUE,
            created_at         TIMESTAMP NOT NULL DEFAULT now(),
            updated_at         TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_productos_sku UNIQUE (sku),
            CONSTRAINT ck_productos_costo CHECK (costo > 0),
            CONSTRAINT ck_productos_margen CHECK (margen BETWEEN 0 AND 1000),
            CONSTRAINT ck_productos_precio CHECK (precio_venta >= 0),
            CONSTRAINT ck_productos_descuento CHECK (descuento_producto BETWEEN 0 AND 100),
            CONSTRAINT ck_productos_peso CHECK (peso_gramos IS NULL OR peso_gramos > 0)
        );
        CREATE INDEX ix_productos_sku_proveedor ON productos (sku_proveedor);
        CREATE INDEX ix_productos_categoria_id ON productos (categoria_id);
        CREATE INDEX ix_productos_proveedor_id ON productos (proveedor_id);
        CREATE INDEX ix_productos_temporada ON productos (temporada);
        CREATE INDEX ix_productos_activo ON productos (activo);
        CREATE INDEX ix_productos_descripcion_lower ON productos (lower(descripcion));
        -- Misma normalización que core/utils.sin_tildes_sql.
        CREATE UNIQUE INDEX uq_productos_descripcion_por_categoria_y_proveedor ON productos (
            lower(translate(descripcion, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')), categoria_id, proveedor_id
        );

        CREATE TABLE producto_fotos (
            id           BIGSERIAL PRIMARY KEY,
            producto_id  BIGINT NOT NULL REFERENCES productos (id) ON DELETE CASCADE,
            url          VARCHAR(255) NOT NULL,
            es_principal BOOLEAN NOT NULL DEFAULT FALSE,
            orden        SMALLINT NOT NULL DEFAULT 0,
            created_at   TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_producto_fotos_orden CHECK (orden >= 0)
        );
        CREATE INDEX ix_producto_fotos_producto_id ON producto_fotos (producto_id);
        CREATE UNIQUE INDEX uq_producto_fotos_principal ON producto_fotos (producto_id) WHERE es_principal;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE producto_fotos;
        DROP TABLE productos;
        DROP SEQUENCE productos_sku_seq;
        DROP TYPE temporada_producto;
        DROP TABLE categorias;
        """
    )
