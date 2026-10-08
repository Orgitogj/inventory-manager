from flask import Response, jsonify


def error_response(code: str, message: str, status: int) -> tuple[Response, int]:
    return jsonify(error={"code": code, "message": message}), status
