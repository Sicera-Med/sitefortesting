from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.ai.base import AIProvider, AIProviderError
from app.ai.contract import (
    AIContractError,
    AIRequest,
    AIResult,
    ExplainRequest,
    PatientContext,
    parse_ai_response,
)
from app.core.errors import AIFailedError
from app.core.ids import new_id
from app.domain.models import Patient, Study, User
from app.services import audit
from app.store import Store

logger = logging.getLogger(__name__)


class AIService:
    """Вызов AI-провайдера + разбор ответа по контракту. Состояние не меняет."""

    def __init__(self, provider: AIProvider, store: Store, *, timeout_s: float) -> None:
        self.provider = provider
        self.store = store
        self.timeout_s = timeout_s

    @staticmethod
    def request_for_study(study: Study, patient: Patient) -> AIRequest:
        return AIRequest(
            request_id=new_id("req"),
            study_id=study.id,
            study_type=study.study_type,
            body_region=study.body_region,
            report_text=study.report_text,
            patient_context=PatientContext(
                age=patient.age_on(study.performed_at.date()), sex=patient.sex
            ),
        )

    @staticmethod
    def explain_request_for_study(study: Study) -> ExplainRequest:
        description = " ".join(f"{f.name}: {f.value.rstrip('.;')}." for f in study.sr_fields)
        return ExplainRequest(
            request_id=new_id("req"),
            study_type=study.study_type,
            body_region=study.body_region,
            description=description or None,
            conclusion=study.conclusion,
        )

    async def explain(self, request: ExplainRequest) -> dict[str, Any]:
        """B2C: {summary, terms} или AIFailedError — объяснение пациенту не критично."""
        try:
            async with asyncio.timeout(self.timeout_s):
                raw = await self.provider.explain(request)
        except TimeoutError as exc:
            raise AIFailedError(f"AI не ответил за {self.timeout_s:g} с") from exc
        except AIProviderError as exc:
            raise AIFailedError(f"Ошибка AI-сервиса: {exc}") from exc
        summary = raw.get("summary") if isinstance(raw, dict) else None
        if not isinstance(summary, str) or not summary.strip():
            raise AIFailedError("Объяснение AI не в нужном формате")
        terms = [
            {"term": str(t["term"]), "explanation": str(t["explanation"])}
            for t in raw.get("explanations") or []
            if isinstance(t, dict) and t.get("term") and t.get("explanation")
        ]
        return {"summary": summary.strip(), "terms": terms}

    async def run(self, request: AIRequest) -> tuple[AIResult, int]:
        """Возвращает (результат, latency_ms) или бросает AIFailedError."""
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_s):
                raw = await self.provider.analyze(request)
            result = parse_ai_response(raw, expected_request_id=request.request_id)
        except TimeoutError as exc:
            raise AIFailedError(f"AI не ответил за {self.timeout_s:g} с") from exc
        except AIProviderError as exc:
            raise AIFailedError(f"Ошибка AI-сервиса: {exc}") from exc
        except AIContractError as exc:
            raise AIFailedError(
                "Ответ AI не соответствует контракту", details={"reason": str(exc)}
            ) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)
        if result.warnings:
            logger.warning(
                "AI response normalized: request_id=%s warnings=%s",
                request.request_id,
                list(result.warnings),
            )
        return result, latency_ms

    @staticmethod
    def parse_manual(data: Any) -> AIResult:
        """Ручная загрузка JSON-ответа (§6.5): та же валидация, свой request_id."""
        try:
            return parse_ai_response(data, expected_request_id=new_id("req"))
        except AIContractError as exc:
            raise AIFailedError(
                "JSON не соответствует контракту AI", details={"reason": str(exc)}
            ) from exc

    async def test_bench(self, user: User, request: AIRequest) -> tuple[AIResult, int]:
        """Test bench для AI-команды: ничего не сохраняет, кроме события аудита."""
        try:
            result, latency_ms = await self.run(request)
        except AIFailedError as exc:
            audit.record(
                self.store,
                user,
                "ai.tested",
                target_type="ai",
                target_id=request.request_id,
                ok=False,
                error=exc.message,
            )
            raise
        audit.record(
            self.store,
            user,
            "ai.tested",
            target_type="ai",
            target_id=request.request_id,
            ok=True,
            recommendation=str(result.recommendation),
            latency_ms=latency_ms,
        )
        return result, latency_ms

    async def list_models(self) -> list[dict[str, str]]:
        return await self.provider.list_models()
