"""Descuento general de la venta (monto que se reparte entre las unidades).

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ventas ADD COLUMN descuento_general NUMERIC(10,2) NOT NULL DEFAULT 0;
        ALTER TABLE ventas ADD CONSTRAINT ck_ventas_descuento_general CHECK (descuento_general >= 0);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ventas DROP COLUMN descuento_general;")
