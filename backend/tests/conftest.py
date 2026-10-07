from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from database_guard import (
    UnsafeTestDatabaseError,
    require_test_database_name,
    require_test_database_url,
)
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import BACKEND_DIR, Settings

SKIP_REASON = "TEST_DATABASE_URL is not set; database tests are skipped."


def get_test_database_url() -> str | None:
    return Settings().test_database_url or None


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if get_test_database_url():
        return

    skip_db = pytest.mark.skip(reason=SKIP_REASON)

    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    database_url = get_test_database_url()

    if not database_url:
        pytest.skip(SKIP_REASON)

    try:
        engine = create_engine(require_test_database_url(database_url))

        with engine.begin() as connection:
            require_test_database_name(
                connection.scalar(text("SELECT current_database()"))
            )

            alembic_config = Config(BACKEND_DIR / "alembic.ini")
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")
    except UnsafeTestDatabaseError as error:
        pytest.exit(str(error), returncode=1)

    yield engine

    engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    with db_engine.connect() as connection:
        transaction = connection.begin()

        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def db_session_factory(db_connection: Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = db_session_factory()

    try:
        yield session
    finally:
        session.close()
