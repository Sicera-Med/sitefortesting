"""Вычисляемое расписание врачей (SPEC §5.6): без таблиц расписаний.

Рабочее время одинаковое у всех врачей. Слоты считаются в часовом поясе клиники,
наружу отдаются в UTC.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WORK_START = time(9, 0)
WORK_END = time(17, 0)
SLOT = timedelta(minutes=30)
MIN_LEAD = timedelta(hours=1)  # записаться можно не раньше чем через час
HORIZON = timedelta(days=14)  # и не дальше чем на две недели


def day_slots(day: date, tz: ZoneInfo) -> list[datetime]:
    """Все слоты рабочего дня (UTC). В выходные — пусто."""
    if day.weekday() >= 5:
        return []
    start = datetime.combine(day, WORK_START, tzinfo=tz)
    end = datetime.combine(day, WORK_END, tzinfo=tz)
    slots = []
    t = start
    while t < end:
        slots.append(t.astimezone(UTC))
        t += SLOT
    return slots


def is_work_slot(moment: datetime, tz: ZoneInfo) -> bool:
    return moment.astimezone(UTC) in day_slots(moment.astimezone(tz).date(), tz)


def is_bookable(moment: datetime, now: datetime, tz: ZoneInfo) -> bool:
    return is_work_slot(moment, tz) and now + MIN_LEAD <= moment <= now + HORIZON


def free_slots(day: date, tz: ZoneInfo, now: datetime, busy: Iterable[datetime]) -> list[datetime]:
    taken = {b.astimezone(UTC) for b in busy}
    return [s for s in day_slots(day, tz) if s not in taken and is_bookable(s, now, tz)]
