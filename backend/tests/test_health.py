from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings


def test_health_returns_ok():
    settings = Settings(
        app_env="testing",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "inventory-api",
    }
