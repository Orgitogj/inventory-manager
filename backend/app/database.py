from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class DatabaseNotConfiguredError(RuntimeError):
    pass


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def violated_constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


@contextmanager
def translate_unique_violation(
    constraint: str, error_factory: Callable[[], Exception]
) -> Iterator[None]:
    try:
        yield
    except IntegrityError as error:
        if violated_constraint(error) == constraint:
            raise error_factory() from None
        raise


def build_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(database_url))


def get_db(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory

    if session_factory is None:
        raise DatabaseNotConfiguredError("Database is not configured.")

    session = session_factory()

    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
