from flask import Blueprint, Response, current_app, g, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import login_required
from app.auth.schemas import LoginRequest
from app.auth.service import (
    InvalidCredentialsError,
    IssuedSession,
    authenticate,
    end_session,
    find_active_session,
    start_session,
)
from app.database import get_db
from app.errors import error_response
from app.users.schemas import UserOut

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def set_session_cookie(response: Response, issued: IssuedSession) -> None:
    response.set_cookie(
        current_app.config["AUTH_COOKIE_NAME"],
        issued.token,
        max_age=int(current_app.config["AUTH_SESSION_LIFETIME"].total_seconds()),
        httponly=True,
        secure=current_app.config["AUTH_COOKIE_SECURE"],
        samesite="Lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        current_app.config["AUTH_COOKIE_NAME"],
        path="/",
        httponly=True,
        secure=current_app.config["AUTH_COOKIE_SECURE"],
        samesite="Lax",
    )


@auth_bp.post("/login")
def login():
    try:
        data = LoginRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return error_response(
            "invalid_request", "Email and password are required.", 400
        )

    db = get_db()

    try:
        user = authenticate(db, data.email, data.password.get_secret_value())
    except InvalidCredentialsError:
        return error_response("invalid_credentials", "Invalid email or password.", 401)

    old_token = request.cookies.get(current_app.config["AUTH_COOKIE_NAME"])
    old_session = find_active_session(db, old_token) if old_token else None
    if old_session is not None:
        end_session(db, old_session)

    issued = start_session(db, user, current_app.config["AUTH_SESSION_LIFETIME"])
    db.commit()

    response = jsonify(
        user=UserOut.model_validate(user).model_dump(mode="json"),
        csrf_token=issued.csrf_token,
    )
    set_session_cookie(response, issued)
    return response, 200


@auth_bp.post("/logout")
@login_required
def logout():
    db = get_db()
    end_session(db, g.user_session)
    db.commit()

    response = Response(status=204)
    clear_session_cookie(response)
    return response


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(
        user=UserOut.model_validate(g.current_user).model_dump(mode="json"),
        csrf_token=g.user_session.csrf_token,
    )
