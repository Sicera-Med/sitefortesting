"""Бизнес-правила: переходы статусов Study и права на конкретный объект.

Функции чистые и возвращают bool — ошибки поднимает сервисный слой.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.enums import RecommendationType, Role, StudyStatus
from app.domain.models import Decision, Notification, Patient, Study, User

S = StudyStatus

# Единственный источник правды о переходах (SPEC §5.3).
# ai_ready/ai_failed → ai_ready/ai_failed — повторный анализ.
TRANSITIONS: Mapping[StudyStatus, frozenset[StudyStatus]] = {
    S.NEW: frozenset({S.AI_READY, S.AI_FAILED}),
    S.AI_READY: frozenset({S.AI_READY, S.AI_FAILED, S.DECIDED}),
    S.AI_FAILED: frozenset({S.AI_READY, S.AI_FAILED, S.DECIDED}),
    S.DECIDED: frozenset({S.NOTIFIED}),
    S.NOTIFIED: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
}

ANALYZABLE_STATUSES = frozenset({S.NEW, S.AI_READY, S.AI_FAILED})
DECIDABLE_STATUSES = frozenset({S.AI_READY, S.AI_FAILED})


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
    chosen: RecommendationType, ai_recommendation: RecommendationType | None
) -> bool | None:
    """Согласие врача с AI. None — AI-рекомендации не было (в agreement не учитывается)."""
    if ai_recommendation is None:
        return None
    return chosen == ai_recommendation


# --- Пациент ---


def is_patient_self(user: User, patient: Patient) -> bool:
    return user.role is Role.PATIENT and patient.user_id == user.id


def can_respond_to_notification(notification: Notification) -> bool:
    """Пациент отвечает на уведомление один раз: запись или отказ."""
    return notification.patient_action is None


def suggested_specialty(decision: Decision) -> str | None:
    """Специальность врача, к которому стоит записаться по решению.

    None — записываться к лечащему врачу (повторный приём, доп. исследование).
    """
    if decision.chosen_type is RecommendationType.SPECIALIST_CONSULT:
        return decision.details.get("specialist")
    return None
