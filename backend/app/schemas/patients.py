from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel

from app.domain.enums import (
    AppointmentStatus,
    RecommendationType,
    StudyType,
)
from app.schemas.common import DoctorBrief
from app.schemas.studies import NotificationOut
from app.services.appointments import AppointmentView, DaySlots
from app.services.notifications import PatientNotificationView

# --- Уведомления ---


class NotificationStudyBrief(BaseModel):
    """Что пациент видит об исследовании: без текста заключения."""

    id: str
    study_type: StudyType
    body_region: str
    performed_at: datetime


class NotificationAppointmentOut(BaseModel):
    id: str
    doctor: DoctorBrief
    scheduled_for: datetime
    status: AppointmentStatus


class PatientNotificationOut(BaseModel):
    notification: NotificationOut
    recommendations: list[RecommendationType]
    details: dict[str, Any]
    comment: str | None
    study: NotificationStudyBrief
    treating_doctor: DoctorBrief
    suggested_specialties: list[str]
    suggested_doctors: list[DoctorBrief]
    only_treating_doctor: bool
    appointments: list[NotificationAppointmentOut]

    @classmethod
    def build(cls, v: PatientNotificationView) -> PatientNotificationOut:
        return cls(
            notification=NotificationOut.build(v.notification),
            recommendations=list(v.decision.chosen_types),
            details=v.decision.details,
            comment=v.decision.comment,
            study=NotificationStudyBrief(
                id=v.study.id,
                study_type=v.study.study_type,
                body_region=v.study.body_region,
                performed_at=v.study.performed_at,
            ),
            treating_doctor=DoctorBrief.build(v.treating_doctor),
            suggested_specialties=v.suggested_specialties,
            suggested_doctors=[DoctorBrief.build(d) for d in v.suggested_doctors],
            only_treating_doctor=v.only_treating_doctor,
            appointments=[
                NotificationAppointmentOut(
                    id=a.id,
                    doctor=DoctorBrief.build(doctor),
                    scheduled_for=a.scheduled_for,
                    status=a.status,
                )
                for a, doctor in v.appointments
            ],
        )


# --- Врачи и слоты ---


class DaySlotsOut(BaseModel):
    date: date
    slots: list[datetime]

    @classmethod
    def build(cls, d: DaySlots) -> DaySlotsOut:
        return cls(date=d.day, slots=d.slots)


# --- Записи ---


class AppointmentIn(BaseModel):
    doctor_id: str
    scheduled_for: AwareDatetime  # с часовым поясом, например 2026-10-05T10:00:00+03:00
    notification_id: str | None = None


class AppointmentPatch(BaseModel):
    status: AppointmentStatus


class AppointmentPatientBrief(BaseModel):
    id: str
    full_name: str
    phone: str


class AppointmentOut(BaseModel):
    id: str
    status: AppointmentStatus
    scheduled_for: datetime
    created_at: datetime
    notification_id: str | None
    doctor: DoctorBrief
    patient: AppointmentPatientBrief

    @classmethod
    def build(cls, v: AppointmentView) -> AppointmentOut:
        a = v.appointment
        return cls(
            id=a.id,
            status=a.status,
            scheduled_for=a.scheduled_for,
            created_at=a.created_at,
            notification_id=a.notification_id,
            doctor=DoctorBrief.build(v.doctor),
            patient=AppointmentPatientBrief(
                id=v.patient.id, full_name=v.patient.full_name, phone=v.patient.phone
            ),
        )
