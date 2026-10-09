import uuid

from flask import Blueprint, g, jsonify
from pydantic import ValidationError

from app.api import request_payload, validation_error_response
from app.auth.decorators import login_required, require_role
from app.database import get_db
from app.errors import error_response
from app.users.models import User, UserRole
from app.users.schemas import (
    StaffCreate,
    StaffOut,
    StaffUpdate,
)
from app.users.service import (
    EmailAlreadyExistsError,
    LastAdminError,
    SelfModificationError,
    create_user,
    get_user,
    list_users,
    update_user,
)

users_bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


def staff_json(user: User) -> dict:
    return StaffOut.model_validate(user).model_dump(mode="json")


def not_found_response():
    return error_response("not_found", "User not found.", 404)


@users_bp.post("")
@login_required
@require_role(UserRole.ADMIN)
def create_staff():
    try:
        data = StaffCreate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    db = get_db()

    try:
        user = create_user(db, data)
    except EmailAlreadyExistsError:
        return error_response(
            "email_taken", "A user with this email already exists.", 409
        )

    db.commit()
    return jsonify(staff_json(user)), 201


@users_bp.get("")
@login_required
@require_role(UserRole.ADMIN)
def list_staff():
    return jsonify(users=[staff_json(user) for user in list_users(get_db())])


@users_bp.get("/<uuid:user_id>")
@login_required
@require_role(UserRole.ADMIN)
def get_staff(user_id: uuid.UUID):
    user = get_user(get_db(), user_id)

    if user is None:
        return not_found_response()

    return jsonify(staff_json(user))


@users_bp.patch("/<uuid:user_id>")
@login_required
@require_role(UserRole.ADMIN)
def update_staff(user_id: uuid.UUID):
    db = get_db()
    user = get_user(db, user_id)

    if user is None:
        return not_found_response()

    try:
        data = StaffUpdate.model_validate(request_payload())
    except ValidationError as error:
        return validation_error_response(error)

    try:
        update_user(db, g.current_user, user, data)
    except SelfModificationError as error:
        return error_response("self_modification", str(error), 409)
    except LastAdminError as error:
        return error_response("last_admin", str(error), 409)

    db.commit()
    return jsonify(staff_json(user))
