from flask import request


def include_archived_requested() -> bool:
    return request.args.get("include_archived", "").lower() in {"1", "true", "yes"}
