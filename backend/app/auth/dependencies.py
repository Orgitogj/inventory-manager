import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import UserSession
from app.auth.service import find_active_session
from app.database import DbSession
from app.errors import ApiError
from app.users.models import User, UserRole

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


def current_session(request: Request, db: DbSession) -> UserSession:
    token = request.cookies.get(request.app.state.cookie_name)
    user_session = find_active_session(db, token) if token else None

    if user_session is None:
        raise ApiError(401, "unauthenticated", "Login required.")

    if request.method not in SAFE_METHODS and not hmac.compare_digest(
        request.headers.get(CSRF_HEADER, ""), user_session.csrf_token
    ):
        raise ApiError(403, "csrf_failed", "Missing or invalid CSRF token.")

    return user_session


CurrentSession = Annotated[UserSession, Depends(current_session)]


def current_user(user_session: CurrentSession) -> User:
    return user_session.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    allowed_roles = frozenset(roles)

    def authorized_user(user: CurrentUser) -> User:
        if user.role not in allowed_roles:
            raise ApiError(403, "forbidden", "You do not have permission to do this.")

        return user

    return authorized_user
