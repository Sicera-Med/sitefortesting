from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.domain.enums import Role, Sex
from app.domain.models import Patient, User


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
