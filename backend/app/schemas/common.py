from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from app.domain.enums import Role, Sex
from app.domain.models import Patient, User

if TYPE_CHECKING:
    from app.services.notifications import RequirementView


class UserOut(BaseModel):
    id: str
    role: Role
    email: str
    full_name: str
    specialty: str | None = None
    patient_id: str | None = None

    @classmethod
    def build(cls, user: User, patient: Patient | None = None) -> UserOut:
        return cls(
            id=user.id,
            role=user.role,
            email=user.email,
            full_name=user.full_name,
            specialty=user.specialty,
            patient_id=patient.id if patient else None,
        )


class DoctorBrief(BaseModel):
    id: str
    full_name: str
    specialty: str | None

    @classmethod
    def build(cls, user: User) -> DoctorBrief:
        return cls(id=user.id, full_name=user.full_name, specialty=user.specialty)


class PatientBrief(BaseModel):
    id: str
    full_name: str
    birth_date: date
    age: int
    sex: Sex

    @classmethod
    def build(cls, patient: Patient, on: datetime) -> PatientBrief:
        return cls(
            id=patient.id,
            full_name=patient.full_name,
            birth_date=patient.birth_date,
            age=patient.age_on(on.date()),
            sex=patient.sex,
        )


class RequirementOut(BaseModel):
    """Направление из решения врача и запись по нему."""

    key: str
    kind: Literal["treating", "specialist", "research"]
    code: str | None
    doctor: DoctorBrief | None
    appointment_id: str | None
    scheduled_for: datetime | None

    @classmethod
    def build(cls, v: RequirementView) -> RequirementOut:
        a = v.appointment
        return cls(
            key=v.requirement.key,
            kind=v.requirement.kind,
            code=v.requirement.code,
            doctor=DoctorBrief.build(v.doctor) if v.doctor else None,
            appointment_id=a.id if a else None,
            scheduled_for=a.scheduled_for if a else None,
        )


class BookingProgress(BaseModel):
    booked: int
    required: int

    @classmethod
    def build(cls, items: list[RequirementView]) -> BookingProgress | None:
        if not items:
            return None
        return cls(booked=sum(v.appointment is not None for v in items), required=len(items))
