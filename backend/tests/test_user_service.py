import pytest
from sqlalchemy import func, select

from app.auth.passwords import verify_password
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import EmailAlreadyExistsError, admin_exists, create_user

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"


def staff(**overrides) -> StaffCreate:
    data = {
        "email": "ana@example.com",
        "full_name": "Ana Hoxha",
        "password": PASSWORD,
        "role": UserRole.SALES,
    }
    data.update(overrides)
    return StaffCreate(**data)


def count_users(session) -> int:
    return session.scalar(select(func.count()).select_from(User))


def test_create_user_stores_normalized_email_and_verifiable_hash(db_session):
    user = create_user(db_session, staff(email="  Ana@Example.COM "))
    db_session.commit()

    stored = db_session.get(User, user.id)

    assert stored.email == "ana@example.com"
    assert stored.role is UserRole.SALES
    assert stored.password_hash != PASSWORD
    assert verify_password(stored.password_hash, PASSWORD)


def test_create_user_does_not_commit(db_session_factory):
    with db_session_factory() as session:
        create_user(session, staff())
        session.rollback()

        assert count_users(session) == 0


def test_duplicate_email_raises_domain_error_and_keeps_session_usable(db_session):
    create_user(db_session, staff())

    with pytest.raises(EmailAlreadyExistsError) as error:
        create_user(db_session, staff(email=" ANA@example.com", full_name="Other"))

    assert error.value.email == "ana@example.com"
    assert count_users(db_session) == 1


def test_admin_exists_only_after_an_admin_is_created(db_session):
    assert admin_exists(db_session) is False

    create_user(db_session, staff(role=UserRole.WAREHOUSE))
    assert admin_exists(db_session) is False

    create_user(db_session, staff(email="boss@example.com", role=UserRole.ADMIN))
    assert admin_exists(db_session) is True
