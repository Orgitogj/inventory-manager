from flask import Response, jsonify


def error_response(
    code: str,
    message: str,
    status: int,
    details: list[dict[str, str]] | None = None,
) -> tuple[Response, int]:
    error: dict[str, object] = {"code": code, "message": message}

    if details is not None:
        error["details"] = details

    return jsonify(error=error), status
