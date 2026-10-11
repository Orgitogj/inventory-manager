from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app.api import request_payload, validation_error_response
from app.auth.decorators import login_required, require_role
from app.catalog.models import Product
from app.catalog.schemas import ProductListQuery
from app.database import get_db
from app.errors import error_response
from app.inventory.models import StockMovement
from app.inventory.schemas import (
    MovementCreate,
    MovementListQuery,
    MovementOut,
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
from app.users.models import UserRole

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/v1/inventory")


def stock_json(product: Product, quantity: int) -> dict:
    return StockOut.model_validate(
        {"product": product, "quantity": quantity}, from_attributes=True
    ).model_dump(mode="json")


def movement_json(movement: StockMovement) -> dict:
    return MovementOut.model_validate(movement).model_dump(mode="json")


def field_error_response(code: str, field: str, message: str):
    return error_response(code, message, 422, [{"field": field, "message": message}])


@inventory_bp.get("/stock")
@login_required
def stock():
    try:
        filters = ProductListQuery.model_validate(request.args.to_dict())
    except ValidationError as error:
        return validation_error_response(error)

    rows, total = list_stock(get_db(), filters)
    return jsonify(
        stock=[stock_json(product, quantity) for product, quantity in rows],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@inventory_bp.get("/movements")
@login_required
def movements():
    try:
        filters = MovementListQuery.model_validate(request.args.to_dict())
    except ValidationError as error:
        return validation_error_response(error)

    items, total = list_movements(get_db(), filters)
    return jsonify(
        movements=[movement_json(movement) for movement in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@inventory_bp.post("/movements")
@login_required
@require_role(UserRole.ADMIN, UserRole.WAREHOUSE)
def create_movement():
    try:
        data = MovementCreate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    db = get_db()

    try:
        movement = record_movement(
            db,
            product_id=data.product_id,
            kind=data.kind,
            quantity=data.quantity,
            actor_id=g.current_user.id,
            reason=data.reason,
        )
    except InvalidQuantityError as error:
        return field_error_response("invalid_quantity", "quantity", str(error))
    except ProductNotFoundError:
        return field_error_response(
            "invalid_reference", "product_id", "Referenced record does not exist."
        )
    except ArchivedProductError:
        return field_error_response(
            "archived_reference", "product_id", "Referenced record is archived."
        )
    except InsufficientStockError as error:
        return error_response("insufficient_stock", str(error), 409)

    db.commit()
    return jsonify(movement_json(movement)), 201
