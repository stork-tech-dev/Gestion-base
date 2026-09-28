"""Clientes, medios de pago, descuentos, promociones y ventas.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE SEQUENCE ventas_numero_seq START 1;
        CREATE TYPE condicion_iva AS ENUM ('consumidor_final', 'responsable_inscripto', 'monotributista', 'exento');
        CREATE TYPE tipo_promocion AS ENUM ('dos_x_uno', 'tres_x_dos', 'porcentaje');
        CREATE TYPE tipo_alcance_promocion AS ENUM ('producto', 'categoria', 'todos_productos', 'todos_categorias', 'medio_de_pago');
        CREATE TYPE estado_venta AS ENUM ('en_curso', 'confirmada', 'anulada');

        -- cuit y condicion_iva no se usan hoy en ningún cálculo: quedan cargados
        -- para la futura facturación electrónica.
        CREATE TABLE clientes (
            id            BIGSERIAL PRIMARY KEY,
            nombre        VARCHAR(150) NOT NULL,          -- nombre o razón social
            dni           VARCHAR(15) UNIQUE,             -- solo dígitos
            cuit          VARCHAR(11) UNIQUE,             -- solo dígitos, verificador válido (lo valida el service)
            condicion_iva condicion_iva NOT NULL DEFAULT 'consumidor_final',
            domicilio     VARCHAR(200),
            codigo_postal VARCHAR(10),
            localidad     VARCHAR(100),
            telefono      VARCHAR(30),
            email         VARCHAR(150),
            activo        BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP NOT NULL DEFAULT now(),
            updated_at    TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_clientes_cuit_fuera_de_cf CHECK (condicion_iva = 'consumidor_final' OR cuit IS NOT NULL)
        );

        CREATE TABLE medios_de_pago (
            id             BIGSERIAL PRIMARY KEY,
            nombre         VARCHAR(60) NOT NULL UNIQUE,
            soporta_cuotas BOOLEAN NOT NULL DEFAULT FALSE,
            es_efectivo    BOOLEAN NOT NULL DEFAULT FALSE,   -- el arqueo lo busca por esta marca, nunca por nombre
            activo         BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMP NOT NULL DEFAULT now(),
            updated_at     TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_medios_de_pago_efectivo_sin_cuotas CHECK (NOT (es_efectivo AND soporta_cuotas))
        );
        CREATE UNIQUE INDEX uq_medios_de_pago_efectivo ON medios_de_pago ((true)) WHERE es_efectivo;

        CREATE TABLE planes_cuotas (
            id               BIGSERIAL PRIMARY KEY,
            medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
            cuotas           SMALLINT NOT NULL,
            recargo_cliente  NUMERIC(5,2) NOT NULL DEFAULT 0,   -- % que paga el cliente (0 = sin interés)
            costo_medio      NUMERIC(5,2) NOT NULL DEFAULT 0,   -- % que cobra la terminal: SOLO reportes
            monto_minimo     NUMERIC(10,2) NOT NULL DEFAULT 0,
            activo           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMP NOT NULL DEFAULT now(),
            updated_at       TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_planes_cuotas_cuotas CHECK (cuotas >= 1),
            CONSTRAINT ck_planes_cuotas_recargo CHECK (recargo_cliente BETWEEN 0 AND 100),
            CONSTRAINT ck_planes_cuotas_costo CHECK (costo_medio BETWEEN 0 AND 100),
            CONSTRAINT ck_planes_cuotas_minimo CHECK (monto_minimo >= 0),
            CONSTRAINT uq_planes_cuotas UNIQUE (medio_de_pago_id, cuotas, recargo_cliente)
        );

        CREATE TABLE motivos_descuento (
            id                          BIGSERIAL PRIMARY KEY,
            nombre                      VARCHAR(100) NOT NULL UNIQUE,
            nota                        VARCHAR(500),
            porcentaje_sugerido         NUMERIC(5,2),   -- NULL = quien vende elige
            habilita_cuotas_sin_interes BOOLEAN NOT NULL DEFAULT FALSE,
            activo                      BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_inicio                DATE,
            fecha_fin                   DATE,
            created_at                  TIMESTAMP NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_motivos_descuento_sugerido CHECK (porcentaje_sugerido IS NULL OR (porcentaje_sugerido > 0 AND porcentaje_sugerido <= 100)),
            CONSTRAINT ck_motivos_descuento_fechas CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_inicio <= fecha_fin)
        );
        CREATE TABLE motivo_medios_pago (   -- vacío = todos los medios
            id               BIGSERIAL PRIMARY KEY,
            motivo_id        BIGINT NOT NULL REFERENCES motivos_descuento (id) ON DELETE CASCADE,
            medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
            CONSTRAINT uq_motivo_medios_pago UNIQUE (motivo_id, medio_de_pago_id)
        );

        CREATE TABLE promociones (
            id                   BIGSERIAL PRIMARY KEY,
            nombre               VARCHAR(100) NOT NULL UNIQUE,
            nota                 VARCHAR(500),
            tipo                 tipo_promocion NOT NULL,
            activo               BOOLEAN NOT NULL DEFAULT TRUE,
            porcentaje_descuento INTEGER,
            fecha_inicio         DATE,
            fecha_fin            DATE,
            created_at           TIMESTAMP NOT NULL DEFAULT now(),
            updated_at           TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_promociones_porcentaje CHECK (porcentaje_descuento IS NULL OR porcentaje_descuento BETWEEN 1 AND 75),
            CONSTRAINT ck_promociones_porcentaje_tipo CHECK ((tipo = 'porcentaje') = (porcentaje_descuento IS NOT NULL)),
            CONSTRAINT ck_promociones_fechas CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_inicio <= fecha_fin)
        );
        -- referencia_id no es FK: apunta a productos, categorías o medios según tipo_alcance
        -- (0 = "todos"). El service valida que exista.
        CREATE TABLE promocion_alcance (
            id            BIGSERIAL PRIMARY KEY,
            promocion_id  BIGINT NOT NULL REFERENCES promociones (id) ON DELETE CASCADE,
            tipo_alcance  tipo_alcance_promocion NOT NULL,
            referencia_id BIGINT NOT NULL,
            CONSTRAINT uq_promocion_alcance UNIQUE (promocion_id, tipo_alcance, referencia_id)
        );
        CREATE TABLE cliente_promociones (   -- promociones exclusivas de ciertos clientes
            id           BIGSERIAL PRIMARY KEY,
            cliente_id   BIGINT NOT NULL REFERENCES clientes (id) ON DELETE RESTRICT,
            promocion_id BIGINT NOT NULL REFERENCES promociones (id) ON DELETE CASCADE,
            CONSTRAINT uq_cliente_promociones UNIQUE (cliente_id, promocion_id)
        );
        CREATE INDEX ix_cliente_promociones_promocion_id ON cliente_promociones (promocion_id);

        -- Importes desnormalizados a propósito: son la foto del cierre; se recalculan
        -- mientras está en_curso y se congelan al confirmar.
        -- turno_id / turno_anulacion_id: la FK a turnos se agrega en la sesión 07.
        CREATE TABLE ventas (
            id                 BIGSERIAL PRIMARY KEY,
            numero             VARCHAR(12) NOT NULL UNIQUE,
            cliente_id         BIGINT REFERENCES clientes (id) ON DELETE RESTRICT,
            usuario_id         BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE RESTRICT,
            estado             estado_venta NOT NULL DEFAULT 'en_curso',
            subtotal           NUMERIC(10,2) NOT NULL DEFAULT 0,
            descuento_total    NUMERIC(10,2) NOT NULL DEFAULT 0,
            recargo_total      NUMERIC(10,2) NOT NULL DEFAULT 0,
            total              NUMERIC(10,2) NOT NULL DEFAULT 0,
            codigo_cambio      VARCHAR(8) UNIQUE,
            promocion_id       BIGINT REFERENCES promociones (id) ON DELETE RESTRICT,
            promocion_a_mano   BOOLEAN NOT NULL DEFAULT FALSE,   -- la eligió quien vende: dura hasta el próximo cambio del carrito
            confirmada_en      TIMESTAMP,
            turno_id           BIGINT,
            anulada_en         TIMESTAMP,
            anulada_por_id     BIGINT REFERENCES usuarios (id) ON DELETE RESTRICT,
            motivo_anulacion   VARCHAR(500),
            turno_anulacion_id BIGINT,
            created_at         TIMESTAMP NOT NULL DEFAULT now(),
            updated_at         TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT ck_ventas_importes CHECK (subtotal >= 0 AND descuento_total >= 0 AND recargo_total >= 0 AND total >= 0),
            CONSTRAINT ck_ventas_estado CHECK (
                (estado = 'en_curso'   AND codigo_cambio IS NULL AND confirmada_en IS NULL AND anulada_en IS NULL) OR
                (estado = 'confirmada' AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL AND anulada_en IS NULL) OR
                (estado = 'anulada'    AND codigo_cambio IS NOT NULL AND confirmada_en IS NOT NULL
                                       AND anulada_en IS NOT NULL AND anulada_por_id IS NOT NULL
                                       AND motivo_anulacion IS NOT NULL))
        );
        CREATE INDEX ix_ventas_cliente_id ON ventas (cliente_id);
        CREATE INDEX ix_ventas_usuario_id ON ventas (usuario_id);
        CREATE INDEX ix_ventas_estado ON ventas (estado);
        CREATE INDEX ix_ventas_confirmada_en ON ventas (confirmada_en);
        CREATE INDEX ix_ventas_turno_id ON ventas (turno_id);
        CREATE INDEX ix_ventas_turno_anulacion_id ON ventas (turno_anulacion_id);
        -- Nunca dos ventas en curso del mismo usuario (aun con dos pestañas).
        CREATE UNIQUE INDEX uq_ventas_en_curso_usuario ON ventas (usuario_id) WHERE estado = 'en_curso';

        -- Una fila por UNIDAD. precio_lista, precio_unitario y costo_unitario son la
        -- foto del momento de la venta (precio, costo y dólar cambian).
        CREATE TABLE venta_items (
            id                    BIGSERIAL PRIMARY KEY,
            venta_id              BIGINT NOT NULL REFERENCES ventas (id) ON DELETE CASCADE,
            producto_id           BIGINT NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
            precio_unitario       NUMERIC(10,2) NOT NULL,
            precio_lista          NUMERIC(10,2) NOT NULL,
            costo_unitario        NUMERIC(12,2) NOT NULL,
            descuento_item        NUMERIC(5,2) NOT NULL DEFAULT 0,
            motivo_descuento_id   BIGINT REFERENCES motivos_descuento (id) ON DELETE RESTRICT,
            porcentaje_modificado BOOLEAN NOT NULL DEFAULT FALSE,
            precio_final          NUMERIC(10,2) NOT NULL,
            en_promocion          BOOLEAN NOT NULL DEFAULT FALSE,
            orden                 SMALLINT NOT NULL,
            CONSTRAINT ck_venta_items_importes CHECK (precio_unitario >= 0 AND precio_lista >= 0 AND costo_unitario >= 0 AND precio_final >= 0),
            CONSTRAINT ck_venta_items_descuento CHECK (descuento_item BETWEEN 0 AND 100),
            CONSTRAINT ck_venta_items_motivo CHECK (descuento_item = 0 OR motivo_descuento_id IS NOT NULL),
            CONSTRAINT ck_venta_items_promo_sin_descuento CHECK (NOT (en_promocion AND descuento_item > 0))
        );
        CREATE INDEX ix_venta_items_venta_id ON venta_items (venta_id);
        CREATE INDEX ix_venta_items_producto_id ON venta_items (producto_id);

        CREATE TABLE venta_pagos (
            id               BIGSERIAL PRIMARY KEY,
            venta_id         BIGINT NOT NULL REFERENCES ventas (id) ON DELETE CASCADE,
            medio_de_pago_id BIGINT NOT NULL REFERENCES medios_de_pago (id) ON DELETE RESTRICT,
            plan_cuotas_id   BIGINT REFERENCES planes_cuotas (id) ON DELETE RESTRICT,
            monto            NUMERIC(10,2) NOT NULL,   -- antes del recargo
            recargo          NUMERIC(10,2) NOT NULL DEFAULT 0,
            monto_total      NUMERIC(10,2) NOT NULL,
            CONSTRAINT ck_venta_pagos_monto CHECK (monto > 0 AND recargo >= 0),
            CONSTRAINT ck_venta_pagos_total CHECK (monto_total = monto + recargo)
        );
        CREATE INDEX ix_venta_pagos_venta_id ON venta_pagos (venta_id);

        -- El índice de esta columna ya existe desde la sesión 05
        -- (ix_movimientos_stock_referencia_venta_id); acá solo se agrega la FK.
        ALTER TABLE movimientos_stock
            ADD CONSTRAINT fk_movimientos_stock_referencia_venta
            FOREIGN KEY (referencia_venta_id) REFERENCES ventas (id) ON DELETE RESTRICT;

        INSERT INTO medios_de_pago (nombre, es_efectivo, soporta_cuotas) VALUES
            ('Efectivo', TRUE, FALSE), ('Débito', FALSE, FALSE),
            ('Tarjeta de Crédito', FALSE, TRUE), ('Transferencia', FALSE, FALSE)
        ON CONFLICT (nombre) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE movimientos_stock DROP CONSTRAINT fk_movimientos_stock_referencia_venta;
        DROP TABLE venta_pagos;
        DROP TABLE venta_items;
        DROP TABLE ventas;
        DROP TABLE cliente_promociones;
        DROP TABLE promocion_alcance;
        DROP TABLE promociones;
        DROP TABLE motivo_medios_pago;
        DROP TABLE motivos_descuento;
        DROP TABLE planes_cuotas;
        DROP TABLE medios_de_pago;
        DROP TABLE clientes;
        DROP TYPE estado_venta;
        DROP TYPE tipo_alcance_promocion;
        DROP TYPE tipo_promocion;
        DROP TYPE condicion_iva;
        DROP SEQUENCE ventas_numero_seq;
        """
    )
