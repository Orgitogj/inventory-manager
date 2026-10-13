from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError

from app.auth.dependencies import CurrentSession
from app.auth.schemas import LoginRequest, SessionOut
from app.auth.service import (
    InvalidCredentialsError,
    IssuedSession,
    authenticate,
    end_session,
    find_active_session,
    start_session,
)
from app.database import DbSession
from app.errors import ApiError
from app.users.models import normalize_email
from app.users.schemas import UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def set_session_cookie(
    request: Request, response: Response, issued: IssuedSession
) -> None:
    state = request.app.state
    response.set_cookie(
        state.cookie_name,
        issued.token,
        max_age=int(state.session_lifetime.total_seconds()),
        httponly=True,
        secure=state.cookie_secure,
        samesite="Lax",
        path="/",
    )


def clear_session_cookie(request: Request, response: Response) -> None:
    state = request.app.state
    response.delete_cookie(
        state.cookie_name,
        path="/",
        httponly=True,
        secure=state.cookie_secure,
        samesite="Lax",
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def json_body(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError:
        return None


LOGIN_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": LoginRequest.model_json_schema()}},
    }
}


@router.post("/login", response_model=SessionOut, openapi_extra=LOGIN_REQUEST_BODY)
def login(
    request: Request,
    response: Response,
    db: DbSession,
    payload: Annotated[Any, Depends(json_body)],
) -> SessionOut:
    try:
        data = LoginRequest.model_validate(payload or {})
    except ValidationError:
        raise ApiError(
            400, "invalid_request", "Email and password are required."
        ) from None

    state = request.app.state
    limiter = state.login_rate_limiter
    ip = client_ip(request)
    email = normalize_email(data.email)

    retry_after = limiter.retry_after(ip, email)
    if retry_after is not None:
        raise ApiError(
            429,
            "too_many_attempts",
            "Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        user = authenticate(db, data.email, data.password.get_secret_value())
    except InvalidCredentialsError:
        limiter.record_failure(ip, email)
        raise ApiError(
            401, "invalid_credentials", "Invalid email or password."
        ) from None

    limiter.reset(ip, email)

    old_token = request.cookies.get(state.cookie_name)
    old_session = find_active_session(db, old_token) if old_token else None
    if old_session is not None:
        end_session(db, old_session)

    issued = start_session(db, user, state.session_lifetime)
    db.commit()

    set_session_cookie(request, response, issued)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=issued.csrf_token)


@router.post("/logout", status_code=204, response_class=Response)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    user_session: CurrentSession,
) -> None:
    end_session(db, user_session)
    db.commit()
    clear_session_cookie(request, response)


@router.get("/me", response_model=SessionOut)
def me(user_session: CurrentSession) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(user_session.user),
        csrf_token=user_session.csrf_token,
    )
