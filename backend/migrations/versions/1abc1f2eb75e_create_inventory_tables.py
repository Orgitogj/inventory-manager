"""create inventory tables

Revision ID: 1abc1f2eb75e
Revises: eff5c24e4d5c
Create Date: 2026-10-10 22:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1abc1f2eb75e"
down_revision: str | Sequence[str] | None = "eff5c24e4d5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_levels",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0", name=op.f("ck_stock_levels_quantity_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_levels_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_stock_levels")),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "receipt",
                "issue",
                "adjustment",
                name="movement_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("quantity_change", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'receipt' AND quantity_change > 0) OR (kind = 'issue' AND quantity_change < 0) OR kind = 'adjustment'",
            name=op.f("ck_stock_movements_direction_matches_kind"),
        ),
        sa.CheckConstraint(
            "kind <> 'adjustment' OR reason IS NOT NULL",
            name=op.f("ck_stock_movements_adjustment_has_reason"),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR (reason = btrim(reason) AND reason <> '')",
            name=op.f("ck_stock_movements_reason_trimmed"),
        ),
        sa.CheckConstraint(
            "quantity_after >= 0",
            name=op.f("ck_stock_movements_quantity_after_non_negative"),
        ),
        sa.CheckConstraint(
            "quantity_change <> 0",
            name=op.f("ck_stock_movements_quantity_change_not_zero"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_stock_movements_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_movements_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index(
        "ix_stock_movements_product_id_created_at",
        "stock_movements",
        ["product_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stock_movements_product_id_created_at", table_name="stock_movements"
    )
    op.drop_table("stock_movements")
    op.drop_table("stock_levels")
