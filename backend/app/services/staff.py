"""Главврач управляет врачами: список с нагрузкой, добавление, изменение, отключение."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.clock import utcnow
from app.core.errors import ConflictError, InvalidInputError, NotFoundError
from app.core.ids import new_id
from app.core.security import hash_password
from app.domain import rules
from app.domain.dictionaries import SPECIALISTS
from app.domain.enums import AppointmentStatus, Role
from app.domain.models import User
from app.services import audit
from app.store import Store

MIN_PASSWORD = 4  # демо: без требований к сложности


@dataclass(slots=True)
class DoctorLoad:
    doctor: User
    open_studies: int  # ждут решения
    decisions: int
    upcoming_appointments: int  # записи на ближайшие 7 дней


def _specialty(code: str) -> str:
    if code not in SPECIALISTS:
        raise InvalidInputError("Неизвестная специальность", details={"specialty": code})
    return code


class StaffService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _doctor(self, doctor_id: str) -> User:
        doctor = self.store.get_user(doctor_id)
        if doctor is None or doctor.role is not Role.DOCTOR:
            raise NotFoundError("Врач не найден", details={"doctor_id": doctor_id})
        return doctor

    def _load(self, doctor: User) -> DoctorLoad:
        now = utcnow()
        studies = self.store.list_studies(doctor_id=doctor.id)
        return DoctorLoad(
            doctor=doctor,
            open_studies=sum(s.status in rules.DECIDABLE_STATUSES for s in studies),
            decisions=sum(d.doctor_id == doctor.id for d in self.store.list_decisions()),
            upcoming_appointments=sum(
                now <= a.scheduled_for <= now + timedelta(days=7)
                for a in self.store.list_appointments(
                    doctor_id=doctor.id, status=AppointmentStatus.SCHEDULED
                )
            ),
        )

    def doctors(self) -> list[DoctorLoad]:
        return [self._load(d) for d in self.store.list_doctors(include_inactive=True)]

    def create(
        self, actor: User, *, full_name: str, email: str, specialty: str, password: str
    ) -> DoctorLoad:
        full_name, email = full_name.strip(), email.strip().lower()
        if not full_name:
            raise InvalidInputError("Укажите ФИО")
        if self.store.user_by_email(email):
            raise ConflictError("Пользователь с таким email уже есть")
        if len(password) < MIN_PASSWORD:
            raise InvalidInputError(f"Пароль — не короче {MIN_PASSWORD} символов")
        doctor = self.store.add_user(
            User(
                id=new_id("usr"),
                role=Role.DOCTOR,
                email=email,
                password_hash=hash_password(password, rounds=4),
                full_name=full_name,
                specialty=_specialty(specialty),
            )
        )
        audit.record(self.store, actor, "staff.created", target_type="user", target_id=doctor.id)
        return self._load(doctor)

    def update(
        self,
        actor: User,
        doctor_id: str,
        *,
        full_name: str | None = None,
        specialty: str | None = None,
        active: bool | None = None,
    ) -> DoctorLoad:
        doctor = self._doctor(doctor_id)
        changes: dict[str, object] = {}
        if full_name is not None and full_name.strip() != doctor.full_name:
            if not full_name.strip():
                raise InvalidInputError("Укажите ФИО")
            doctor.full_name = changes["full_name"] = full_name.strip()
        if specialty is not None and specialty != doctor.specialty:
            doctor.specialty = changes["specialty"] = _specialty(specialty)
        if active is not None and active != doctor.active:
            doctor.active = changes["active"] = active
        if changes:
            audit.record(
                self.store,
                actor,
                "staff.updated",
                target_type="user",
                target_id=doctor.id,
                **changes,
            )
        return self._load(doctor)
