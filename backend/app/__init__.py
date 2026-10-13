from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app import models
from app.auth.routes import router as auth_router
from app.catalog.routes import categories_router, products_router, suppliers_router
from app.config import Settings
from app.customers.routes import router as customers_router
from app.database import build_engine
from app.errors import register_error_handlers
from app.health.routes import router as health_router
from app.inventory.routes import router as inventory_router
from app.orders.routes import router as orders_router
from app.users.routes import router as users_router

CORS_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Content-Type", "X-CSRF-Token"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    docs_enabled = settings.app_env != "production"

    app = FastAPI(
        title="Inventory Manager API",
        redirect_slashes=False,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    engine = build_engine(settings.database_url) if settings.database_url else None

    app.state.settings = settings
    app.state.cookie_name = "inventory_session"
    app.state.cookie_secure = settings.app_env == "production"
    app.state.session_lifetime = timedelta(hours=settings.session_lifetime_hours)
    app.state.engine = engine
    app.state.session_factory = sessionmaker(bind=engine) if engine else None

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=CORS_METHODS,
            allow_headers=CORS_HEADERS,
        )

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(categories_router)
    app.include_router(suppliers_router)
    app.include_router(products_router)
    app.include_router(inventory_router)
    app.include_router(customers_router)
    app.include_router(orders_router)

    return app


__all__ = ["create_app", "models"]
