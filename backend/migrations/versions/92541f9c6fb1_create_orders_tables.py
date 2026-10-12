"""create orders tables

Revision ID: 92541f9c6fb1
Revises: 0262d60e7831
Create Date: 2026-10-12 01:22:19.809369

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "92541f9c6fb1"
down_revision: str | Sequence[str] | None = "0262d60e7831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "confirmed",
                "cancelled",
                name="order_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'draft' AND confirmed_at IS NULL AND cancelled_at IS NULL) OR (status = 'confirmed' AND confirmed_at IS NOT NULL AND cancelled_at IS NULL) OR (status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name=op.f("ck_orders_status_timestamps"),
        ),
        sa.CheckConstraint(
            "notes IS NULL OR (notes = btrim(notes) AND notes <> '')",
            name=op.f("ck_orders_notes_trimmed"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_orders_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_orders_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("number", name=op.f("uq_orders_number")),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)
    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_order_items_quantity_positive")
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name=op.f("ck_order_items_unit_price_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_order_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint(
            "order_id", "product_id", name="uq_order_items_order_product"
        ),
    )
    op.create_index(
        "ix_order_items_product_id", "order_items", ["product_id"], unique=False
    )
    op.add_column("stock_movements", sa.Column("order_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_stock_movements_order_id", "stock_movements", ["order_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_stock_movements_order_id_orders"),
        "stock_movements",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_stock_movements_order_id_orders"),
        "stock_movements",
        type_="foreignkey",
    )
    op.drop_index("ix_stock_movements_order_id", table_name="stock_movements")
    op.drop_column("stock_movements", "order_id")
    op.drop_index("ix_order_items_product_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
