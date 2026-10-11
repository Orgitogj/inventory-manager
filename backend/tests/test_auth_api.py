from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app import create_app
from app.auth.models import UserSession
from app.auth.service import hash_token
from app.config import Settings
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

EMAIL = "ana@shop.al"
PASSWORD = "long-enough-password"
COOKIE = "inventory_session"


@pytest.fixture
def app(db_session_factory) -> FastAPI:
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))
    app.state.session_factory = db_session_factory
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def user(db_session) -> User:
    user = create_user(
        db_session,
        StaffCreate(
            email=EMAIL, full_name="Ana", password=PASSWORD, role=UserRole.WAREHOUSE
        ),
    )
    db_session.commit()
    return user


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def count_sessions(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(UserSession))


def test_login_sets_http_only_cookie_and_returns_user(client, user, db_session):
    response = login(client, email="  ANA@shop.al ")

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": str(user.id),
        "email": EMAIL,
        "full_name": "Ana",
        "role": "warehouse",
    }
    assert body["csrf_token"]

    cookie = SimpleCookie(response.headers["set-cookie"]).get(COOKIE)
    assert cookie is not None
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert client.cookies.get(COOKIE) == cookie.value

    stored = db_session.scalars(select(UserSession)).one()
    assert stored.token_hash == hash_token(cookie.value)
    assert stored.token_hash != cookie.value


@pytest.mark.parametrize(
    ("email", "password"),
    [(EMAIL, "wrong-password-123"), ("nobody@shop.al", PASSWORD)],
)
def test_bad_credentials_get_the_same_generic_error(client, user, email, password):
    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Invalid email or password.",
        }
    }
    assert client.cookies.get(COOKIE) is None


def test_inactive_user_cannot_login(client, user, db_session):
    user.is_active = False
    db_session.commit()

    assert login(client).status_code == 401


@pytest.mark.parametrize("payload", [None, {}, {"email": EMAIL}, {"password": "x"}])
def test_invalid_login_body_is_rejected(client, user, payload):
    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_me_requires_login(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_returns_current_user_and_csrf_token(client, user):
    csrf_token = login(client).json()["csrf_token"]

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL
    assert response.json()["csrf_token"] == csrf_token


def test_logout_requires_csrf_token(client, user, db_session):
    login(client)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert count_sessions(db_session) == 1


def test_logout_ends_the_session(client, user, db_session):
    csrf_token = login(client).json()["csrf_token"]

    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert client.cookies.get(COOKIE) is None
    assert count_sessions(db_session) == 0
    assert client.get("/api/v1/auth/me").status_code == 401


def test_stolen_cookie_stops_working_after_logout(app, client, user):
    csrf_token = login(client).json()["csrf_token"]
    stolen_token = client.cookies.get(COOKIE)

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    attacker = TestClient(app)
    attacker.cookies.set(COOKIE, stolen_token)
    assert attacker.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(client, user, db_session):
    login(client)
    db_session.execute(
        update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_deactivated_user_loses_access_immediately(client, user, db_session):
    login(client)
    user.is_active = False
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_again_replaces_the_previous_session(client, user, db_session):
    login(client)
    first_token = client.cookies.get(COOKIE)

    login(client)

    assert count_sessions(db_session) == 1
    assert client.cookies.get(COOKIE) != first_token
