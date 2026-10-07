import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.users.models import User, UserRole

pytestmark = pytest.mark.db

INSERT_USER = text(
    "INSERT INTO users (id, email, full_name, password_hash, role) "
    "VALUES (gen_random_uuid(), :email, 'Ana', 'not-a-real-hash', :role)"
)


def make_user(**overrides) -> User:
    data = {
        "email": "ana@example.com",
        "full_name": "Ana",
        "password_hash": "not-a-real-hash",
        "role": UserRole.SALES,
    }
    data.update(overrides)
    return User(**data)


def count_users(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User))


def violated_constraint(error: IntegrityError) -> str | None:
    return error.orig.diag.constraint_name


def test_user_is_stored_with_normalized_email_and_database_defaults(db_session):
    user = make_user(email="  Ana@Example.COM ", role=UserRole.WAREHOUSE)
    db_session.add(user)
    db_session.commit()

    row = db_session.execute(
        text("SELECT email, role, is_active, created_at FROM users WHERE id = :id"),
        {"id": user.id},
    ).one()

    assert row.email == "ana@example.com"
    assert row.role == "warehouse"
    assert row.is_active is True
    assert row.created_at.tzinfo is not None


def test_duplicate_email_is_rejected_even_with_different_case_and_spaces(db_session):
    db_session.add(make_user(email="ana@example.com"))
    db_session.commit()

    db_session.add(make_user(email="  ANA@Example.com "))

    with pytest.raises(IntegrityError) as error:
        db_session.commit()

    assert violated_constraint(error.value) == "uq_users_email"

    db_session.rollback()

    assert count_users(db_session) == 1


def test_raw_sql_with_unnormalized_email_is_rejected(db_session):
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT_USER, {"email": "Ana@x.com", "role": "sales"})

    assert violated_constraint(error.value) == "ck_users_email_normalized"
    assert count_users(db_session) == 0


def test_raw_sql_with_invalid_role_is_rejected(db_session):
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT_USER, {"email": "ana@x.com", "role": "ADMIN"})

    assert violated_constraint(error.value) == "ck_users_user_role"
    assert count_users(db_session) == 0
