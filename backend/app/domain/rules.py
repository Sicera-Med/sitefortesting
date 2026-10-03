"""Бизнес-правила: переходы статусов Study и права на конкретный объект.

Функции чистые и возвращают bool — ошибки поднимает сервисный слой.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.enums import (
    NotificationChannel,
    RecommendationType,
    Role,
    StudyStatus,
)
from app.domain.models import Decision, Notification, Patient, Study, User

S = StudyStatus

# Единственный источник правды о переходах (SPEC §5.3).
# Анализ запускается автоматически; ai_failed → повтор. Решение врач может принять
# в любой момент до него — с AI или без.
TRANSITIONS: Mapping[StudyStatus, frozenset[StudyStatus]] = {
    S.NEW: frozenset({S.AI_READY, S.AI_FAILED, S.DECIDED}),
    S.AI_READY: frozenset({S.AI_READY, S.AI_FAILED, S.DECIDED}),
    S.AI_FAILED: frozenset({S.AI_READY, S.AI_FAILED, S.DECIDED}),
    S.DECIDED: frozenset({S.NOTIFIED}),
    S.NOTIFIED: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
}

ANALYZABLE_STATUSES = frozenset({S.NEW, S.AI_READY, S.AI_FAILED})
DECIDABLE_STATUSES = frozenset({S.NEW, S.AI_READY, S.AI_FAILED})


def can_transition(src: StudyStatus, dst: StudyStatus) -> bool:
    return dst in TRANSITIONS[src]


def is_treating_doctor(user: User, study: Study) -> bool:
    return user.role is Role.DOCTOR and user.id == study.treating_doctor_id


def can_view_study(user: User, study: Study) -> bool:
    # Врачи видят любые Study (чужие — read-only), head — все, пациент — никакие
    return user.role in (Role.DOCTOR, Role.HEAD)


def can_analyze(user: User, study: Study) -> bool:
    return user.role is Role.HEAD or is_treating_doctor(user, study)


def can_decide(user: User, study: Study) -> bool:
    return is_treating_doctor(user, study)


def can_act(user: User, study: Study) -> bool:
    """Флаг для UI: может ли пользователь что-то делать со Study прямо сейчас."""
    if study.status is S.COMPLETED:
        return False
    if is_treating_doctor(user, study):
        return True
    return can_analyze(user, study) and study.status in ANALYZABLE_STATUSES


def compute_accepted_ai(
    chosen: tuple[RecommendationType, ...], ai_recommendation: RecommendationType | None
) -> bool | None:
    """Согласие с AI: вариант AI есть среди выбранных врачом (врач мог и дополнить).

    None — AI-рекомендации не было (в agreement не учитывается).
    """
    if ai_recommendation is None:
        return None
    return ai_recommendation in chosen


def compute_details_match(
    chosen: tuple[RecommendationType, ...],
    details: dict[str, Any],
    ai_recommendation: RecommendationType | None,
    ai_details: dict[str, Any] | None,
) -> bool | None:
    """Совпали ли детали по варианту AI (набор специалистов / исследований).

    None — не с чем сравнивать: врач не выбрал вариант AI или AI деталей не предлагал.
    """
    if ai_recommendation is None or ai_recommendation not in chosen or not ai_details:
        return None
    key = DETAILS_KEY.get(ai_recommendation)
    if key is None or key not in ai_details:
        return None
    return set(details.get(key, [])) == set(ai_details[key])


# Какой ключ details относится к какому варианту
DETAILS_KEY: Mapping[RecommendationType, str] = {
    RecommendationType.SPECIALIST_CONSULT: "specialists",
    RecommendationType.ADDITIONAL_RESEARCH: "research_types",
}


def contact_channels(patient: Patient, user: User | None) -> tuple[NotificationChannel, ...]:
    """Все каналы, для которых у пациента есть контакт."""
    channels: list[NotificationChannel] = []
    if patient.phone:
        channels.append(NotificationChannel.SMS)
    if user is not None and user.email:
        channels.append(NotificationChannel.EMAIL)
    if patient.social:
        channels.append(NotificationChannel.SOCIAL)
    return tuple(channels)


def is_patient_self(user: User, patient: Patient) -> bool:
    return user.role is Role.PATIENT and patient.user_id == user.id


def can_respond_to_notification(notification: Notification) -> bool:
    """Пациент отвечает на уведомление один раз: запись или отказ."""
    return notification.patient_action is None


def only_treating_doctor(decision: Decision) -> bool:
    """Только повторный приём — записаться по уведомлению можно лишь к лечащему врачу."""
    return set(decision.chosen_types) == {RecommendationType.REPEAT_APPOINTMENT}


def needs_treating_doctor(decision: Decision) -> bool:
    """Повторный приём и доп. обследование назначает/проводит лечащий врач."""
    return bool(
        {RecommendationType.REPEAT_APPOINTMENT, RecommendationType.ADDITIONAL_RESEARCH}
        & set(decision.chosen_types)
    )


def suggested_specialties(decision: Decision) -> list[str]:
    """Специальности, к которым врач направил на консультацию."""
    if RecommendationType.SPECIALIST_CONSULT not in decision.chosen_types:
        return []
    return list(decision.details.get("specialists", []))
