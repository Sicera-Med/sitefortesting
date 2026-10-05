"""Лимит частоты повторных действий: отправка в AI, объяснение пациенту, «Напомнить сейчас».

Бережёт кредиты модели и SMS: двойной клик или две открытые вкладки не порождают лишних
запросов. Ответ — 429 с retry_after_s, фронтенд показывает обратный отсчёт.
"""

from __future__ import annotations

import math
from datetime import datetime

from app.core.errors import TooManyRequestsError


def check_cooldown(last: datetime | None, now: datetime, cooldown_s: float, message: str) -> None:
    """Не прошло cooldown_s секунд с last — TooManyRequestsError.

    message — текст ошибки; «{s}» в нём заменяется на число секунд до следующей попытки.
    """
    if last is None:
        return
    wait = cooldown_s - (now - last).total_seconds()
    if wait > 0:
        seconds = math.ceil(wait)
        raise TooManyRequestsError(message.format(s=seconds), details={"retry_after_s": seconds})
