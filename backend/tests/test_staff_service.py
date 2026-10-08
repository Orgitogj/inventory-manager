import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app.auth.models import UserSession
from app.auth.service import start_session
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate, StaffUpdate
from app.users.service import (
    LastAdminError,
    SelfModificationError,
    create_user,
    get_user,
    list_users,
    update_user,
)

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
LIFETIME = timedelta(hours=1)


def add_user(session, email: str, role: UserRole, is_active: bool = True) -> User:
    user = create_user(
        session,
        StaffCreate(email=email, full_name="Staff", password=PASSWORD, role=role),
    )
    user.is_active = is_active
    session.flush()
    return user


def count_sessions(session, user: User) -> int:
    return session.scalar(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.user_id == user.id)
    )


def test_list_users_is_ordered_by_created_at(db_session):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    emails = ["c@shop.al", "a@shop.al", "b@shop.al"]

    for position, email in enumerate(emails):
        user = add_user(db_session, email, UserRole.SALES)
        user.created_at = start + timedelta(days=position)

    db_session.flush()

    assert [user.email for user in list_users(db_session)] == emails


def test_get_user_returns_the_user_or_none(db_session):
    user = add_user(db_session, "ana@shop.al", UserRole.SALES)

    assert get_user(db_session, user.id) is user
    assert get_user(db_session, uuid.uuid4()) is None


def test_update_changes_only_the_given_fields(db_session):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    user = add_user(db_session, "ana@shop.al", UserRole.SALES)

    update_user(db_session, admin, user, StaffUpdate(role=UserRole.WAREHOUSE))

    assert user.role is UserRole.WAREHOUSE
    assert user.full_name == "Staff"
    assert user.is_active is True


def test_update_does_not_commit(db_session_factory):
    with db_session_factory() as session:
        admin = add_user(session, "admin@shop.al", UserRole.ADMIN)
        user = add_user(session, "ana@shop.al", UserRole.SALES)
        session.commit()

        update_user(session, admin, user, StaffUpdate(full_name="Changed"))
        session.rollback()

        assert session.get(User, user.id).full_name == "Staff"


@pytest.mark.parametrize(
    "data", [StaffUpdate(is_active=False), StaffUpdate(role=UserRole.SALES)]
)
def test_admin_cannot_deactivate_or_demote_themselves(db_session, data):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    add_user(db_session, "second@shop.al", UserRole.ADMIN)

    with pytest.raises(SelfModificationError):
        update_user(db_session, admin, admin, data)

    assert admin.role is UserRole.ADMIN
    assert admin.is_active is True


def test_admin_can_update_themselves_without_losing_access(db_session):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)

    update_user(
        db_session,
        admin,
        admin,
        StaffUpdate(full_name="Renamed", role=UserRole.ADMIN, is_active=True),
    )

    assert admin.full_name == "Renamed"


@pytest.mark.parametrize(
    "data", [StaffUpdate(is_active=False), StaffUpdate(role=UserRole.WAREHOUSE)]
)
def test_last_active_admin_cannot_be_demoted_or_deactivated(db_session, data):
    last_admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    stale_actor = add_user(db_session, "gone@shop.al", UserRole.ADMIN, is_active=False)

    with pytest.raises(LastAdminError):
        update_user(db_session, stale_actor, last_admin, data)

    assert last_admin.role is UserRole.ADMIN
    assert last_admin.is_active is True


def test_one_of_two_active_admins_can_be_demoted_but_not_the_remaining_one(db_session):
    first = add_user(db_session, "first@shop.al", UserRole.ADMIN)
    second = add_user(db_session, "second@shop.al", UserRole.ADMIN)

    update_user(db_session, first, second, StaffUpdate(role=UserRole.SALES))

    assert second.role is UserRole.SALES

    with pytest.raises(LastAdminError):
        update_user(db_session, second, first, StaffUpdate(is_active=False))


def test_inactive_admin_can_be_demoted_while_another_admin_is_active(db_session):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    retired = add_user(db_session, "retired@shop.al", UserRole.ADMIN, is_active=False)

    update_user(db_session, admin, retired, StaffUpdate(role=UserRole.SALES))

    assert retired.role is UserRole.SALES


def test_active_admins_are_locked_before_they_are_counted(db_session):
    first = add_user(db_session, "first@shop.al", UserRole.ADMIN)
    second = add_user(db_session, "second@shop.al", UserRole.ADMIN)
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)

    try:
        update_user(db_session, first, second, StaffUpdate(is_active=False))
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert any("FOR UPDATE" in statement for statement in statements)


def test_deactivation_ends_only_the_sessions_of_that_user(db_session):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    user = add_user(db_session, "ana@shop.al", UserRole.SALES)
    start_session(db_session, admin, LIFETIME)
    start_session(db_session, user, LIFETIME)
    start_session(db_session, user, LIFETIME)

    update_user(db_session, admin, user, StaffUpdate(is_active=False))

    assert user.is_active is False
    assert count_sessions(db_session, user) == 0
    assert count_sessions(db_session, admin) == 1


def test_role_change_keeps_the_sessions(db_session):
    admin = add_user(db_session, "admin@shop.al", UserRole.ADMIN)
    user = add_user(db_session, "ana@shop.al", UserRole.SALES)
    start_session(db_session, user, LIFETIME)

    update_user(db_session, admin, user, StaffUpdate(role=UserRole.WAREHOUSE))

    assert count_sessions(db_session, user) == 1
