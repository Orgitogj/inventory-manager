import hmac
from collections.abc import Callable
from functools import wraps

from flask import current_app, g, request

from app.auth.service import find_active_session
from app.database import get_db
from app.errors import error_response

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


def login_required[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs):
        token = request.cookies.get(current_app.config["AUTH_COOKIE_NAME"])
        user_session = find_active_session(get_db(), token) if token else None

        if user_session is None:
            return error_response("unauthenticated", "Login required.", 401)

        if request.method not in SAFE_METHODS and not hmac.compare_digest(
            request.headers.get(CSRF_HEADER, ""), user_session.csrf_token
        ):
            return error_response("csrf_failed", "Missing or invalid CSRF token.", 403)

        g.user_session = user_session
        g.current_user = user_session.user
        return view(*args, **kwargs)

    return wrapper
