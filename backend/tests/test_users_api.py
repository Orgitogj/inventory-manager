import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import create_app
from app.auth.models import UserSession
from app.auth.passwords import verify_password
from app.config import Settings
from app.users import routes
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import LastAdminError, create_user

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
ADMIN_EMAIL = "admin@shop.al"
USERS_URL = "/api/v1/users"
ME_URL = "/api/v1/auth/me"
PASSWORD_MESSAGE = "Password must be between 12 and 128 characters."


@pytest.fixture
def app(db_session_factory) -> FastAPI:
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))
    app.state.session_factory = db_session_factory
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def add_user(db_session, email: str, role: UserRole, full_name: str = "Staff") -> User:
    user = create_user(
        db_session,
        StaffCreate(email=email, full_name=full_name, password=PASSWORD, role=role),
    )
    db_session.commit()
    return user


@pytest.fixture
def admin(db_session) -> User:
    return add_user(db_session, ADMIN_EMAIL, UserRole.ADMIN, "Admin")


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.json()
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def csrf(client: TestClient, admin: User) -> dict[str, str]:
    return login(client, ADMIN_EMAIL)


def staff_payload(**overrides) -> dict:
    payload = {
        "email": "vera@shop.al",
        "full_name": "Vera",
        "password": PASSWORD,
        "role": "warehouse",
    }
    payload.update(overrides)
    return payload


def user_url(user_id) -> str:
    return f"{USERS_URL}/{user_id}"


def error_code(response) -> str:
    return response.json()["error"]["code"]


def count_users(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(User))


def count_sessions(db_session, user: User) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.user_id == user.id)
    )


def test_users_require_login(client):
    response = client.get(USERS_URL)

    assert response.status_code == 401
    assert error_code(response) == "unauthenticated"


@pytest.mark.parametrize("role", [UserRole.WAREHOUSE, UserRole.SALES])
def test_non_admin_roles_are_forbidden(client, db_session, role):
    other = add_user(db_session, "staff@shop.al", role)
    csrf = login(client, "staff@shop.al")

    responses = [
        client.get(USERS_URL),
        client.get(user_url(other.id)),
        client.post(USERS_URL, json=staff_payload(), headers=csrf),
        client.patch(user_url(other.id), json={"role": "admin"}, headers=csrf),
    ]

    assert [response.status_code for response in responses] == [403] * 4
    assert {error_code(response) for response in responses} == {"forbidden"}
    assert count_users(db_session) == 1
    assert db_session.get(User, other.id).role is role


def test_admin_creates_staff(app, client, csrf, db_session):
    response = client.post(
        USERS_URL, json=staff_payload(email="  Vera@Shop.AL "), headers=csrf
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "role", "is_active", "created_at"}
    assert body["email"] == "vera@shop.al"
    assert body["full_name"] == "Vera"
    assert body["role"] == "warehouse"
    assert body["is_active"] is True
    assert PASSWORD not in response.text

    stored = db_session.get(User, uuid.UUID(body["id"]))
    assert stored.email == "vera@shop.al"
    assert stored.password_hash != PASSWORD
    assert verify_password(stored.password_hash, PASSWORD)
    assert stored.password_hash not in response.text

    login(TestClient(app), "vera@shop.al")


def test_duplicate_email_is_a_conflict(client, csrf, db_session):
    assert client.post(USERS_URL, json=staff_payload(), headers=csrf).status_code == 201

    response = client.post(
        USERS_URL, json=staff_payload(email=" VERA@shop.al "), headers=csrf
    )

    assert response.status_code == 409
    assert error_code(response) == "email_taken"
    assert count_users(db_session) == 2


def test_short_password_is_rejected_without_echoing_it(client, csrf, db_session):
    response = client.post(
        USERS_URL, json=staff_payload(password="short-pw"), headers=csrf
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "Invalid input.",
        "details": [{"field": "password", "message": PASSWORD_MESSAGE}],
    }
    assert "short-pw" not in response.text
    assert count_users(db_session) == 1


def test_invalid_fields_are_reported_without_input_values(client, csrf, db_session):
    response = client.post(
        USERS_URL,
        json={"email": "not-an-email", "role": "owner", "password": "secret-pw"},
        headers=csrf,
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert {detail["field"] for detail in details} == {
        "email",
        "full_name",
        "password",
        "role",
    }
    assert all(set(detail) == {"field", "message"} for detail in details)
    assert "secret-pw" not in response.text
    assert count_users(db_session) == 1


def test_create_requires_csrf_token(client, csrf, db_session):
    response = client.post(USERS_URL, json=staff_payload())

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"
    assert count_users(db_session) == 1


def test_list_returns_all_users_without_password_hash(client, csrf, admin, db_session):
    other = add_user(db_session, "vera@shop.al", UserRole.SALES, "Vera")

    response = client.get(USERS_URL)

    assert response.status_code == 200
    users = response.json()["users"]
    assert {user["id"] for user in users} == {str(admin.id), str(other.id)}
    assert all("password_hash" not in user for user in users)
    assert admin.password_hash not in response.text


def test_get_returns_one_user(client, csrf, db_session):
    other = add_user(db_session, "vera@shop.al", UserRole.SALES, "Vera")

    response = client.get(user_url(other.id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(other.id)
    assert body["email"] == "vera@shop.al"
    assert body["role"] == "sales"
    assert body["is_active"] is True
    assert "password_hash" not in body


def test_unknown_user_is_not_found(client, csrf):
    responses = [
        client.get(user_url(uuid.uuid4())),
        client.patch(user_url(uuid.uuid4()), json={"full_name": "X"}, headers=csrf),
    ]

    assert [response.status_code for response in responses] == [404, 404]
    assert {error_code(response) for response in responses} == {"not_found"}


def test_admin_changes_name_and_role_of_another_user(client, csrf, db_session):
    other = add_user(db_session, "vera@shop.al", UserRole.WAREHOUSE, "Vera")

    response = client.patch(
        user_url(other.id),
        json={"full_name": "  Vera Hoxha ", "role": "sales"},
        headers=csrf,
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Vera Hoxha"
    assert response.json()["role"] == "sales"

    db_session.refresh(other)
    assert other.full_name == "Vera Hoxha"
    assert other.role is UserRole.SALES
    assert other.is_active is True


def test_deactivation_logs_the_user_out_everywhere(app, client, csrf, db_session):
    other = add_user(db_session, "vera@shop.al", UserRole.WAREHOUSE, "Vera")
    phone = TestClient(app)
    laptop = TestClient(app)
    login(phone, "vera@shop.al")
    login(laptop, "vera@shop.al")
    assert phone.get(ME_URL).status_code == 200
    assert count_sessions(db_session, other) == 2

    response = client.patch(user_url(other.id), json={"is_active": False}, headers=csrf)

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert count_sessions(db_session, other) == 0
    assert phone.get(ME_URL).status_code == 401
    assert laptop.get(ME_URL).status_code == 401
    assert client.get(ME_URL).status_code == 200

    retry = TestClient(app).post(
        "/api/v1/auth/login", json={"email": "vera@shop.al", "password": PASSWORD}
    )
    assert retry.status_code == 401


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "body"),
        ({"role": None}, "role"),
        ({"role": "owner"}, "role"),
        ({"full_name": "   "}, "full_name"),
        ({"is_active": "no"}, "is_active"),
        ({"email": "new@shop.al"}, "email"),
        ({"password": "another-long-password"}, "password"),
    ],
)
def test_invalid_update_is_rejected(client, csrf, db_session, payload, field):
    other = add_user(db_session, "vera@shop.al", UserRole.WAREHOUSE, "Vera")

    response = client.patch(user_url(other.id), json=payload, headers=csrf)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    details = response.json()["error"]["details"]
    assert [detail["field"] for detail in details] == [field]
    assert "another-long-password" not in response.text


def test_update_requires_csrf_token(client, csrf, db_session):
    other = add_user(db_session, "vera@shop.al", UserRole.WAREHOUSE, "Vera")

    response = client.patch(user_url(other.id), json={"is_active": False})

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"
    assert db_session.get(User, other.id).is_active is True


@pytest.mark.parametrize("payload", [{"is_active": False}, {"role": "sales"}])
def test_admin_cannot_deactivate_or_demote_themselves(
    client, csrf, admin, db_session, payload
):
    add_user(db_session, "second@shop.al", UserRole.ADMIN)

    response = client.patch(user_url(admin.id), json=payload, headers=csrf)

    assert response.status_code == 409
    assert error_code(response) == "self_modification"

    db_session.refresh(admin)
    assert admin.role is UserRole.ADMIN
    assert admin.is_active is True
    assert client.get(ME_URL).status_code == 200


def test_admin_can_change_their_own_name(client, csrf, admin):
    response = client.patch(
        user_url(admin.id), json={"full_name": "New Name"}, headers=csrf
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


@pytest.mark.parametrize("payload", [{"is_active": False}, {"role": "warehouse"}])
def test_last_active_admin_cannot_be_demoted_or_deactivated(
    client, csrf, admin, db_session, payload
):
    retired = add_user(db_session, "retired@shop.al", UserRole.ADMIN)
    retired.is_active = False
    db_session.commit()

    response = client.patch(user_url(admin.id), json=payload, headers=csrf)

    assert response.status_code == 409

    db_session.refresh(admin)
    assert admin.role is UserRole.ADMIN
    assert admin.is_active is True


def test_last_admin_error_is_reported_as_a_conflict(
    client, csrf, db_session, monkeypatch
):
    other = add_user(db_session, "second@shop.al", UserRole.ADMIN)

    def refuse(*_args, **_kwargs):
        raise LastAdminError

    monkeypatch.setattr(routes, "update_user", refuse)

    response = client.patch(user_url(other.id), json={"role": "sales"}, headers=csrf)

    assert response.status_code == 409
    assert error_code(response) == "last_admin"


def test_one_of_two_admins_can_demote_the_other(app, client, csrf, db_session):
    other = add_user(db_session, "second@shop.al", UserRole.ADMIN)
    other_client = TestClient(app)
    login(other_client, "second@shop.al")
    assert other_client.get(USERS_URL).status_code == 200

    response = client.patch(user_url(other.id), json={"role": "sales"}, headers=csrf)

    assert response.status_code == 200
    assert response.json()["role"] == "sales"
    assert other_client.get(ME_URL).status_code == 200
    assert other_client.get(USERS_URL).status_code == 403
