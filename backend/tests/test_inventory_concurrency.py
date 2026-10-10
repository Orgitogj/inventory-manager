import threading
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.catalog.models import Category, Product
from app.inventory.models import MovementKind, StockLevel, StockMovement
from app.inventory.service import (
    InsufficientStockError,
    get_stock_quantity,
    lock_stock_level,
    record_movement,
)
from app.users.models import User, UserRole

pytestmark = pytest.mark.db


@pytest.fixture
def committed_product(db_engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, category_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with Session(db_engine) as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@shop.al",
                full_name="Ana",
                password_hash="not-a-real-hash",
                role=UserRole.WAREHOUSE,
            )
        )
        session.add(Category(id=category_id, name=f"Kategori {category_id}"))
        session.flush()
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
        record_movement(
            session,
            product_id=product_id,
            kind=MovementKind.RECEIPT,
            quantity=1,
            actor_id=user_id,
        )

    try:
        yield product_id, user_id
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(StockMovement.product_id == product_id)
            )
            connection.execute(
                delete(StockLevel).where(StockLevel.product_id == product_id)
            )
            connection.execute(delete(Product).where(Product.id == product_id))
            connection.execute(delete(Category).where(Category.id == category_id))
            connection.execute(delete(User).where(User.id == user_id))


def issue_one(session: Session, product_id: uuid.UUID, user_id: uuid.UUID) -> None:
    record_movement(
        session,
        product_id=product_id,
        kind=MovementKind.ISSUE,
        quantity=1,
        actor_id=user_id,
    )


def test_second_issue_waits_for_the_first_and_cannot_take_the_last_unit(
    db_engine, committed_product
):
    product_id, user_id = committed_product
    outcome: dict[str, object] = {}

    def second_worker() -> None:
        with Session(db_engine) as session, session.begin():
            try:
                issue_one(session, product_id, user_id)
                outcome["second"] = "ok"
            except InsufficientStockError as error:
                outcome["second"] = error

    with Session(db_engine) as first:
        first.begin()
        issue_one(first, product_id, user_id)

        worker = threading.Thread(target=second_worker)
        worker.start()
        worker.join(timeout=1)

        assert worker.is_alive(), "second issue should wait for the row lock"

        first.commit()

    worker.join(timeout=10)

    assert not worker.is_alive()
    assert isinstance(outcome["second"], InsufficientStockError)
    assert outcome["second"].available == 0

    with Session(db_engine) as session:
        assert get_stock_quantity(session, product_id) == 0


def test_reading_the_stock_row_locks_it_until_commit(db_engine, committed_product):
    product_id, _ = committed_product
    second_read: dict[str, int] = {}

    def second_reader() -> None:
        with Session(db_engine) as session, session.begin():
            second_read["quantity"] = lock_stock_level(session, product_id).quantity

    with Session(db_engine) as first:
        first.begin()
        stock = lock_stock_level(first, product_id)

        reader = threading.Thread(target=second_reader)
        reader.start()
        reader.join(timeout=1)

        assert reader.is_alive(), "a second reader must wait while the row is locked"

        stock.quantity = 0
        first.commit()

    reader.join(timeout=10)

    assert not reader.is_alive()
    assert second_read["quantity"] == 0
