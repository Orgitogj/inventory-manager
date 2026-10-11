import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import Product
from app.database import Base
from app.users.models import User


class MovementKind(enum.StrEnum):
    RECEIPT = "receipt"
    ISSUE = "issue"
    ADJUSTMENT = "adjustment"


class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_non_negative"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_change <> 0", name="quantity_change_not_zero"),
        CheckConstraint("quantity_after >= 0", name="quantity_after_non_negative"),
        CheckConstraint(
            "(kind = 'receipt' AND quantity_change > 0)"
            " OR (kind = 'issue' AND quantity_change < 0)"
            " OR kind = 'adjustment'",
            name="direction_matches_kind",
        ),
        CheckConstraint(
            "reason IS NULL OR (reason = btrim(reason) AND reason <> '')",
            name="reason_trimmed",
        ),
        CheckConstraint(
            "kind <> 'adjustment' OR reason IS NOT NULL",
            name="adjustment_has_reason",
        ),
        Index("ix_stock_movements_product_id_created_at", "product_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    kind: Mapped[MovementKind] = mapped_column(
        Enum(
            MovementKind,
            name="movement_kind",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda kinds: [kind.value for kind in kinds],
        )
    )
    quantity_change: Mapped[int]
    quantity_after: Mapped[int]
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    product: Mapped[Product] = relationship(lazy="joined", innerjoin=True)
    created_by: Mapped[User] = relationship(lazy="joined", innerjoin=True)
