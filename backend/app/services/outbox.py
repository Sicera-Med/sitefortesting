"""Очередь отправки уведомлений: доставки со статусом pending уходят через services/channels.py.

deliver() только ставит доставку в очередь — решение врача не ждёт SMS и SMTP. Воркер раз в
NOTIFY_OUTBOX_POLL_S секунд отправляет их по одной в потоке и ставит sent / failed.
В тестах воркер выключен, функция отправки подменена.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.domain.enums import DeliveryStatus, NotificationChannel
from app.domain.models import Delivery, Notification
from app.store import Store

logger = logging.getLogger(__name__)

# (канал, адрес, текст) → None; ошибка канала — исключение
SendFn = Callable[[NotificationChannel, str, str], None]


class OutboxService:
    def __init__(self, store: Store, send: SendFn, *, poll_s: float = 2) -> None:
        self.store = store
        self.send = send
        self.poll_s = poll_s

    def pending(self) -> list[tuple[Notification, Delivery]]:
        return [
            (n, d)
            for n in self.store.list_notifications()
            for d in n.deliveries
            if d.status is DeliveryStatus.PENDING
        ]

    def send_one(self, notification: Notification, delivery: Delivery) -> None:
        try:
            self.send(delivery.channel, delivery.target, delivery.text)
        except Exception as exc:  # ошибка одного канала не мешает остальным
            delivery.status = DeliveryStatus.FAILED
            delivery.detail = str(exc)[:300] or exc.__class__.__name__
            logger.warning(
                "delivery failed: %s %s (%s): %s",
                delivery.channel,
                delivery.target,
                notification.id,
                delivery.detail,
            )
        else:
            delivery.status = DeliveryStatus.SENT
            logger.info(
                "delivery sent: %s %s (%s)", delivery.channel, delivery.target, notification.id
            )

    def run_once(self) -> int:
        """Отправить всё из очереди (синхронно — для тестов). Возвращает число попыток."""
        items = self.pending()
        for n, d in items:
            self.send_one(n, d)
        return len(items)

    async def run_forever(self) -> None:
        while True:
            try:
                for n, d in self.pending():
                    await asyncio.to_thread(self.send_one, n, d)
            except Exception:  # воркер не должен умирать из-за одной ошибки
                logger.exception("outbox crashed")
            await asyncio.sleep(self.poll_s)
