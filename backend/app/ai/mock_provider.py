"""Mock AI: отвечает заготовками из fixtures/responses.json (формат §6.2).

Выбор фикстуры детерминированный: среди подходящих по типу и области —
та, у которой больше совпадений ключевых слов; без совпадений — generic.
Маркер [[ai_fail]] в тексте заключения имитирует сбой AI.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from app.ai.base import AIProviderError
from app.ai.contract import AIRequest, ExplainRequest
from app.domain.enums import AISource

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "responses.json"
FAIL_MARKER = "[[ai_fail]]"


class MockAIProvider:
    source = AISource.MOCK

    def __init__(self, *, latency_ms: int = 0, fixtures_path: Path = FIXTURES_PATH) -> None:
        self.latency_ms = latency_ms
        self.fixtures: list[dict[str, Any]] = json.loads(fixtures_path.read_text("utf-8"))

    def pick(self, request: AIRequest) -> dict[str, Any]:
        text = request.report_text.lower()
        best, best_hits = None, 0
        fallback = None
        for fx in self.fixtures:
            match = fx["match"]
            if match["study_type"] is None and match["body_region"] is None:
                fallback = fallback or fx
                continue
            if match["study_type"] not in (None, request.study_type):
                continue
            if match["body_region"] not in (None, request.body_region):
                continue
            hits = sum(kw in text for kw in match["keywords"])
            if hits > best_hits:
                best, best_hits = fx, hits
        chosen = best or fallback
        if chosen is None:
            raise AIProviderError("no mock fixture matches the request")
        return chosen

    async def analyze(self, request: AIRequest) -> Any:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        if FAIL_MARKER in request.report_text:
            raise AIProviderError("simulated AI failure ([[ai_fail]] marker)")
        response = copy.deepcopy(self.pick(request)["response"])
        response["request_id"] = request.request_id
        return response

    async def explain(self, request: ExplainRequest) -> Any:
        """Тестовое объяснение (только в тестах — mock запрещён вне APP_ENV=test)."""
        if FAIL_MARKER in f"{request.description} {request.conclusion}":
            raise AIProviderError("simulated AI failure ([[ai_fail]] marker)")
        return {
            "summary": "Тестовое объяснение результата.",
            "explanations": [{"term": "КТИ", "explanation": "тестовое объяснение термина"}],
            "request_id": request.request_id,
        }

    async def list_models(self) -> list[dict[str, str]]:
        seen: dict[tuple[str, str], None] = {}
        for fx in self.fixtures:
            m = fx["response"]["model"]
            seen[(m["name"], m["version"])] = None
        return [{"name": n, "version": v, "source": "mock"} for n, v in seen]

    async def aclose(self) -> None:
        return None
