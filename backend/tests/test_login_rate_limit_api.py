import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import create_app
from app.auth import routes
from app.auth.rate_limit import LoginRateLimiter
from app.config import Settings
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

EMAIL = "ana@shop.al"
UNKNOWN_EMAIL = "nobody@shop.al"
PASSWORD = "long-enough-password"
WRONG_PASSWORD = "wrong-password-123"
LOGIN_URL = "/api/v1/auth/login"
WINDOW_SECONDS = 15 * 60
BLOCKED = {
    "error": {
        "code": "too_many_attempts",
        "message": "Too many failed login attempts. Try again later.",
    }
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="testing",
        database_url=None,
        login_max_attempts=5,
        login_window_minutes=15,
        login_max_attempts_per_ip=7,
        _env_file=None,
    )


@pytest.fixture
def app(db_session_factory, settings: Settings, clock: FakeClock) -> FastAPI:
    app = create_app(settings)
    app.state.session_factory = db_session_factory
    app.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=settings.login_max_attempts,
        max_attempts_per_ip=settings.login_max_attempts_per_ip,
        window_seconds=settings.login_window_minutes * 60,
        clock=clock,
    )
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
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def fail(client: TestClient, times: int, email: str = EMAIL) -> list[int]:
    return [
        login(client, email=email, password=WRONG_PASSWORD).status_code
        for _ in range(times)
    ]


def test_app_gets_a_limiter_built_from_settings():
    settings = Settings(
        app_env="testing",
        login_max_attempts=2,
        login_window_minutes=1,
        login_max_attempts_per_ip=9,
        _env_file=None,
    )
    first = create_app(settings).state.login_rate_limiter
    second = create_app(settings).state.login_rate_limiter

    assert isinstance(first, LoginRateLimiter)
    assert first is not second

    first.record_failure("ip", "a@shop.al")
    first.record_failure("ip", "a@shop.al")

    assert 0 < first.retry_after("ip", "a@shop.al") <= 60
    assert second.retry_after("ip", "a@shop.al") is None


def test_five_failures_block_the_sixth_attempt(client, user):
    assert fail(client, 5) == [401] * 5

    response = login(client, password=WRONG_PASSWORD)

    assert response.status_code == 429
    assert response.json() == BLOCKED
    assert response.headers["retry-after"] == str(WINDOW_SECONDS)


def test_retry_after_counts_down(client, user, clock):
    fail(client, 5)
    clock.advance(60)

    response = login(client, password=WRONG_PASSWORD)

    assert response.status_code == 429
    assert response.headers["retry-after"] == str(WINDOW_SECONDS - 60)


def test_blocked_client_is_rejected_before_the_password_is_checked(
    client, user, monkeypatch
):
    fail(client, 5)

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("authenticate must not run for a blocked client")

    monkeypatch.setattr(routes, "authenticate", unexpected_call)

    response = login(client)

    assert response.status_code == 429
    assert response.json() == BLOCKED
    assert "set-cookie" not in response.headers


def test_email_is_normalized_before_counting(client, user):
    first = login(client, email="  ANA@shop.al ", password=WRONG_PASSWORD)
    assert first.status_code == 401
    assert fail(client, 4) == [401] * 4

    assert login(client, email="Ana@Shop.AL").status_code == 429


def test_other_email_from_the_same_ip_is_allowed_until_the_ip_limit(client, user):
    fail(client, 5)
    assert login(client).status_code == 429

    assert fail(client, 2, email="vera@shop.al") == [401, 401]

    response = login(client, email="third@shop.al", password=WRONG_PASSWORD)

    assert response.status_code == 429
    assert response.json() == BLOCKED
    assert int(response.headers["retry-after"]) > 0


def test_successful_login_resets_the_counter(client, user):
    fail(client, 4)
    assert login(client).status_code == 200

    assert fail(client, 2) == [401, 401]
    assert login(client).status_code == 200


def test_login_works_again_after_the_window_passes(client, user, clock):
    fail(client, 5)
    assert login(client).status_code == 429

    clock.advance(WINDOW_SECONDS - 1)
    assert login(client).status_code == 429

    clock.advance(1)
    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL


def test_blocked_response_does_not_reveal_whether_the_user_exists(app, user):
    known = TestClient(app, client=("203.0.113.1", 50000))
    unknown = TestClient(app, client=("203.0.113.2", 50000))

    assert fail(known, 5) == fail(unknown, 5, email=UNKNOWN_EMAIL)

    known_response = login(known, password=WRONG_PASSWORD)
    unknown_response = login(unknown, email=UNKNOWN_EMAIL, password=WRONG_PASSWORD)

    assert known_response.status_code == unknown_response.status_code == 429
    assert known_response.content == unknown_response.content
    assert known_response.headers.items() == unknown_response.headers.items()


def test_clients_on_different_ips_are_limited_separately(app, user):
    attacker = TestClient(app, client=("203.0.113.1", 50000))
    owner = TestClient(app, client=("203.0.113.2", 50000))

    fail(attacker, 5)

    assert login(attacker).status_code == 429
    assert login(owner).status_code == 200


def test_invalid_body_does_not_count_as_a_failed_login(client, user):
    for _ in range(10):
        assert client.post(LOGIN_URL, json={"email": EMAIL}).status_code == 400

    assert login(client).status_code == 200
