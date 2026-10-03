from contextvars import ContextVar

# Текущий request_id: ставит RequestIdMiddleware, читают логи и аудит.
# Вынесен отдельно, чтобы сервисы не зависели от Starlette.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
