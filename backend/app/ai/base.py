from __future__ import annotations

from typing import Any, Protocol

from app.ai.contract import AIRequest
from app.domain.enums import AISource


class AIProviderError(Exception):
    """Провайдер не смог получить ответ (сеть, HTTP-ошибка, имитация сбоя)."""


class AIProvider(Protocol):
    source: AISource

    async def analyze(self, request: AIRequest) -> Any:
        """Сырой JSON-ответ по контракту §6.2. Разбор и валидация — в AIService."""
        ...

    async def list_models(self) -> list[dict[str, str]]: ...

    async def aclose(self) -> None: ...
