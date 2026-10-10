import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.inventory.models import MovementKind, StockLevel, StockMovement


class ProductNotFoundError(Exception):
    def __init__(self, product_id: uuid.UUID) -> None:
        super().__init__(f"Product {product_id} does not exist.")
        self.product_id = product_id


class ArchivedProductError(Exception):
    def __init__(self, product_id: uuid.UUID) -> None:
        super().__init__(f"Product {product_id} is archived.")
        self.product_id = product_id


class InvalidQuantityError(Exception):
    def __init__(self, kind: MovementKind, quantity: int) -> None:
        super().__init__(f"Quantity {quantity} is not valid for a {kind} movement.")
        self.kind = kind
        self.quantity = quantity


class InsufficientStockError(Exception):
    def __init__(self, available: int, requested: int) -> None:
        super().__init__(
            f"Not enough stock: {available} available, {requested} requested."
        )
        self.available = available
        self.requested = requested


def signed_change(kind: MovementKind, quantity: int) -> int:
    if kind is MovementKind.ADJUSTMENT:
        if quantity == 0:
            raise InvalidQuantityError(kind, quantity)
        return quantity

    if quantity <= 0:
        raise InvalidQuantityError(kind, quantity)

    return quantity if kind is MovementKind.RECEIPT else -quantity


def lock_stock_level(session: Session, product_id: uuid.UUID) -> StockLevel:
    session.execute(
        insert(StockLevel)
        .values(product_id=product_id)
        .on_conflict_do_nothing(index_elements=[StockLevel.product_id])
    )
    return session.scalars(
        select(StockLevel)
        .where(StockLevel.product_id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def record_movement(
    session: Session,
    *,
    product_id: uuid.UUID,
    kind: MovementKind,
    quantity: int,
    actor_id: uuid.UUID,
    reason: str | None = None,
) -> StockMovement:
    change = signed_change(kind, quantity)
    product = session.get(Product, product_id)

    if product is None:
        raise ProductNotFoundError(product_id)

    if product.is_archived:
        raise ArchivedProductError(product_id)

    stock = lock_stock_level(session, product_id)
    new_quantity = stock.quantity + change

    if new_quantity < 0:
        raise InsufficientStockError(available=stock.quantity, requested=-change)

    stock.quantity = new_quantity
    movement = StockMovement(
        product_id=product_id,
        kind=kind,
        quantity_change=change,
        quantity_after=new_quantity,
        reason=reason,
        created_by_id=actor_id,
    )
    session.add(movement)
    session.flush()
    return movement


def get_stock_quantity(session: Session, product_id: uuid.UUID) -> int:
    quantity = session.scalar(
        select(StockLevel.quantity).where(StockLevel.product_id == product_id)
    )
    return quantity or 0
