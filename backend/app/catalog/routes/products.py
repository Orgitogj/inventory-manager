import uuid

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.api import request_payload, validation_error_response
from app.auth.decorators import login_required, require_role
from app.catalog.models import Product
from app.catalog.schemas import (
    ProductCreate,
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
from app.database import get_db
from app.errors import error_response
from app.users.models import UserRole

products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products")


def product_json(product: Product) -> dict:
    return ProductOut.model_validate(product).model_dump(mode="json")


def not_found_response():
    return error_response("not_found", "Product not found.", 404)


def sku_taken_response():
    return error_response("sku_taken", "A product with this SKU already exists.", 409)


def reference_error_response(
    code: str, error: InvalidReferenceError | ArchivedReferenceError
):
    message = str(error)
    return error_response(
        code, message, 422, [{"field": error.field, "message": message}]
    )


@products_bp.get("")
@login_required
def list_all():
    try:
        filters = ProductListQuery.model_validate(request.args.to_dict())
    except ValidationError as error:
        return validation_error_response(error)

    products, total = list_products(get_db(), filters)
    return jsonify(
        products=[product_json(product) for product in products],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@products_bp.get("/<uuid:product_id>")
@login_required
def get_one(product_id: uuid.UUID):
    product = get_product(get_db(), product_id)

    if product is None:
        return not_found_response()

    return jsonify(product_json(product))


@products_bp.post("")
@login_required
@require_role(UserRole.ADMIN)
def create():
    try:
        data = ProductCreate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    db = get_db()

    try:
        product = create_product(db, data)
    except InvalidReferenceError as error:
        return reference_error_response("invalid_reference", error)
    except ArchivedReferenceError as error:
        return reference_error_response("archived_reference", error)
    except SkuTakenError:
        return sku_taken_response()

    db.commit()
    return jsonify(product_json(product)), 201


@products_bp.patch("/<uuid:product_id>")
@login_required
@require_role(UserRole.ADMIN)
def update(product_id: uuid.UUID):
    db = get_db()
    product = get_product(db, product_id)

    if product is None:
        return not_found_response()

    try:
        data = ProductUpdate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    try:
        update_product(db, product, data)
    except InvalidReferenceError as error:
        return reference_error_response("invalid_reference", error)
    except ArchivedReferenceError as error:
        return reference_error_response("archived_reference", error)
    except SkuTakenError:
        return sku_taken_response()

    db.commit()
    return jsonify(product_json(product))
