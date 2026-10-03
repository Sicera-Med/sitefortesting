from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import request_id_ctx

# Стандартные атрибуты LogRecord, которые не должны попадать в payload.
_STD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}

# Зарезервированные ключи payload — extra с такими именами не перезапишет их.
_RESERVED = {"ts", "level", "logger", "msg", "exc", "stack"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        # msg добавляем отдельно: _safe_message может захотеть записать
        # в payload информацию об ошибке форматирования.
        payload["msg"] = self._safe_message(record, payload)
        # request_id из контекста; явный extra={"request_id": ...} ниже перекроет его.
        payload["request_id"] = request_id_ctx.get()

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        collisions: list[str] = []
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS:
                continue
            if key in _RESERVED:
                collisions.append(key)
                continue
            payload[key] = value

        if collisions:
            bucket = payload.get("_extra_collisions")
            if not isinstance(bucket, dict):
                bucket = {}
                payload["_extra_collisions"] = bucket
            for key in collisions:
                bucket[key] = record.__dict__[key]

        return self._safe_dumps(payload)

    @staticmethod
    def _safe_message(record: logging.LogRecord, payload: dict[str, Any]) -> str:
        try:
            return record.getMessage()
        except Exception as exc:
            # record.message ещё не создан — getMessage() упал до присваивания.
            payload["msg_format_error"] = repr(exc)
            return str(record.msg)

    @staticmethod
    def _safe_dumps(payload: dict[str, Any]) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception as exc:
            # Например, циклические ссылки в extra или падающий __str__.
            fallback: dict[str, Any] = {
                "ts": payload.get("ts"),
                "level": payload.get("level"),
                "logger": payload.get("logger"),
                "msg": payload.get("msg"),
                "request_id": payload.get("request_id"),
                "json_dumps_error": repr(exc),
            }
            try:
                fallback["payload_repr"] = repr(payload)
            except Exception:
                fallback["payload_repr"] = "<unrepresentable>"
            return json.dumps(fallback, ensure_ascii=False, default=str)


def setup_logging(level: str | int = "INFO") -> None:
    """Настраивает root-логгер. Заменяет все существующие хендлеры.

    Логгеры uvicorn перенаправляются в root, чтобы их сообщения тоже шли
    через JsonFormatter.
    """
    if isinstance(level, str):
        level = level.upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn по умолчанию ставит propagate=False и свои хендлеры —
    # иначе JSON-формат не применится. Уровень NOTSET, чтобы он наследовался от root.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
        lg.setLevel(logging.NOTSET)
