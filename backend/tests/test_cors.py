from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings

ORIGIN = "http://localhost:3000"
HEALTH_URL = "/api/v1/health"
LOGIN_URL = "/api/v1/auth/login"


def build_client(origins: list[str]) -> TestClient:
    settings = Settings(app_env="testing", cors_origins=origins, _env_file=None)
    return TestClient(create_app(settings))


def preflight(client: TestClient, origin: str):
    return client.options(
        LOGIN_URL,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )


def test_preflight_from_an_allowed_origin_returns_cors_headers():
    response = preflight(build_client([ORIGIN]), ORIGIN)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"

    methods = {
        method.strip()
        for method in response.headers["access-control-allow-methods"].split(",")
    }
    assert methods == {"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"}

    headers = {
        header.strip().lower()
        for header in response.headers["access-control-allow-headers"].split(",")
    }
    assert {"content-type", "x-csrf-token"} <= headers


def test_preflight_for_a_header_that_is_not_allowed_is_rejected():
    response = build_client([ORIGIN]).options(
        LOGIN_URL,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-secret",
        },
    )

    assert response.status_code == 400


def test_request_from_an_allowed_origin_returns_cors_headers():
    response = build_client([ORIGIN]).get(HEALTH_URL, headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_disallowed_origin_gets_no_allow_origin_header():
    client = build_client([ORIGIN])
    other = "http://evil.example.com"

    blocked_preflight = preflight(client, other)
    blocked_request = client.get(HEALTH_URL, headers={"Origin": other})

    assert blocked_preflight.status_code == 400
    assert "access-control-allow-origin" not in blocked_preflight.headers
    assert "access-control-allow-origin" not in blocked_request.headers


def test_no_cors_middleware_without_configured_origins():
    settings = Settings(app_env="testing", cors_origins=[], _env_file=None)
    app = create_app(settings)

    assert all(
        middleware.cls is not CORSMiddleware for middleware in app.user_middleware
    )

    response = TestClient(app).get(HEALTH_URL, headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_is_added_with_configured_origins():
    settings = Settings(app_env="testing", cors_origins=[ORIGIN], _env_file=None)
    app = create_app(settings)

    assert [middleware.cls for middleware in app.user_middleware] == [CORSMiddleware]
