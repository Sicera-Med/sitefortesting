"""Автоанализ: исследования уходят в AI без участия врача (SPEC §5.3).

Новое исследование анализируется сразу; если AI не ответил — повторяем через AI_RETRY_S,
пока не ответит или пока врач не примет решение (тогда анализ уже не нужен).
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.errors import AIFailedError
from app.domain.enums import StudyStatus
from app.services.studies import StudyService

logger = logging.getLogger(__name__)


class AutoAnalyzer:
    def __init__(self, service: StudyService, *, poll_s: float, retry_s: float) -> None:
        self.service = service
        self.poll_s = poll_s
        self.retry_s = retry_s
        self._last_attempt: dict[str, float] = {}

    def _due(self) -> list[str]:
        now = time.monotonic()
        due = []
        for study in self.service.store.studies.values():
            if study.status is StudyStatus.NEW:
                due.append(study.id)
            elif study.status is StudyStatus.AI_FAILED:
                last = self._last_attempt.get(study.id)
                if last is None or now - last >= self.retry_s:
                    due.append(study.id)
        return due

    async def run_once(self) -> int:
        """Один проход: анализирует всё, что пора. Возвращает число попыток."""
        due = self._due()
        for study_id in due:
            self._last_attempt[study_id] = time.monotonic()
            try:
                await self.service.analyze_auto(study_id)
            except AIFailedError as exc:
                logger.warning("auto-analyze failed: study=%s error=%s", study_id, exc.message)
            except Exception:  # воркер не должен умирать из-за одной ошибки
                logger.exception("auto-analyze crashed: study=%s", study_id)
        return len(due)

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.poll_s)
