import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.catalog.models import Category, Product
from app.customers.models import Customer
from app.inventory.models import MovementKind, StockLevel, StockMovement
from app.inventory.service import get_stock_quantity, lock_stock_level, record_movement
from app.orders.models import Order, OrderStatus
from app.orders.schemas import OrderCreate
from app.orders.service import OrderStateError, confirm_order, create_order, get_order
from app.users.models import User, UserRole

pytestmark = pytest.mark.db

WAIT_SECONDS = 10


@dataclass(frozen=True)
class Shop:
    user_id: uuid.UUID
    customer_id: uuid.UUID
    first_id: uuid.UUID
    second_id: uuid.UUID


@pytest.fixture
def shop(db_engine: Engine) -> Iterator[Shop]:
    user_id, customer_id, category_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first_id, second_id = sorted([uuid.uuid4(), uuid.uuid4()])
    product_ids = [first_id, second_id]

    with Session(db_engine) as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@shop.al",
                full_name="Ana",
                password_hash="not-a-real-hash",
                role=UserRole.SALES,
            )
        )
        session.add(Customer(id=customer_id, name="Market Ana"))
        session.add(Category(id=category_id, name=f"Kategori {category_id}"))
        session.flush()

        for product_id in product_ids:
            session.add(
                Product(
                    id=product_id,
                    sku=f"P-{product_id.hex[:12].upper()}",
                    name="Ujë",
                    category_id=category_id,
                    unit_price=1,
                )
            )
        session.flush()

        for product_id in product_ids:
            record_movement(
                session,
                product_id=product_id,
                kind=MovementKind.RECEIPT,
                quantity=10,
                actor_id=user_id,
            )

    try:
        yield Shop(user_id, customer_id, first_id, second_id)
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
            connection.execute(delete(Order).where(Order.customer_id == customer_id))
            connection.execute(
                delete(StockLevel).where(StockLevel.product_id.in_(product_ids))
            )
            connection.execute(delete(Product).where(Product.id.in_(product_ids)))
            connection.execute(delete(Category).where(Category.id == category_id))
            connection.execute(delete(Customer).where(Customer.id == customer_id))
            connection.execute(delete(User).where(User.id == user_id))


def committed_order(db_engine: Engine, shop: Shop, product_ids) -> uuid.UUID:
    with Session(db_engine) as session, session.begin():
        order = create_order(
            session,
            OrderCreate(
                customer_id=shop.customer_id,
                items=[
                    {"product_id": product_id, "quantity": 1}
                    for product_id in product_ids
                ],
            ),
            shop.user_id,
        )
        return order.id


def confirm_in_thread(db_engine: Engine, order_id, user_id, outcome: dict):
    def work() -> None:
        with Session(db_engine) as session, session.begin():
            try:
                confirm_order(session, get_order(session, order_id), user_id)
                outcome["result"] = "confirmed"
            except OrderStateError as error:
                outcome["result"] = error

    worker = threading.Thread(target=work)
    worker.start()
    return worker


def wait_until_blocked(db_engine: Engine) -> None:
    deadline = time.monotonic() + WAIT_SECONDS

    while time.monotonic() < deadline:
        with db_engine.connect() as connection:
            waiting = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )

        if waiting:
            return

        time.sleep(0.05)

    pytest.fail("the confirming transaction never waited for a lock")


def test_confirm_locks_stock_rows_in_product_order(db_engine, shop):
    order_id = committed_order(db_engine, shop, [shop.second_id, shop.first_id])
    outcome: dict[str, object] = {}

    with Session(db_engine) as blocker:
        blocker.begin()
        lock_stock_level(blocker, shop.first_id)

        worker = confirm_in_thread(db_engine, order_id, shop.user_id, outcome)
        wait_until_blocked(db_engine)

        second_row = blocker.scalars(
            select(StockLevel)
            .where(StockLevel.product_id == shop.second_id)
            .with_for_update(nowait=True)
        ).one()

        assert second_row.quantity == 10
        blocker.commit()

    worker.join(timeout=WAIT_SECONDS)

    assert not worker.is_alive()
    assert outcome["result"] == "confirmed"

    with Session(db_engine) as session:
        assert get_stock_quantity(session, shop.first_id) == 9
        assert get_stock_quantity(session, shop.second_id) == 9


def test_the_same_order_is_confirmed_only_once(db_engine, shop):
    order_id = committed_order(db_engine, shop, [shop.first_id, shop.second_id])
    outcome: dict[str, object] = {}

    with Session(db_engine) as first:
        first.begin()
        confirm_order(first, get_order(first, order_id), shop.user_id)

        worker = confirm_in_thread(db_engine, order_id, shop.user_id, outcome)
        wait_until_blocked(db_engine)

        first.commit()

    worker.join(timeout=WAIT_SECONDS)

    assert not worker.is_alive()
    assert isinstance(outcome["result"], OrderStateError)
    assert outcome["result"].status is OrderStatus.CONFIRMED

    with Session(db_engine) as session:
        issued = session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.order_id == order_id)
        )
        assert issued == 2
        assert get_stock_quantity(session, shop.first_id) == 9
