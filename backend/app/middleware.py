import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_response

logger = logging.getLogger(__name__)


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response_start(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, receive, track_response_start)
        except Exception:
            logger.exception(
                "Unhandled error during %s %s", scope["method"], scope["path"]
            )

            if response_started:
                raise

            response = error_response(
                500, "internal_error", "An unexpected error occurred."
            )
            await response(scope, receive, send)
