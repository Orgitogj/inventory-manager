"""create categories table

Revision ID: 708f94c7ba86
Revises: 72acfb9e581c
Create Date: 2026-10-09 15:24:54.599047

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "708f94c7ba86"
down_revision: str | Sequence[str] | None = "72acfb9e581c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "name = btrim(name) AND name <> ''", name=op.f("ck_categories_name_trimmed")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(
        "uq_categories_name_lower",
        "categories",
        [sa.literal_column("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_categories_name_lower", table_name="categories")
    op.drop_table("categories")
