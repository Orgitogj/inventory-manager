import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.database import DatabaseNotConfiguredError

logger = logging.getLogger(__name__)

REQUEST_LOCATIONS = frozenset({"body", "query", "path"})
HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}
INVALID_JSON = "json_invalid"

type ErrorDetails = list[dict[str, str]]


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: ErrorDetails | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_response(
    status: int,
    code: str,
    message: str,
    details: ErrorDetails | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}

    if details is not None:
        error["details"] = details

    return JSONResponse({"error": error}, status_code=status, headers=headers)


def field_name(error_type: str, location: tuple[str | int, ...]) -> str:
    if error_type == INVALID_JSON:
        return "body"

    parts = (
        location[1:] if location[:1] and location[0] in REQUEST_LOCATIONS else location
    )
    return ".".join(str(part) for part in parts) or "body"


async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
    return error_response(
        error.status, error.code, error.message, error.details, error.headers
    )


async def handle_validation_error(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "field": field_name(detail["type"], tuple(detail["loc"])),
            "message": detail["msg"],
        }
        for detail in error.errors()
    ]
    return error_response(422, "validation_error", "Invalid input.", details)


async def handle_http_error(_request: Request, error: HTTPException) -> JSONResponse:
    code = HTTP_ERROR_CODES.get(error.status_code, "http_error")
    return error_response(error.status_code, code, str(error.detail))


async def handle_unavailable_service(
    request: Request, error: Exception
) -> JSONResponse:
    logger.exception(
        "Database unavailable during %s %s",
        request.method,
        request.url.path,
        exc_info=error,
    )
    return error_response(
        503, "service_unavailable", "The service is temporarily unavailable."
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(OperationalError, handle_unavailable_service)
    app.add_exception_handler(DatabaseNotConfiguredError, handle_unavailable_service)
