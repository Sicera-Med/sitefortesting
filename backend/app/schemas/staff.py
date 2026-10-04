from __future__ import annotations

from pydantic import BaseModel

from app.services.staff import DoctorLoad


class StaffDoctorOut(BaseModel):
    id: str
    full_name: str
    email: str
    specialty: str | None
    active: bool
    open_studies: int
    decisions: int
    upcoming_appointments: int

    @classmethod
    def build(cls, v: DoctorLoad) -> StaffDoctorOut:
        d = v.doctor
        return cls(
            id=d.id,
            full_name=d.full_name,
            email=d.email,
            specialty=d.specialty,
            active=d.active,
            open_studies=v.open_studies,
            decisions=v.decisions,
            upcoming_appointments=v.upcoming_appointments,
        )


class StaffDoctorIn(BaseModel):
    full_name: str
    email: str
    specialty: str
    password: str


class StaffDoctorPatch(BaseModel):
    full_name: str | None = None
    specialty: str | None = None
    active: bool | None = None
