import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import create_app
from app.config import Settings
from app.database import get_db

ORIGIN = "http://localhost:3000"
SECRET = "hunter2-internal-detail"
STATEMENT = "SELECT password_hash FROM users"
INTERNAL_ERROR = {
    "error": {"code": "internal_error", "message": "An unexpected error occurred."}
}
SERVICE_UNAVAILABLE = {
    "error": {
        "code": "service_unavailable",
        "message": "The service is temporarily unavailable.",
    }
}


def build_app(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(SECRET)

    @app.get("/database-down")
    def database_down() -> None:
        raise OperationalError(STATEMENT, {}, Exception(SECRET))

    return app


@pytest.fixture
def app() -> FastAPI:
    return build_app(Settings(app_env="testing", database_url=None, _env_file=None))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def assert_nothing_leaks(response) -> None:
    assert response.headers["content-type"] == "application/json"
    assert SECRET not in response.text
    assert STATEMENT not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert "OperationalError" not in response.text


def test_unexpected_error_returns_generic_json(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.middleware"):
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert_nothing_leaks(response)

    record = caplog.records[-1]
    assert record.name == "app.middleware"
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


def test_unexpected_error_from_an_allowed_origin_keeps_cors_headers():
    app = build_app(
        Settings(
            app_env="testing",
            database_url=None,
            cors_origins=[ORIGIN],
            _env_file=None,
        )
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert_nothing_leaks(response)
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unexpected_error_from_a_disallowed_origin_gets_no_cors_headers():
    app = build_app(
        Settings(
            app_env="testing",
            database_url=None,
            cors_origins=[ORIGIN],
            _env_file=None,
        )
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert "access-control-allow-origin" not in response.headers


def test_database_outage_returns_service_unavailable(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = client.get("/database-down")

    assert response.status_code == 503
    assert response.json() == SERVICE_UNAVAILABLE
    assert_nothing_leaks(response)

    record = caplog.records[-1]
    assert record.exc_info is not None
    assert record.exc_info[0] is OperationalError


def test_missing_database_configuration_returns_service_unavailable(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = client.get("/api/v1/categories")

    assert response.status_code == 503
    assert response.json() == SERVICE_UNAVAILABLE
    assert_nothing_leaks(response)
    assert caplog.records


def test_failing_dependency_returns_generic_json(app, client):
    def broken_database():
        raise RuntimeError(SECRET)

    app.dependency_overrides[get_db] = broken_database

    response = client.get("/api/v1/categories")

    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    assert_nothing_leaks(response)


def test_known_errors_keep_their_own_response(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
