from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import current_session, require_role
from app.catalog.schemas import ProductListQuery
from app.database import DbSession
from app.errors import ApiError
from app.inventory.schemas import (
    MovementCreate,
    MovementListOut,
    MovementListQuery,
    MovementOut,
    StockListOut,
    StockOut,
)
from app.inventory.service import (
    ArchivedProductError,
    InsufficientStockError,
    InvalidQuantityError,
    ProductNotFoundError,
    list_movements,
    list_stock,
    record_movement,
)
from app.users.models import User, UserRole

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

LOGGED_IN = [Depends(current_session)]
StockKeeper = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.WAREHOUSE))]


def field_error(code: str, field: str, message: str) -> ApiError:
    return ApiError(422, code, message, [{"field": field, "message": message}])


@router.get("/stock", response_model=StockListOut, dependencies=LOGGED_IN)
def stock(filters: Annotated[ProductListQuery, Query()], db: DbSession) -> StockListOut:
    rows, total = list_stock(db, filters)
    return StockListOut(
        stock=[
            StockOut.model_validate(
                {"product": product, "quantity": quantity}, from_attributes=True
            )
            for product, quantity in rows
        ],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/movements", response_model=MovementListOut, dependencies=LOGGED_IN)
def movements(
    filters: Annotated[MovementListQuery, Query()], db: DbSession
) -> MovementListOut:
    items, total = list_movements(db, filters)
    return MovementListOut(
        movements=[MovementOut.model_validate(movement) for movement in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.post("/movements", response_model=MovementOut, status_code=201)
def create_movement(
    data: MovementCreate, db: DbSession, user: StockKeeper
) -> MovementOut:
    try:
        movement = record_movement(
            db,
            product_id=data.product_id,
            kind=data.kind,
            quantity=data.quantity,
            actor_id=user.id,
            reason=data.reason,
        )
    except InvalidQuantityError as error:
        raise field_error("invalid_quantity", "quantity", str(error)) from None
    except ProductNotFoundError:
        raise field_error(
            "invalid_reference", "product_id", "Referenced record does not exist."
        ) from None
    except ArchivedProductError:
        raise field_error(
            "archived_reference", "product_id", "Referenced record is archived."
        ) from None
    except InsufficientStockError as error:
        raise ApiError(409, "insufficient_stock", str(error)) from None

    db.commit()
    return MovementOut.model_validate(movement)
