import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings

DOCS_URLS = ["/docs", "/redoc", "/openapi.json"]


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
