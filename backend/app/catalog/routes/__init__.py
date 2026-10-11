from app.catalog.routes.categories import router as categories_router
from app.catalog.routes.products import router as products_router
from app.catalog.routes.suppliers import router as suppliers_router

__all__ = ["categories_router", "products_router", "suppliers_router"]
