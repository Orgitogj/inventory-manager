import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings

DOCS_URLS = ["/docs", "/redoc", "/openapi.json"]
UNUSED_DATABASE_URL = "postgresql+psycopg://nobody@127.0.0.1:1/unused_test"


@pytest.mark.parametrize("app_env", ["development", "testing"])
@pytest.mark.parametrize("url", DOCS_URLS)
def test_docs_are_served_outside_production(app_env, url):
    app = create_app(Settings(app_env=app_env, database_url=None, _env_file=None))

    assert TestClient(app).get(url).status_code == 200


@pytest.mark.parametrize("url", DOCS_URLS)
def test_docs_are_disabled_in_production(url):
    app = create_app(Settings(app_env="production", database_url=None, _env_file=None))

    response = TestClient(app).get(url)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_api_still_works_in_production_without_docs():
    app = create_app(Settings(app_env="production", database_url=None, _env_file=None))

    assert TestClient(app).get("/api/v1/health").status_code == 200


def test_engine_is_disposed_on_shutdown(monkeypatch):
    app = create_app(
        Settings(app_env="testing", database_url=UNUSED_DATABASE_URL, _env_file=None)
    )
    calls = []
    monkeypatch.setattr(app.state.engine, "dispose", lambda: calls.append("dispose"))

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert calls == []

    assert calls == ["dispose"]


def test_shutdown_without_an_engine_does_nothing():
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200

    assert app.state.engine is None
