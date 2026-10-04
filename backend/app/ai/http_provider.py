"""HTTP AI: ходит в сервис AI-команды по контракту §6 (POST /ai/v1/analyze)."""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.base import AIProviderError
from app.ai.contract import AIRequest, ExplainRequest
from app.domain.enums import AISource

ANALYZE_PATH = "/ai/v1/analyze"
EXPLAIN_PATH = "/ai/v1/explain"


def _error_text(response: httpx.Response) -> str:
    """Понятная причина сбоя: detail от ai_service (FastAPI) или начало тела ответа."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str) and detail:
        return detail
    return f"AI service returned HTTP {response.status_code}: {response.text[:300]}"


class HttpAIProvider:
    source = AISource.HTTP

    def __init__(
        self, *, base_url: str, timeout_s: float, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url = base_url
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def analyze(self, request: AIRequest) -> Any:
        return await self._post(ANALYZE_PATH, request.model_dump(mode="json"))

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI service timeout") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"AI service unavailable: {exc.__class__.__name__}") from exc

        if response.is_error:
            raise AIProviderError(_error_text(response))
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("AI service returned invalid JSON") from exc

    async def explain(self, request: ExplainRequest) -> Any:
        return await self._post(EXPLAIN_PATH, request.model_dump(mode="json"))

    async def list_models(self) -> list[dict[str, str]]:
        # Отдельного эндпоинта моделей в контракте нет — модель видна в каждом ответе
        return [{"name": "remote", "version": "see responses", "source": "http"}]

    async def aclose(self) -> None:
        await self._client.aclose()
