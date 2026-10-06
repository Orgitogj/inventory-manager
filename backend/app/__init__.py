from flask import Flask

from app.config import Settings
from app.database import init_database
from app.health.routes import health_bp


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings if settings is not None else Settings()

    app = Flask(__name__)

    app.config.update(
        APP_ENV=settings.app_env,
        TESTING=settings.app_env == "testing",
        DATABASE_URL=settings.database_url,
    )

    init_database(app)
    app.register_blueprint(health_bp)

    return app
