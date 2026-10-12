import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.customers.models import Customer
from app.inventory.models import MovementKind
from app.inventory.service import record_movement
from app.orders.models import Order, OrderItem, OrderStatus
from app.orders.schemas import OrderCreate, OrderItemIn, OrderItemsReplace, OrderUpdate


class InvalidReferenceError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__("Referenced record does not exist.")
        self.field = field


class ArchivedReferenceError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__("Referenced record is archived.")
        self.field = field


class OrderStateError(Exception):
    def __init__(self, status: OrderStatus, action: str) -> None:
        super().__init__(f"A {status} order cannot be {action}.")
        self.status = status
        self.action = action


class EmptyOrderError(Exception):
    def __init__(self) -> None:
        super().__init__("An order needs at least one item to be confirmed.")


def require_customer(session: Session, customer_id: uuid.UUID) -> Customer:
    customer = session.get(Customer, customer_id)

    if customer is None:
        raise InvalidReferenceError("customer_id")

    if customer.is_archived:
        raise ArchivedReferenceError("customer_id")

    return customer


def build_items(session: Session, items: list[OrderItemIn]) -> list[OrderItem]:
    product_ids = [item.product_id for item in items]
    products = {
        product.id: product
        for product in session.scalars(
            select(Product).where(Product.id.in_(product_ids))
        )
    }
    order_items = []

    for position, item in enumerate(items):
        field = f"items.{position}.product_id"
        product = products.get(item.product_id)

        if product is None:
            raise InvalidReferenceError(field)

        if product.is_archived:
            raise ArchivedReferenceError(field)

        order_items.append(
            OrderItem(
                product_id=product.id,
                position=position,
                quantity=item.quantity,
                unit_price=product.unit_price,
            )
        )

    return order_items


def require_status(order: Order, action: str, *allowed: OrderStatus) -> None:
    if order.status not in allowed:
        raise OrderStateError(order.status, action)


def create_order(session: Session, data: OrderCreate, actor_id: uuid.UUID) -> Order:
    require_customer(session, data.customer_id)
    order = Order(
        customer_id=data.customer_id,
        notes=data.notes,
        created_by_id=actor_id,
        items=build_items(session, data.items),
    )
    session.add(order)
    session.flush()
    return order


def get_order(session: Session, order_id: uuid.UUID) -> Order | None:
    return session.get(Order, order_id)


def lock_order(session: Session, order_id: uuid.UUID) -> Order | None:
    return session.scalars(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update(of=Order)
        .execution_options(populate_existing=True)
    ).one_or_none()


def update_order(session: Session, order: Order, data: OrderUpdate) -> Order:
    require_status(order, "edited", OrderStatus.DRAFT)
    changes = data.model_dump(exclude_unset=True)

    if "customer_id" in changes and changes["customer_id"] != order.customer_id:
        require_customer(session, changes["customer_id"])

    for field, value in changes.items():
        setattr(order, field, value)

    session.flush()
    session.expire(order, ["customer"])
    return order


def replace_items(session: Session, order: Order, data: OrderItemsReplace) -> Order:
    require_status(order, "edited", OrderStatus.DRAFT)
    new_items = build_items(session, data.items)
    order.items.clear()
    session.flush()
    order.items.extend(new_items)
    order.updated_at = func.now()
    session.flush()
    return order


def movement_reason(order: Order, action: str) -> str:
    return f"Order #{order.number} {action}"


def sorted_items(order: Order) -> list[OrderItem]:
    return sorted(order.items, key=lambda item: item.product_id)


def confirm_order(session: Session, order: Order, actor_id: uuid.UUID) -> Order:
    order = lock_order(session, order.id)
    require_status(order, "confirmed", OrderStatus.DRAFT)

    if not order.items:
        raise EmptyOrderError

    with session.begin_nested():
        for item in sorted_items(order):
            record_movement(
                session,
                product_id=item.product_id,
                kind=MovementKind.ISSUE,
                quantity=item.quantity,
                actor_id=actor_id,
                reason=movement_reason(order, "confirmed"),
                order_id=order.id,
            )

        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = func.now()
        session.flush()

    session.refresh(order)
    return order


def cancel_order(session: Session, order: Order, actor_id: uuid.UUID) -> Order:
    order = lock_order(session, order.id)
    require_status(order, "cancelled", OrderStatus.DRAFT, OrderStatus.CONFIRMED)

    with session.begin_nested():
        if order.status is OrderStatus.CONFIRMED:
            for item in sorted_items(order):
                record_movement(
                    session,
                    product_id=item.product_id,
                    kind=MovementKind.RECEIPT,
                    quantity=item.quantity,
                    actor_id=actor_id,
                    reason=movement_reason(order, "cancelled"),
                    order_id=order.id,
                )

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = func.now()
        session.flush()

    session.refresh(order)
    return order
