"""create customers table

Revision ID: 0262d60e7831
Revises: 5c3e9a7d41b2
Create Date: 2026-10-11 23:15:39.749994

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0262d60e7831"
down_revision: str | Sequence[str] | None = "5c3e9a7d41b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
        sa.CheckConstraint(
            "name = btrim(name) AND name <> ''", name=op.f("ck_customers_name_trimmed")
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(btrim(email))",
            name=op.f("ck_customers_email_normalized"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    op.create_index(
        "ix_customers_name_lower",
        "customers",
        [sa.literal_column("lower(name)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customers_name_lower", table_name="customers")
    op.drop_table("customers")
