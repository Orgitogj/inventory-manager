from datetime import timedelta

from flask import Flask

from app.auth.routes import auth_bp
from app.catalog.routes import categories_bp, products_bp, suppliers_bp
from app.config import Settings
from app.database import init_database
from app.health.routes import health_bp
from app.users.cli import create_admin
from app.users.routes import users_bp


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings if settings is not None else Settings()

    app = Flask(__name__)

    app.config.update(
        APP_ENV=settings.app_env,
        TESTING=settings.app_env == "testing",
        DATABASE_URL=settings.database_url,
        AUTH_COOKIE_NAME="inventory_session",
        AUTH_COOKIE_SECURE=settings.app_env == "production",
        AUTH_SESSION_LIFETIME=timedelta(hours=settings.session_lifetime_hours),
    )

    init_database(app)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(products_bp)
    app.cli.add_command(create_admin)

    return app
