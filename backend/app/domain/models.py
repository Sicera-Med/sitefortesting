"""Доменные сущности. Чистый Python, без зависимостей от фреймворков.

Изменяемые сущности (Study, Notification) — обычные dataclass'ы;
неизменяемые (AIInference, AuditEvent) — frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.enums import (
    AISource,
    AppointmentStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    Role,
    Sex,
    StudyStatus,
    StudyType,
)


@dataclass(slots=True, kw_only=True)
class User:
    id: str
    role: Role
    email: str
    password_hash: str
    full_name: str
    # Профиль врача упрощён до одного поля (у head — None)
    specialty: str | None = None


@dataclass(slots=True, kw_only=True)
class Patient:
    id: str
    user_id: str
    full_name: str
    birth_date: date
    sex: Sex
    phone: str

    def age_on(self, day: date) -> int:
        before_birthday = (day.month, day.day) < (self.birth_date.month, self.birth_date.day)
        return day.year - self.birth_date.year - int(before_birthday)


@dataclass(slots=True, kw_only=True)
class Study:
    id: str
    patient_id: str
    treating_doctor_id: str
    study_type: StudyType
    body_region: str
    status: StudyStatus
    performed_at: datetime
    created_at: datetime
    report_text: str


@dataclass(frozen=True, slots=True)
class RankedOption:
    type: RecommendationType
    score: float


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    label: str
    weight: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AIInference:
    id: str
    study_id: str
    source: AISource
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float
    ranked_options: tuple[RankedOption, ...]
    reasons: tuple[Reason, ...]
    latency_ms: int
    created_at: datetime


@dataclass(slots=True, kw_only=True)
class Decision:
    id: str
    study_id: str
    doctor_id: str
    chosen_type: RecommendationType
    details: dict[str, Any]
    comment: str | None
    # Снапшот AI на момент решения (None — решение принято без AI)
    ai_inference_id: str | None
    ai_recommendation: RecommendationType | None
    ai_confidence: float | None
    accepted_ai: bool | None
    created_at: datetime


@dataclass(slots=True, kw_only=True)
class Notification:
    id: str
    decision_id: str
    study_id: str
    patient_id: str
    channel: NotificationChannel
    text: str
    status: NotificationStatus
    sent_at: datetime
    read_at: datetime | None = None
    patient_action: PatientActionType | None = None
    action_at: datetime | None = None
    appointment_id: str | None = None


@dataclass(slots=True, kw_only=True)
class Appointment:
    id: str
    patient_id: str
    doctor_id: str
    scheduled_for: datetime
    status: AppointmentStatus
    created_at: datetime
    notification_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    id: str
    actor_id: str | None
    actor_role: str | None
    action: str
    target_type: str
    target_id: str
    at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
