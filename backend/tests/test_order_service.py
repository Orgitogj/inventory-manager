import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.catalog.schemas import CategoryCreate, ProductCreate, ProductUpdate
from app.catalog.service import create_category, create_product, update_product
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.service import create_customer, update_customer
from app.database import violated_constraint
from app.inventory.models import MovementKind, StockMovement
from app.inventory.service import (
    ArchivedProductError,
    InsufficientStockError,
    get_stock_quantity,
    record_movement,
)
from app.orders.models import OrderStatus
from app.orders.schemas import OrderCreate, OrderItemsReplace, OrderUpdate
from app.orders.service import (
    ArchivedReferenceError,
    EmptyOrderError,
    InvalidReferenceError,
    OrderStateError,
    cancel_order,
    confirm_order,
    create_order,
    replace_items,
    update_order,
)
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

UNKNOWN_ID = uuid.UUID(int=0)


@pytest.fixture
def actor(db_session) -> User:
    return create_user(
        db_session,
        StaffCreate(
            email="shitje@shop.al",
            full_name="Shitësi",
            password="long-enough-password",
            role=UserRole.SALES,
        ),
    )


@pytest.fixture
def customer(db_session):
    return create_customer(db_session, CustomerCreate(name="Market Ana"))


@pytest.fixture
def category(db_session):
    return create_category(db_session, CategoryCreate(name="Pije"))


def add_product(db_session, category, sku: str, price: str, stock: int, actor):
    product = create_product(
        db_session,
        ProductCreate(sku=sku, name=sku, category_id=category.id, unit_price=price),
    )

    if stock:
        record_movement(
            db_session,
            product_id=product.id,
            kind=MovementKind.RECEIPT,
            quantity=stock,
            actor_id=actor.id,
        )

    return product


@pytest.fixture
def water(db_session, category, actor):
    return add_product(db_session, category, "UJE-05", "0.50", 10, actor)


@pytest.fixture
def juice(db_session, category, actor):
    return add_product(db_session, category, "LENG-1", "1.20", 5, actor)


def items(*pairs) -> list[dict]:
    return [{"product_id": product.id, "quantity": qty} for product, qty in pairs]


def new_order(db_session, customer, actor, *pairs, notes=None):
    return create_order(
        db_session,
        OrderCreate(customer_id=customer.id, notes=notes, items=items(*pairs)),
        actor.id,
    )


def order_movements(db_session, order) -> list[StockMovement]:
    return list(
        db_session.scalars(
            select(StockMovement)
            .where(StockMovement.order_id == order.id)
            .order_by(StockMovement.created_at)
        )
    )


def test_new_order_is_a_draft_with_a_number_and_price_snapshots(
    db_session, customer, actor, water, juice
):
    order = new_order(db_session, customer, actor, (water, 3), (juice, 1), notes=" ")

    assert order.status is OrderStatus.DRAFT
    assert order.number > 0
    assert order.notes is None
    assert order.customer.name == "Market Ana"
    assert order.created_by.id == actor.id
    assert [(item.product.sku, item.quantity) for item in order.items] == [
        ("UJE-05", 3),
        ("LENG-1", 1),
    ]
    assert [item.unit_price for item in order.items] == [
        Decimal("0.50"),
        Decimal("1.20"),
    ]
    assert get_stock_quantity(db_session, water.id) == 10


def test_order_numbers_increase(db_session, customer, actor, water):
    first = new_order(db_session, customer, actor, (water, 1))
    second = new_order(db_session, customer, actor, (water, 1))

    assert second.number > first.number


def test_price_change_does_not_touch_existing_lines(db_session, customer, actor, water):
    order = new_order(db_session, customer, actor, (water, 1))
    update_product(db_session, water, ProductUpdate(unit_price="0.80"))

    db_session.refresh(order)

    assert order.items[0].unit_price == Decimal("0.50")


@pytest.mark.parametrize("archived", [False, True])
def test_customer_must_exist_and_be_active(db_session, customer, actor, archived):
    if archived:
        update_customer(db_session, customer, CustomerUpdate(is_archived=True))
        expected, customer_id = ArchivedReferenceError, customer.id
    else:
        expected, customer_id = InvalidReferenceError, UNKNOWN_ID

    with pytest.raises(expected) as error:
        create_order(db_session, OrderCreate(customer_id=customer_id), actor.id)

    assert error.value.field == "customer_id"


def test_unknown_and_archived_products_are_reported_by_position(
    db_session, customer, actor, water, juice
):
    update_product(db_session, juice, ProductUpdate(is_archived=True))

    with pytest.raises(InvalidReferenceError) as unknown:
        create_order(
            db_session,
            OrderCreate(
                customer_id=customer.id,
                items=[
                    {"product_id": water.id, "quantity": 1},
                    {"product_id": UNKNOWN_ID, "quantity": 1},
                ],
            ),
            actor.id,
        )

    with pytest.raises(ArchivedReferenceError) as archived:
        new_order(db_session, customer, actor, (juice, 1))

    assert unknown.value.field == "items.1.product_id"
    assert archived.value.field == "items.0.product_id"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"items": [{"quantity": 1}]}, "items.0.product_id"),
        (
            {"items": [{"product_id": str(UNKNOWN_ID), "quantity": 0}]},
            "items.0.quantity",
        ),
        (
            {"items": [{"product_id": str(UNKNOWN_ID), "quantity": "2"}]},
            "items.0.quantity",
        ),
        ({"items": [{"product_id": str(UNKNOWN_ID), "quantity": 1}] * 2}, "items"),
        ({"items": [], "status": "confirmed"}, "status"),
        ({"notes": "x" * 1001}, "notes"),
    ],
)
def test_invalid_order_input_is_rejected(payload, field):
    with pytest.raises(ValidationError) as error:
        OrderCreate.model_validate({"customer_id": str(UNKNOWN_ID), **payload})

    assert [".".join(map(str, detail["loc"])) for detail in error.value.errors()] == [
        field
    ]


def test_draft_details_and_items_can_be_changed(
    db_session, customer, actor, water, juice
):
    other = create_customer(db_session, CustomerCreate(name="Bar Drini"))
    order = new_order(db_session, customer, actor, (water, 3), (juice, 1))

    update_order(db_session, order, OrderUpdate(customer_id=other.id, notes="Shpejt"))
    replace_items(db_session, order, OrderItemsReplace(items=items((juice, 2))))
    db_session.expire_all()

    assert order.customer.name == "Bar Drini"
    assert order.notes == "Shpejt"
    assert [(item.product.sku, item.quantity) for item in order.items] == [
        ("LENG-1", 2)
    ]


def test_items_can_be_replaced_with_the_same_products(
    db_session, customer, actor, water
):
    order = new_order(db_session, customer, actor, (water, 3))

    replace_items(db_session, order, OrderItemsReplace(items=items((water, 5))))

    assert [item.quantity for item in order.items] == [5]


def test_confirm_issues_stock_for_every_line(db_session, customer, actor, water, juice):
    order = new_order(db_session, customer, actor, (water, 3), (juice, 5))

    confirm_order(db_session, order, actor.id)

    assert order.status is OrderStatus.CONFIRMED
    assert order.confirmed_at is not None
    assert get_stock_quantity(db_session, water.id) == 7
    assert get_stock_quantity(db_session, juice.id) == 0
    movements = order_movements(db_session, order)
    assert sorted(movement.quantity_change for movement in movements) == [-5, -3]
    assert {movement.kind for movement in movements} == {MovementKind.ISSUE}
    assert {movement.reason for movement in movements} == {
        f"Order #{order.number} confirmed"
    }


def test_confirm_is_all_or_nothing(db_session, customer, actor, water, juice):
    order = new_order(db_session, customer, actor, (water, 3), (juice, 6))

    with pytest.raises(InsufficientStockError) as error:
        confirm_order(db_session, order, actor.id)

    assert error.value.product_id == juice.id
    assert error.value.available == 5
    assert error.value.requested == 6
    assert order.status is OrderStatus.DRAFT
    assert get_stock_quantity(db_session, water.id) == 10
    assert get_stock_quantity(db_session, juice.id) == 5
    assert order_movements(db_session, order) == []


def test_confirm_rejects_archived_products(db_session, customer, actor, water):
    order = new_order(db_session, customer, actor, (water, 1))
    update_product(db_session, water, ProductUpdate(is_archived=True))

    with pytest.raises(ArchivedProductError):
        confirm_order(db_session, order, actor.id)

    assert order.status is OrderStatus.DRAFT


def test_empty_order_cannot_be_confirmed(db_session, customer, actor):
    order = new_order(db_session, customer, actor)

    with pytest.raises(EmptyOrderError):
        confirm_order(db_session, order, actor.id)


def test_confirmed_order_is_locked(db_session, customer, actor, water):
    order = new_order(db_session, customer, actor, (water, 1))
    confirm_order(db_session, order, actor.id)

    with pytest.raises(OrderStateError):
        confirm_order(db_session, order, actor.id)

    with pytest.raises(OrderStateError):
        update_order(db_session, order, OrderUpdate(notes="Ndryshim"))

    with pytest.raises(OrderStateError):
        replace_items(db_session, order, OrderItemsReplace(items=items((water, 2))))

    assert get_stock_quantity(db_session, water.id) == 9


def test_cancelling_a_draft_does_not_touch_stock(db_session, customer, actor, water):
    order = new_order(db_session, customer, actor, (water, 4))

    cancel_order(db_session, order, actor.id)

    assert order.status is OrderStatus.CANCELLED
    assert order.cancelled_at is not None
    assert order.confirmed_at is None
    assert get_stock_quantity(db_session, water.id) == 10
    assert order_movements(db_session, order) == []


def test_cancelling_a_confirmed_order_returns_the_stock(
    db_session, customer, actor, water, juice
):
    order = new_order(db_session, customer, actor, (water, 3), (juice, 2))
    confirm_order(db_session, order, actor.id)

    cancel_order(db_session, order, actor.id)

    assert order.status is OrderStatus.CANCELLED
    assert order.confirmed_at is not None
    assert get_stock_quantity(db_session, water.id) == 10
    assert get_stock_quantity(db_session, juice.id) == 5
    kinds = [movement.kind for movement in order_movements(db_session, order)]
    assert sorted(kinds) == sorted(
        [MovementKind.ISSUE] * 2 + [MovementKind.RECEIPT] * 2
    )


def test_cancelled_order_cannot_change(db_session, customer, actor, water):
    order = new_order(db_session, customer, actor, (water, 1))
    cancel_order(db_session, order, actor.id)

    for action in (
        lambda: cancel_order(db_session, order, actor.id),
        lambda: confirm_order(db_session, order, actor.id),
        lambda: update_order(db_session, order, OrderUpdate(notes="x")),
    ):
        with pytest.raises(OrderStateError):
            action()


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "UPDATE orders SET status = 'confirmed' WHERE id = :id",
            "ck_orders_status_timestamps",
        ),
        (
            "UPDATE orders SET confirmed_at = now() WHERE id = :id",
            "ck_orders_status_timestamps",
        ),
        (
            "UPDATE orders SET status = 'shipped' WHERE id = :id",
            "ck_orders_order_status",
        ),
        (
            "UPDATE order_items SET quantity = 0 WHERE order_id = :id",
            "ck_order_items_quantity_positive",
        ),
        (
            "UPDATE order_items SET unit_price = -1 WHERE order_id = :id",
            "ck_order_items_unit_price_non_negative",
        ),
    ],
)
def test_database_rejects_invalid_order_rows(
    db_session, customer, actor, water, statement, constraint
):
    order = new_order(db_session, customer, actor, (water, 1))

    with pytest.raises(IntegrityError) as error:
        db_session.execute(text(statement), {"id": order.id})

    assert violated_constraint(error.value) == constraint
