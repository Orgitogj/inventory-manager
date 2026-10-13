import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import current_session, require_role
from app.catalog.models import Product
from app.database import DbSession
from app.errors import ApiError
from app.inventory.service import ArchivedProductError, InsufficientStockError
from app.orders.models import Order
from app.orders.schemas import (
    OrderCreate,
    OrderItemsReplace,
    OrderListOut,
    OrderListQuery,
    OrderOut,
    OrderUpdate,
)
from app.orders.service import (
    ArchivedReferenceError,
    EmptyOrderError,
    InvalidReferenceError,
    OrderStateError,
    cancel_order,
    confirm_order,
    create_order,
    get_order,
    list_orders,
    replace_items,
    update_order,
)
from app.users.models import User, UserRole

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

LOGGED_IN = [Depends(current_session)]
CAN_WRITE = [Depends(require_role(UserRole.ADMIN, UserRole.SALES))]
Seller = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.SALES))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Order not found.")


def reference_error(
    code: str, error: InvalidReferenceError | ArchivedReferenceError
) -> ApiError:
    message = str(error)
    return ApiError(422, code, message, [{"field": error.field, "message": message}])


def state_error(error: OrderStateError) -> ApiError:
    return ApiError(409, "invalid_order_status", str(error))


def stock_error(db: DbSession, order: Order, error: InsufficientStockError) -> ApiError:
    product = db.get(Product, error.product_id)
    position = next(
        index
        for index, item in enumerate(order.items)
        if item.product_id == error.product_id
    )
    message = (
        f"Not enough stock for {product.sku}: "
        f"{error.available} available, {error.requested} requested."
    )
    return ApiError(
        409,
        "insufficient_stock",
        message,
        [{"field": f"items.{position}.quantity", "message": message}],
    )


def order_or_404(db: DbSession, order_id: uuid.UUID) -> Order:
    order = get_order(db, order_id)

    if order is None:
        raise not_found()

    return order


@router.get("", response_model=OrderListOut, dependencies=LOGGED_IN)
def list_all(
    filters: Annotated[OrderListQuery, Query()], db: DbSession
) -> OrderListOut:
    orders, total = list_orders(db, filters)
    return OrderListOut(
        orders=[OrderOut.model_validate(order) for order in orders],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{order_id}", response_model=OrderOut, dependencies=LOGGED_IN)
def get_one(order_id: uuid.UUID, db: DbSession) -> OrderOut:
    return OrderOut.model_validate(order_or_404(db, order_id))


@router.post("", response_model=OrderOut, status_code=201)
def create(data: OrderCreate, db: DbSession, user: Seller) -> OrderOut:
    try:
        order = create_order(db, data, user.id)
    except InvalidReferenceError as error:
        raise reference_error("invalid_reference", error) from None
    except ArchivedReferenceError as error:
        raise reference_error("archived_reference", error) from None

    db.commit()
    return OrderOut.model_validate(order)


@router.patch("/{order_id}", response_model=OrderOut, dependencies=CAN_WRITE)
def update(order_id: uuid.UUID, data: OrderUpdate, db: DbSession) -> OrderOut:
    order = order_or_404(db, order_id)

    try:
        update_order(db, order, data)
    except OrderStateError as error:
        raise state_error(error) from None
    except InvalidReferenceError as error:
        raise reference_error("invalid_reference", error) from None
    except ArchivedReferenceError as error:
        raise reference_error("archived_reference", error) from None

    db.commit()
    return OrderOut.model_validate(order)


@router.put("/{order_id}/items", response_model=OrderOut, dependencies=CAN_WRITE)
def replace(order_id: uuid.UUID, data: OrderItemsReplace, db: DbSession) -> OrderOut:
    order = order_or_404(db, order_id)

    try:
        replace_items(db, order, data)
    except OrderStateError as error:
        raise state_error(error) from None
    except InvalidReferenceError as error:
        raise reference_error("invalid_reference", error) from None
    except ArchivedReferenceError as error:
        raise reference_error("archived_reference", error) from None

    db.commit()
    return OrderOut.model_validate(order)


@router.post("/{order_id}/confirm", response_model=OrderOut)
def confirm(order_id: uuid.UUID, db: DbSession, user: Seller) -> OrderOut:
    order = order_or_404(db, order_id)

    try:
        order = confirm_order(db, order, user.id)
    except OrderStateError as error:
        raise state_error(error) from None
    except EmptyOrderError as error:
        raise ApiError(409, "empty_order", str(error)) from None
    except ArchivedProductError as error:
        raise ApiError(409, "archived_product", str(error)) from None
    except InsufficientStockError as error:
        raise stock_error(db, order, error) from None

    db.commit()
    return OrderOut.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: uuid.UUID, db: DbSession, user: Seller) -> OrderOut:
    order = order_or_404(db, order_id)

    try:
        order = cancel_order(db, order, user.id)
    except OrderStateError as error:
        raise state_error(error) from None

    db.commit()
    return OrderOut.model_validate(order)
