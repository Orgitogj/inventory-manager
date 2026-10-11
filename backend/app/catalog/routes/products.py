import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import current_session, require_role
from app.catalog.schemas import (
    ProductCreate,
    ProductListOut,
    ProductListQuery,
    ProductOut,
    ProductUpdate,
)
from app.catalog.service import (
    ArchivedReferenceError,
    InvalidReferenceError,
    SkuTakenError,
    create_product,
    get_product,
    list_products,
    update_product,
)
from app.database import DbSession
from app.errors import ApiError
from app.users.models import UserRole

router = APIRouter(prefix="/api/v1/products", tags=["products"])

LOGGED_IN = [Depends(current_session)]
ADMIN_ONLY = [Depends(require_role(UserRole.ADMIN))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Product not found.")


def sku_taken() -> ApiError:
    return ApiError(409, "sku_taken", "A product with this SKU already exists.")


def reference_error(
    code: str, error: InvalidReferenceError | ArchivedReferenceError
) -> ApiError:
    message = str(error)
    return ApiError(422, code, message, [{"field": error.field, "message": message}])


@router.get("", response_model=ProductListOut, dependencies=LOGGED_IN)
def list_all(
    filters: Annotated[ProductListQuery, Query()], db: DbSession
) -> ProductListOut:
    products, total = list_products(db, filters)
    return ProductListOut(
        products=[ProductOut.model_validate(product) for product in products],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{product_id}", response_model=ProductOut, dependencies=LOGGED_IN)
def get_one(product_id: uuid.UUID, db: DbSession) -> ProductOut:
    product = get_product(db, product_id)

    if product is None:
        raise not_found()

    return ProductOut.model_validate(product)


@router.post("", response_model=ProductOut, status_code=201, dependencies=ADMIN_ONLY)
def create(data: ProductCreate, db: DbSession) -> ProductOut:
    try:
        product = create_product(db, data)
    except InvalidReferenceError as error:
        raise reference_error("invalid_reference", error) from None
    except ArchivedReferenceError as error:
        raise reference_error("archived_reference", error) from None
    except SkuTakenError:
        raise sku_taken() from None

    db.commit()
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut, dependencies=ADMIN_ONLY)
def update(product_id: uuid.UUID, data: ProductUpdate, db: DbSession) -> ProductOut:
    product = get_product(db, product_id)

    if product is None:
        raise not_found()

    try:
        update_product(db, product, data)
    except InvalidReferenceError as error:
        raise reference_error("invalid_reference", error) from None
    except ArchivedReferenceError as error:
        raise reference_error("archived_reference", error) from None
    except SkuTakenError:
        raise sku_taken() from None

    db.commit()
    return ProductOut.model_validate(product)
