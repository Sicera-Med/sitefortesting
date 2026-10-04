"""Бизнес-правила: переходы статусов Study и права на конкретный объект.

Функции чистые и возвращают bool — ошибки поднимает сервисный слой.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.enums import (
    AppointmentStatus,
    NotificationChannel,
    RecommendationType,
    Role,
    StudyStatus,
)
from app.domain.models import Appointment, Decision, Notification, Patient, Study, User

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
    # Пациент отменил одну из записей — направление снова не закрыто
    S.COMPLETED: frozenset({S.NOTIFIED}),
}

ANALYZABLE_STATUSES = frozenset({S.NEW, S.AI_READY, S.AI_FAILED})
DECIDABLE_STATUSES = frozenset({S.NEW, S.AI_READY, S.AI_FAILED})


def can_transition(src: StudyStatus, dst: StudyStatus) -> bool:
    return dst in TRANSITIONS[src]


def is_treating_doctor(user: User, study: Study) -> bool:
    return user.role is Role.DOCTOR and user.id == study.treating_doctor_id


STAFF_ROLES = frozenset({Role.DOCTOR, Role.CHIEF, Role.MANAGER})


def can_view_study(user: User, study: Study) -> bool:
    # Врачи видят любые Study (чужие — read-only), главврач и менеджер — все, пациент — никакие
    return user.role in STAFF_ROLES


def is_responsible(user: User, study: Study) -> bool:
    """Лечащий врач или главврач — тот, кто может решать по исследованию."""
    return user.role is Role.CHIEF or is_treating_doctor(user, study)


def can_analyze(user: User, study: Study) -> bool:
    return is_responsible(user, study)


def can_decide(user: User, study: Study) -> bool:
    return is_responsible(user, study)


def can_act(user: User, study: Study) -> bool:
    """Флаг для UI: может ли пользователь что-то делать со Study прямо сейчас."""
    return study.status is not S.COMPLETED and is_responsible(user, study)


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


def available_channels(patient: Patient, user: User | None) -> tuple[NotificationChannel, ...]:
    """Каналы, для которых у пациента есть контакт."""
    channels: list[NotificationChannel] = []
    if patient.phone:
        channels.append(NotificationChannel.SMS)
    if user is not None and user.email:
        channels.append(NotificationChannel.EMAIL)
    if patient.social:
        channels.append(NotificationChannel.SOCIAL)
    return tuple(channels)


def contact_channels(patient: Patient, user: User | None) -> tuple[NotificationChannel, ...]:
    """Куда уходит уведомление: доступные контакты, которые пациент не выключил."""
    return tuple(c for c in available_channels(patient, user) if c in patient.notify_channels)


def is_patient_self(user: User, patient: Patient) -> bool:
    return user.role is Role.PATIENT and patient.user_id == user.id


def can_respond_to_notification(notification: Notification) -> bool:
    """Пациент отвечает на уведомление один раз: запись или отказ."""
    return notification.patient_action is None


def needs_booking(decision: Decision) -> bool:
    """Есть ли куда записываться. «Патологии не выявлено» — кейс закрыт сразу."""
    return bool(required_bookings(decision))


# --- Направления, на которые пациент должен записаться ---

RequirementKind = Literal["treating", "specialist", "research"]


@dataclass(frozen=True, slots=True)
class Requirement:
    """Одно направление из решения врача: повторный приём, специалист или исследование."""

    kind: RequirementKind
    code: str | None = None  # специальность или вид исследования; у повторного приёма — None

    @property
    def key(self) -> str:
        return self.kind if self.code is None else f"{self.kind}:{self.code}"


def required_bookings(decision: Decision) -> list[Requirement]:
    """Куда пациенту записаться: кейс закрыт, только когда покрыто всё."""
    chosen = decision.chosen_types
    result: list[Requirement] = []
    if RecommendationType.REPEAT_APPOINTMENT in chosen:
        result.append(Requirement("treating"))
    if RecommendationType.SPECIALIST_CONSULT in chosen:
        result += [Requirement("specialist", c) for c in decision.details.get("specialists", [])]
    if RecommendationType.ADDITIONAL_RESEARCH in chosen:
        result += [Requirement("research", c) for c in decision.details.get("research_types", [])]
    return result


def covered_keys(appointments: Iterable[Appointment]) -> set[str]:
    return {
        a.requirement
        for a in appointments
        if a.requirement and a.status is AppointmentStatus.SCHEDULED
    }


def all_covered(decision: Decision, appointments: Iterable[Appointment]) -> bool:
    covered = covered_keys(appointments)
    return all(r.key in covered for r in required_bookings(decision))


def fits_requirement(
    req: Requirement, study: Study, doctor: User | None, research_type: str | None
) -> bool:
    """Подходит ли запись (врач или кабинет) под направление."""
    match req.kind:
        case "treating":
            return doctor is not None and doctor.id == study.treating_doctor_id
        case "specialist":
            return doctor is not None and doctor.specialty == req.code
        case "research":
            return doctor is None and research_type == req.code
    return False
