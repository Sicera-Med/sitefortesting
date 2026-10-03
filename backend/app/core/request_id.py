from __future__ import annotations

import re
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from ulid import ULID

REQUEST_ID_HEADER = "X-Request-ID"

# Текущий request_id; читается JSON-форматтером логов.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Принимаем входящий id только «безопасного» вида, иначе генерируем свой.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Чистый ASGI-middleware: берёт/генерирует request_id, кладёт его
    в contextvar, в request.state и в заголовок ответа."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if incoming and _VALID_ID.match(incoming) else str(ULID())

        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        token = request_id_ctx.set(request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(token)
