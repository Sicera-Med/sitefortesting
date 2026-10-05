from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain import rules
from app.domain.enums import (
    AISource,
    AppointmentStatus,
    DeliveryStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    StudyStatus,
    StudyType,
)
from app.domain.models import AIInference, Appointment, AuditEvent, Decision, Notification, User
from app.schemas.common import BookingProgress, DoctorBrief, PatientBrief, RequirementOut
from app.services.studies import StudyView

# --- AI ---


class RankedOptionOut(BaseModel):
    type: RecommendationType
    score: float | None


class ReasonOut(BaseModel):
    code: str
    label: str
    weight: float | None


class SourceRefOut(BaseModel):
    """Документ, на котором основан пункт: КР Минздрава, методичка НПКЦ ДиТ и т. п."""

    text: str  # «КР «…» (Минздрав, 2025), стр. 89»
    document: str | None = None
    organization: str | None = None
    year: str | int | None = None
    pages: str | None = None
    url: str | None = None  # официальная страница документа (PDF — сразу на странице)


class AIItemOut(BaseModel):
    code: str
    reason: str | None
    timing: str | None
    source_refs: list[SourceRefOut]
    unconfirmed_sources: list[str]  # модель сослалась, но в документе такого действия нет


class AIOptionOut(BaseModel):
    type: RecommendationType
    recommended: bool
    rationale: str | None
    items: list[AIItemOut]
    source_refs: list[SourceRefOut]
    unconfirmed_sources: list[str]


class InferenceOut(BaseModel):
    id: str
    source: AISource
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float | None
    ranked_options: list[RankedOptionOut]
    reasons: list[ReasonOut]
    details: dict[str, Any]
    options: list[AIOptionOut]  # все варианты модели, основной первым ([] — старый формат)
    guidelines_mode: str | None
    latency_ms: int
    created_at: datetime

    @classmethod
    def build(cls, i: AIInference) -> InferenceOut:
        return cls(
            id=i.id,
            source=i.source,
            request_id=i.request_id,
            model_name=i.model_name,
            model_version=i.model_version,
            recommendation=i.recommendation,
            confidence=i.confidence,
            ranked_options=[RankedOptionOut(type=o.type, score=o.score) for o in i.ranked_options],
            reasons=[ReasonOut(code=r.code, label=r.label, weight=r.weight) for r in i.reasons],
            details=i.details,
            options=[AIOptionOut.model_validate(o) for o in i.options],
            guidelines_mode=i.guidelines_mode,
            latency_ms=i.latency_ms,
            created_at=i.created_at,
        )


class InferenceBrief(BaseModel):
    recommendation: RecommendationType
    confidence: float | None


# --- Решение ---


class StudyIn(BaseModel):
    """Новое исследование из сырых данных DICOM SR."""

    patient_id: str
    study_type: StudyType
    body_region: str
    description: str = Field(max_length=20_000)  # раздел «Описание»: строки «Поле- значение»
    performed_at: datetime | None = None
    treating_doctor_id: str | None = None  # главврач выбирает; врачу — он сам


class ReassignIn(BaseModel):
    doctor_id: str


class DecisionIn(BaseModel):
    # От одного до всех трёх вариантов
    chosen_types: list[RecommendationType] = Field(min_length=1, max_length=3)
    details: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def _legacy_single(cls, data: Any) -> Any:
        # Старый формат: один chosen_type
        if isinstance(data, dict) and "chosen_types" not in data and "chosen_type" in data:
            data = {**data, "chosen_types": [data["chosen_type"]]}
        return data


class DecisionOut(BaseModel):
    id: str
    study_id: str
    doctor_id: str
    chosen_types: list[RecommendationType]
    details: dict[str, Any]
    comment: str | None
    ai_inference_id: str | None
    ai_recommendation: RecommendationType | None
    ai_confidence: float | None
    accepted_ai: bool | None
    ai_details: dict[str, Any] | None
    details_match: bool | None
    created_at: datetime

    @classmethod
    def build(cls, d: Decision) -> DecisionOut:
        return cls(
            id=d.id,
            study_id=d.study_id,
            doctor_id=d.doctor_id,
            chosen_types=list(d.chosen_types),
            details=d.details,
            comment=d.comment,
            ai_inference_id=d.ai_inference_id,
            ai_recommendation=d.ai_recommendation,
            ai_confidence=d.ai_confidence,
            accepted_ai=d.accepted_ai,
            ai_details=d.ai_details,
            details_match=d.details_match,
            created_at=d.created_at,
        )


class DecisionBrief(BaseModel):
    chosen_types: list[RecommendationType]
    accepted_ai: bool | None


# --- Уведомление и запись (в карточке) ---


class DeliveryOut(BaseModel):
    at: datetime
    channel: NotificationChannel
    target: str  # телефон, email или «Telegram @…»
    attempt: int  # 0 — первое уведомление, 1.. — напоминания
    text: str  # что ушло в канал (коротко, со ссылкой на сайт)
    status: DeliveryStatus  # pending / sent / failed / simulated
    detail: str | None  # ошибка канала или почему имитация


class NotificationOut(BaseModel):
    id: str
    decision_id: str
    channels: list[NotificationChannel]
    text: str  # подробный — для сайта
    short_text: str  # короткий со ссылкой — для SMS / email / соцсетей
    status: NotificationStatus
    sent_at: datetime
    read_at: datetime | None
    patient_action: PatientActionType | None
    action_at: datetime | None
    appointment_id: str | None
    # История отправок (имитация каналов) и напоминания
    deliveries: list[DeliveryOut]
    reminders_sent: int
    max_reminders: int
    next_reminder_at: datetime | None

    @classmethod
    def build(cls, n: Notification) -> NotificationOut:
        return cls(
            id=n.id,
            decision_id=n.decision_id,
            channels=list(n.channels),
            text=n.text,
            short_text=n.short_text,
            status=n.status,
            sent_at=n.sent_at,
            read_at=n.read_at,
            patient_action=n.patient_action,
            action_at=n.action_at,
            appointment_id=n.appointment_id,
            deliveries=[
                DeliveryOut(
                    at=d.at,
                    channel=d.channel,
                    target=d.target,
                    attempt=d.attempt,
                    text=d.text,
                    status=d.status,
                    detail=d.detail,
                )
                for d in n.deliveries
            ],
            reminders_sent=n.reminders_sent,
            max_reminders=rules.MAX_REMINDERS,
            next_reminder_at=n.next_reminder_at,
        )


class CardAppointmentOut(BaseModel):
    id: str
    doctor: DoctorBrief | None  # None — запись на исследование
    research_type: str | None
    requirement: str | None
    scheduled_for: datetime
    status: AppointmentStatus

    @classmethod
    def build(cls, a: Appointment, doctor: User | None) -> CardAppointmentOut:
        return cls(
            id=a.id,
            doctor=DoctorBrief.build(doctor) if doctor else None,
            research_type=a.research_type,
            requirement=a.requirement,
            scheduled_for=a.scheduled_for,
            status=a.status,
        )


# --- Study ---


class StudyListItem(BaseModel):
    id: str
    status: StudyStatus
    study_type: StudyType
    body_region: str
    performed_at: datetime
    patient: PatientBrief
    doctor: DoctorBrief
    ai: InferenceBrief | None
    decision: DecisionBrief | None
    booking: BookingProgress | None  # сколько направлений пациент уже закрыл записью
    ai_auto: bool  # автоотправка в AI включена; False — врач отправляет кнопкой
    can_act: bool

    @classmethod
    def build(cls, v: StudyView) -> StudyListItem:
        s = v.study
        return cls(
            id=s.id,
            status=s.status,
            study_type=s.study_type,
            body_region=s.body_region,
            performed_at=s.performed_at,
            patient=PatientBrief.build(v.patient, s.performed_at),
            doctor=DoctorBrief.build(v.doctor),
            ai=InferenceBrief(
                recommendation=v.inference.recommendation, confidence=v.inference.confidence
            )
            if v.inference
            else None,
            decision=DecisionBrief(
                chosen_types=list(v.decision.chosen_types), accepted_ai=v.decision.accepted_ai
            )
            if v.decision
            else None,
            booking=BookingProgress.build(v.requirements),
            ai_auto=v.ai_auto,
            can_act=v.can_act,
        )


class SRFieldOut(BaseModel):
    name: str
    value: str


class AIRetryOut(BaseModel):
    """Автоповтор после сбоя AI."""

    failures: int  # неудачных автоматических попыток подряд
    next_at: datetime | None  # следующая автоматическая попытка
    stopped: bool  # автоповтор остановлен — только ручная отправка


class StudyCard(BaseModel):
    id: str
    status: StudyStatus
    study_type: StudyType
    body_region: str
    performed_at: datetime
    created_at: datetime
    # Протокол: раздел «Описание» DICOM SR и заключение; report_text — как он уходит в AI
    sr_fields: list[SRFieldOut]
    report_text: str
    patient: PatientBrief
    doctor: DoctorBrief
    ai: InferenceOut | None
    decision: DecisionOut | None
    notification: NotificationOut | None
    appointments: list[CardAppointmentOut]
    requirements: list[RequirementOut]
    ai_retry: AIRetryOut | None  # есть, пока AI не ответил после сбоя
    ai_auto: bool  # автоотправка в AI включена; False — врач отправляет кнопкой
    ai_send_after: datetime | None  # раньше — повторно отправить нельзя (лимит частоты)
    can_act: bool

    @classmethod
    def build(cls, v: StudyView) -> StudyCard:
        s = v.study
        return cls(
            id=s.id,
            status=s.status,
            study_type=s.study_type,
            body_region=s.body_region,
            performed_at=s.performed_at,
            created_at=s.created_at,
            sr_fields=[SRFieldOut(name=f.name, value=f.value) for f in s.sr_fields],
            report_text=s.report_text,
            patient=PatientBrief.build(v.patient, s.performed_at),
            doctor=DoctorBrief.build(v.doctor),
            ai=InferenceOut.build(v.inference) if v.inference else None,
            decision=DecisionOut.build(v.decision) if v.decision else None,
            notification=NotificationOut.build(v.notification) if v.notification else None,
            appointments=[CardAppointmentOut.build(a, doctor) for a, doctor in v.appointments],
            requirements=[RequirementOut.build(r) for r in v.requirements],
            ai_retry=AIRetryOut(
                failures=s.ai_auto_failures,
                next_at=s.ai_next_retry_at,
                stopped=s.ai_auto_stopped,
            )
            if s.status is StudyStatus.AI_FAILED
            else None,
            ai_auto=v.ai_auto,
            ai_send_after=v.ai_send_after,
            can_act=v.can_act,
        )


class StudyHistoryOut(BaseModel):
    inferences: list[InferenceOut]
    decision: DecisionOut | None


class AuditEventOut(BaseModel):
    id: str
    action: str
    at: datetime
    actor_id: str | None
    actor_role: str | None
    actor_name: str | None
    payload: dict[str, Any]
    request_id: str | None

    @classmethod
    def build(cls, e: AuditEvent, actor: User | None) -> AuditEventOut:
        return cls(
            id=e.id,
            action=e.action,
            at=e.at,
            actor_id=e.actor_id,
            actor_role=e.actor_role,
            actor_name=actor.full_name if actor else None,
            payload=e.payload,
            request_id=e.request_id,
        )
