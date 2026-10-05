"""Напоминания пациенту (SPEC §5.6): пока он не записался по всем направлениям и не отказался.

Раз в rules.REMINDER_INTERVAL (неделя), не больше rules.MAX_REMINDERS (3) раз.
Отправка — как и у первого уведомления: через очередь outbox.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.clock import utcnow
from app.domain import rules
from app.services.notifications import send_reminder
from app.store import Store

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(self, store: Store, *, poll_s: float = 60) -> None:
        self.store = store
        self.poll_s = poll_s

    def run_once(self) -> int:
        """Отправляет напоминания, срок которых подошёл. Возвращает число отправленных."""
        now = utcnow()
        sent = 0
        for n in self.store.list_notifications():
            if n.next_reminder_at is None or n.next_reminder_at > now:
                continue
            decision = self.store.get_decision(n.decision_id)
            appointments = self.store.list_appointments(notification_id=n.id)
            if not rules.needs_reminder(n, decision, appointments):
                n.next_reminder_at = None  # пациент записался или отказался
                continue
            send_reminder(self.store, n, now, actor=None)
            sent += 1
        return sent

    async def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception:  # воркер не должен умирать из-за одной ошибки
                logger.exception("reminders crashed")
            await asyncio.sleep(self.poll_s)
