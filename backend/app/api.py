from flask import request
from pydantic import ValidationError

from app.errors import error_response
from app.users.schemas import validation_error_details


def request_payload() -> object:
    payload = request.get_json(silent=True)
    return {} if payload is None else payload


def validation_error_response(error: ValidationError):
    return error_response(
        "validation_error", "Invalid input.", 422, validation_error_details(error)
    )
