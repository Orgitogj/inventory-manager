import uuid

from flask import Blueprint, jsonify
from pydantic import ValidationError

from app.api import request_payload, validation_error_response
from app.auth.decorators import login_required, require_role
from app.catalog.models import Category
from app.catalog.routes.common import include_archived_requested
from app.catalog.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.catalog.service import (
    CategoryNameTakenError,
    create_category,
    get_category,
    list_categories,
    update_category,
)
from app.database import get_db
from app.errors import error_response
from app.users.models import UserRole

categories_bp = Blueprint("categories", __name__, url_prefix="/api/v1/categories")


def category_json(category: Category) -> dict:
    return CategoryOut.model_validate(category).model_dump(mode="json")


def not_found_response():
    return error_response("not_found", "Category not found.", 404)


def name_taken_response():
    return error_response(
        "name_taken", "A category with this name already exists.", 409
    )


@categories_bp.get("")
@login_required
def list_all():
    categories = list_categories(get_db(), include_archived_requested())
    return jsonify(categories=[category_json(category) for category in categories])


@categories_bp.get("/<uuid:category_id>")
@login_required
def get_one(category_id: uuid.UUID):
    category = get_category(get_db(), category_id)

    if category is None:
        return not_found_response()

    return jsonify(category_json(category))


@categories_bp.post("")
@login_required
@require_role(UserRole.ADMIN)
def create():
    try:
        data = CategoryCreate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    db = get_db()

    try:
        category = create_category(db, data)
    except CategoryNameTakenError:
        return name_taken_response()

    db.commit()
    return jsonify(category_json(category)), 201


@categories_bp.patch("/<uuid:category_id>")
@login_required
@require_role(UserRole.ADMIN)
def update(category_id: uuid.UUID):
    db = get_db()
    category = get_category(db, category_id)

    if category is None:
        return not_found_response()

    try:
        data = CategoryUpdate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    try:
        update_category(db, category, data)
    except CategoryNameTakenError:
        return name_taken_response()

    db.commit()
    return jsonify(category_json(category))
