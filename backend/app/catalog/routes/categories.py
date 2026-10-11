import uuid

from fastapi import APIRouter, Depends

from app.auth.dependencies import current_session, require_role
from app.catalog.schemas import (
    CategoryCreate,
    CategoryListOut,
    CategoryOut,
    CategoryUpdate,
)
from app.catalog.service import (
    CategoryNameTakenError,
    create_category,
    get_category,
    list_categories,
    update_category,
)
from app.database import DbSession
from app.errors import ApiError
from app.users.models import UserRole

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])

LOGGED_IN = [Depends(current_session)]
ADMIN_ONLY = [Depends(require_role(UserRole.ADMIN))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Category not found.")


def name_taken() -> ApiError:
    return ApiError(409, "name_taken", "A category with this name already exists.")


@router.get("", response_model=CategoryListOut, dependencies=LOGGED_IN)
def list_all(db: DbSession, include_archived: bool = False) -> CategoryListOut:
    categories = list_categories(db, include_archived)
    return CategoryListOut(
        categories=[CategoryOut.model_validate(category) for category in categories]
    )


@router.get("/{category_id}", response_model=CategoryOut, dependencies=LOGGED_IN)
def get_one(category_id: uuid.UUID, db: DbSession) -> CategoryOut:
    category = get_category(db, category_id)

    if category is None:
        raise not_found()

    return CategoryOut.model_validate(category)


@router.post("", response_model=CategoryOut, status_code=201, dependencies=ADMIN_ONLY)
def create(data: CategoryCreate, db: DbSession) -> CategoryOut:
    try:
        category = create_category(db, data)
    except CategoryNameTakenError:
        raise name_taken() from None

    db.commit()
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryOut, dependencies=ADMIN_ONLY)
def update(category_id: uuid.UUID, data: CategoryUpdate, db: DbSession) -> CategoryOut:
    category = get_category(db, category_id)

    if category is None:
        raise not_found()

    try:
        update_category(db, category, data)
    except CategoryNameTakenError:
        raise name_taken() from None

    db.commit()
    return CategoryOut.model_validate(category)
