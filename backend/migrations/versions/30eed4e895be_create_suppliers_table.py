"""create suppliers table

Revision ID: 30eed4e895be
Revises: 708f94c7ba86
Create Date: 2026-10-09 23:23:56.107239

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "30eed4e895be"
down_revision: str | Sequence[str] | None = "708f94c7ba86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
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
        sa.CheckConstraint(
            "name = btrim(name) AND name <> ''", name=op.f("ck_suppliers_name_trimmed")
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(btrim(email))",
            name=op.f("ck_suppliers_email_normalized"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
    )
    op.create_index(
        "uq_suppliers_name_lower",
        "suppliers",
        [sa.literal_column("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_suppliers_name_lower", table_name="suppliers")
    op.drop_table("suppliers")
