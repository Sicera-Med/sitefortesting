from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    AISource,
    AppointmentStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    StudyStatus,
    StudyType,
)
from app.domain.models import AIInference, AuditEvent, Decision, Notification, User
from app.schemas.common import DoctorBrief, PatientBrief
from app.services.studies import StudyView

# --- AI ---


class RankedOptionOut(BaseModel):
    type: RecommendationType
    score: float


class ReasonOut(BaseModel):
    code: str
    label: str
    weight: float


class InferenceOut(BaseModel):
    id: str
    source: AISource
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float
    ranked_options: list[RankedOptionOut]
    reasons: list[ReasonOut]
    details: dict[str, Any]
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
            latency_ms=i.latency_ms,
            created_at=i.created_at,
        )


class InferenceBrief(BaseModel):
    recommendation: RecommendationType
    confidence: float


# --- Решение ---


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


class NotificationOut(BaseModel):
    id: str
    decision_id: str
    channels: list[NotificationChannel]
    text: str
    status: NotificationStatus
    sent_at: datetime
    read_at: datetime | None
    patient_action: PatientActionType | None
    action_at: datetime | None
    appointment_id: str | None

    @classmethod
    def build(cls, n: Notification) -> NotificationOut:
        return cls(
            id=n.id,
            decision_id=n.decision_id,
            channels=list(n.channels),
            text=n.text,
            status=n.status,
            sent_at=n.sent_at,
            read_at=n.read_at,
            patient_action=n.patient_action,
            action_at=n.action_at,
            appointment_id=n.appointment_id,
        )


class CardAppointmentOut(BaseModel):
    id: str
    doctor: DoctorBrief
    scheduled_for: datetime
    status: AppointmentStatus


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
            can_act=v.can_act,
        )


class StudyCard(BaseModel):
    id: str
    status: StudyStatus
    study_type: StudyType
    body_region: str
    performed_at: datetime
    created_at: datetime
    report_text: str
    patient: PatientBrief
    doctor: DoctorBrief
    ai: InferenceOut | None
    decision: DecisionOut | None
    notification: NotificationOut | None
    appointments: list[CardAppointmentOut]
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
            report_text=s.report_text,
            patient=PatientBrief.build(v.patient, s.performed_at),
            doctor=DoctorBrief.build(v.doctor),
            ai=InferenceOut.build(v.inference) if v.inference else None,
            decision=DecisionOut.build(v.decision) if v.decision else None,
            notification=NotificationOut.build(v.notification) if v.notification else None,
            appointments=[
                CardAppointmentOut(
                    id=a.id,
                    doctor=DoctorBrief.build(doctor),
                    scheduled_for=a.scheduled_for,
                    status=a.status,
                )
                for a, doctor in v.appointments
            ],
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
