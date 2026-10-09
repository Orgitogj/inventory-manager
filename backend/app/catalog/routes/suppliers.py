import uuid

from flask import Blueprint, jsonify
from pydantic import ValidationError

from app.api import request_payload, validation_error_response
from app.auth.decorators import login_required, require_role
from app.catalog.models import Supplier
from app.catalog.routes.common import include_archived_requested
from app.catalog.schemas import SupplierCreate, SupplierOut, SupplierUpdate
from app.catalog.service import (
    SupplierNameTakenError,
    create_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
)
from app.database import get_db
from app.errors import error_response
from app.users.models import UserRole

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/api/v1/suppliers")


def supplier_json(supplier: Supplier) -> dict:
    return SupplierOut.model_validate(supplier).model_dump(mode="json")


def not_found_response():
    return error_response("not_found", "Supplier not found.", 404)


def name_taken_response():
    return error_response(
        "name_taken", "A supplier with this name already exists.", 409
    )


@suppliers_bp.get("")
@login_required
def list_all():
    suppliers = list_suppliers(get_db(), include_archived_requested())
    return jsonify(suppliers=[supplier_json(supplier) for supplier in suppliers])


@suppliers_bp.get("/<uuid:supplier_id>")
@login_required
def get_one(supplier_id: uuid.UUID):
    supplier = get_supplier(get_db(), supplier_id)

    if supplier is None:
        return not_found_response()

    return jsonify(supplier_json(supplier))


@suppliers_bp.post("")
@login_required
@require_role(UserRole.ADMIN)
def create():
    try:
        data = SupplierCreate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    db = get_db()

    try:
        supplier = create_supplier(db, data)
    except SupplierNameTakenError:
        return name_taken_response()

    db.commit()
    return jsonify(supplier_json(supplier)), 201


@suppliers_bp.patch("/<uuid:supplier_id>")
@login_required
@require_role(UserRole.ADMIN)
def update(supplier_id: uuid.UUID):
    db = get_db()
    supplier = get_supplier(db, supplier_id)

    if supplier is None:
        return not_found_response()

    try:
        data = SupplierUpdate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    try:
        update_supplier(db, supplier, data)
    except SupplierNameTakenError:
        return name_taken_response()

    db.commit()
    return jsonify(supplier_json(supplier))
