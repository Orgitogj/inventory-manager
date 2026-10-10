import uuid

import pytest
from sqlalchemy import func, select

from app.catalog.models import Product
from app.catalog.schemas import CategoryCreate, ProductCreate
from app.catalog.service import create_category, create_product
from app.inventory.models import MovementKind, StockMovement
from app.inventory.service import (
    ArchivedProductError,
    InsufficientStockError,
    InvalidQuantityError,
    ProductNotFoundError,
    get_stock_quantity,
    record_movement,
)
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db


@pytest.fixture
def actor(db_session) -> User:
    return create_user(
        db_session,
        StaffCreate(
            email="ana@shop.al",
            full_name="Ana",
            password="long-enough-password",
            role=UserRole.WAREHOUSE,
        ),
    )


@pytest.fixture
def product(db_session) -> Product:
    category = create_category(db_session, CategoryCreate(name="Pije"))
    return create_product(
        db_session,
        ProductCreate(
            sku="UJE-05", name="Ujë 0.5L", category_id=category.id, unit_price="0.50"
        ),
    )


def move(db_session, product, actor, kind, quantity, reason=None) -> StockMovement:
    return record_movement(
        db_session,
        product_id=product.id,
        kind=kind,
        quantity=quantity,
        actor_id=actor.id,
        reason=reason,
    )


def count_movements(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(StockMovement))


def test_product_without_movements_has_zero_stock(db_session, product):
    assert get_stock_quantity(db_session, product.id) == 0


def test_receipt_increases_stock_and_records_history(db_session, product, actor):
    movement = move(db_session, product, actor, MovementKind.RECEIPT, 20)

    assert movement.quantity_change == 20
    assert movement.quantity_after == 20
    assert movement.created_by_id == actor.id
    assert get_stock_quantity(db_session, product.id) == 20


def test_issue_decreases_stock(db_session, product, actor):
    move(db_session, product, actor, MovementKind.RECEIPT, 20)

    movement = move(db_session, product, actor, MovementKind.ISSUE, 5)

    assert movement.quantity_change == -5
    assert movement.quantity_after == 15
    assert get_stock_quantity(db_session, product.id) == 15


def test_issue_can_take_the_last_unit(db_session, product, actor):
    move(db_session, product, actor, MovementKind.RECEIPT, 3)

    move(db_session, product, actor, MovementKind.ISSUE, 3)

    assert get_stock_quantity(db_session, product.id) == 0


def test_issue_beyond_stock_is_rejected_and_changes_nothing(db_session, product, actor):
    move(db_session, product, actor, MovementKind.RECEIPT, 3)

    with pytest.raises(InsufficientStockError) as error:
        move(db_session, product, actor, MovementKind.ISSUE, 4)

    assert error.value.available == 3
    assert error.value.requested == 4
    assert get_stock_quantity(db_session, product.id) == 3
    assert count_movements(db_session) == 1


@pytest.mark.parametrize(("change", "expected"), [(+2, 12), (-4, 6)])
def test_adjustment_moves_stock_in_either_direction(
    db_session, product, actor, change, expected
):
    move(db_session, product, actor, MovementKind.RECEIPT, 10)

    movement = move(
        db_session, product, actor, MovementKind.ADJUSTMENT, change, "Numërim fizik"
    )

    assert movement.quantity_change == change
    assert movement.reason == "Numërim fizik"
    assert get_stock_quantity(db_session, product.id) == expected


def test_adjustment_cannot_make_stock_negative(db_session, product, actor):
    move(db_session, product, actor, MovementKind.RECEIPT, 2)

    with pytest.raises(InsufficientStockError):
        move(db_session, product, actor, MovementKind.ADJUSTMENT, -3, "Dëmtim")


@pytest.mark.parametrize(
    ("kind", "quantity"),
    [
        (MovementKind.RECEIPT, 0),
        (MovementKind.RECEIPT, -5),
        (MovementKind.ISSUE, 0),
        (MovementKind.ISSUE, -5),
        (MovementKind.ADJUSTMENT, 0),
    ],
)
def test_invalid_quantities_are_rejected(db_session, product, actor, kind, quantity):
    with pytest.raises(InvalidQuantityError):
        move(db_session, product, actor, kind, quantity, "Arsye")

    assert count_movements(db_session) == 0


def test_unknown_product_is_rejected(db_session, actor):
    with pytest.raises(ProductNotFoundError):
        record_movement(
            db_session,
            product_id=uuid.uuid4(),
            kind=MovementKind.RECEIPT,
            quantity=1,
            actor_id=actor.id,
        )


def test_archived_product_is_rejected(db_session, product, actor):
    product.is_archived = True
    db_session.flush()

    with pytest.raises(ArchivedProductError):
        move(db_session, product, actor, MovementKind.RECEIPT, 1)
