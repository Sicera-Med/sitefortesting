"""Автоанализ: исследования уходят в AI без участия врача (SPEC §5.3).

Новое исследование анализируется сразу. Если AI не ответил — повтор через AI_RETRY_S
(по умолчанию 8 часов); после AI_MAX_AUTO_ATTEMPTS неудачных попыток подряд исследование
выходит из автоочереди — дальше только ручная отправка врачом. Решение врача анализ отменяет.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.core.clock import utcnow
from app.core.errors import AIFailedError
from app.domain.enums import StudyStatus
from app.domain.models import Study
from app.services import audit
from app.services.studies import StudyService

logger = logging.getLogger(__name__)


class AutoAnalyzer:
    def __init__(
        self, service: StudyService, *, poll_s: float, retry_s: float, max_attempts: int
    ) -> None:
        self.service = service
        self.poll_s = poll_s
        self.retry_s = retry_s
        self.max_attempts = max_attempts

    def _due(self) -> list[str]:
        """Новые — сразу; после сбоя — когда подошёл срок и автоповтор не остановлен."""
        now = utcnow()
        return [
            study.id
            for study in self.service.store.studies.values()
            if study.status is StudyStatus.NEW
            or (
                study.status is StudyStatus.AI_FAILED
                and not study.ai_auto_stopped
                and study.ai_next_retry_at is not None
                and now >= study.ai_next_retry_at
            )
        ]

    def _failed(self, study: Study) -> None:
        """Сбой автоматической попытки: следующая через retry_s или выход из автоочереди."""
        study.ai_auto_failures += 1
        if study.ai_auto_failures >= self.max_attempts:
            study.ai_auto_stopped = True
            study.ai_next_retry_at = None
            audit.record(
                self.service.store,
                None,
                "ai.auto_stopped",
                target_id=study.id,
                attempts=study.ai_auto_failures,
            )
        else:
            study.ai_next_retry_at = utcnow() + timedelta(seconds=self.retry_s)

    async def run_once(self) -> int:
        """Один проход: анализирует всё, что пора. Возвращает число попыток."""
        due = self._due()
        for study_id in due:
            study = self.service.store.get_study(study_id)
            try:
                await self.service.analyze_auto(
                    study_id, attempt=study.ai_auto_failures + 1, of=self.max_attempts
                )
            except AIFailedError as exc:
                logger.warning("auto-analyze failed: study=%s error=%s", study_id, exc.message)
                self._failed(study)
            except Exception:  # воркер не должен умирать из-за одной ошибки
                logger.exception("auto-analyze crashed: study=%s", study_id)
                self._failed(study)
        return len(due)

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.poll_s)
