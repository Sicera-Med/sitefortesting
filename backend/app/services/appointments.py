from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clock import utcnow
from app.core.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.core.ids import new_id
from app.domain import rules, schedule
from app.domain.enums import (
    AppointmentStatus,
    NotificationStatus,
    PatientActionType,
    Role,
)
from app.domain.models import Appointment, Patient, User
from app.services import audit
from app.services.notifications import NotificationService, complete_study
from app.store import Store


@dataclass(slots=True)
class AppointmentView:
    appointment: Appointment
    patient: Patient
    doctor: User


@dataclass(slots=True)
class DaySlots:
    day: date
    slots: list[datetime]


class AppointmentService:
    def __init__(self, store: Store, *, tz: str) -> None:
        self.store = store
        self.tz = ZoneInfo(tz)

    # --- Врачи и слоты ---

    def doctors(self, specialty: str | None = None) -> list[User]:
        return self.store.list_doctors(specialty)

    def _doctor(self, doctor_id: str) -> User:
        doctor = self.store.get_user(doctor_id)
        if doctor is None or doctor.role is not Role.DOCTOR:
            raise NotFoundError("Врач не найден", details={"doctor_id": doctor_id})
        return doctor

    def slots(self, doctor_id: str, *, start: date | None = None, days: int = 7) -> list[DaySlots]:
        """Свободные слоты врача по дням (выходные и пустые дни пропускаются)."""
        self._doctor(doctor_id)
        now = utcnow()
        start = start or now.astimezone(self.tz).date()
        busy = self.store.busy_slots(doctor_id)
        result = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            free = schedule.free_slots(day, self.tz, now, busy)
            if free:
                result.append(DaySlots(day=day, slots=free))
        return result

    # --- Записи ---

    def _view(self, a: Appointment) -> AppointmentView:
        return AppointmentView(
            appointment=a,
            patient=self.store.get_patient(a.patient_id),
            doctor=self.store.get_user(a.doctor_id),
        )

    def list(self, user: User) -> list[AppointmentView]:
        match user.role:
            case Role.PATIENT:
                patient = self.store.patient_by_user(user.id)
                items = self.store.list_appointments(patient_id=patient.id) if patient else []
            case Role.DOCTOR:
                items = self.store.list_appointments(doctor_id=user.id)
            case _:
                items = self.store.list_appointments()
        return [self._view(a) for a in items]

    def book(
        self,
        user: User,
        *,
        doctor_id: str,
        scheduled_for: datetime,
        notification_id: str | None = None,
    ) -> AppointmentView:
        if user.role is not Role.PATIENT:
            raise ForbiddenError("Записаться может только пациент")
        patient = self.store.patient_by_user(user.id)
        if patient is None:
            raise ForbiddenError("Профиль пациента не найден")
        doctor = self._doctor(doctor_id)
        moment = scheduled_for.astimezone(UTC)
        now = utcnow()

        notification = None
        if notification_id:
            notification = NotificationService(self.store).own_notification(user, notification_id)
            if notification.patient_action is PatientActionType.DECLINED:
                raise ConflictError("Вы отказались от этой рекомендации")
            # По одному уведомлению можно записаться к нескольким врачам — но не дважды к одному
            already = self.store.list_appointments(
                notification_id=notification.id,
                doctor_id=doctor.id,
                status=AppointmentStatus.SCHEDULED,
            )
            if already:
                raise ConflictError("Вы уже записаны к этому врачу по этой рекомендации")
            decision = self.store.get_decision(notification.decision_id)
            study = self.store.get_study(notification.study_id)
            if (
                decision
                and study
                and rules.only_treating_doctor(decision)
                and doctor.id != study.treating_doctor_id
            ):
                raise InvalidInputError(
                    "Повторный приём — только у лечащего врача",
                    details={"doctor_id": study.treating_doctor_id},
                )

        if not schedule.is_bookable(moment, now, self.tz):
            raise InvalidInputError(
                "Это время недоступно для записи",
                details={"scheduled_for": moment.isoformat()},
            )
        if moment in self.store.busy_slots(doctor.id):
            raise ConflictError("Это время уже занято, выберите другое")
        clash = any(
            a.scheduled_for == moment
            for a in self.store.list_appointments(
                patient_id=patient.id, status=AppointmentStatus.SCHEDULED
            )
        )
        if clash:
            raise ConflictError("У вас уже есть запись на это время")

        appointment = self.store.add_appointment(
            Appointment(
                id=new_id("ap"),
                patient_id=patient.id,
                doctor_id=doctor.id,
                scheduled_for=moment,
                status=AppointmentStatus.SCHEDULED,
                created_at=now,
                notification_id=notification.id if notification else None,
            )
        )
        if notification:
            first = notification.patient_action is None
            notification.patient_action = PatientActionType.BOOKED
            if first:
                notification.action_at = now
            notification.appointment_id = appointment.id  # последняя запись
            if notification.read_at is None:
                notification.read_at = now
                notification.status = NotificationStatus.READ
            complete_study(self.store, notification.study_id)
            audit.record(
                self.store,
                user,
                "patient.booked",
                target_id=notification.study_id,
                appointment_id=appointment.id,
                doctor_id=doctor.id,
                scheduled_for=moment.isoformat(),
            )
        else:
            audit.record(
                self.store,
                user,
                "appointment.created",
                target_type="appointment",
                target_id=appointment.id,
                doctor_id=doctor.id,
                scheduled_for=moment.isoformat(),
            )
        return self._view(appointment)

    def cancel(self, user: User, appointment_id: str) -> AppointmentView:
        appointment = self.store.get_appointment(appointment_id)
        if appointment is None:
            raise NotFoundError("Запись не найдена")
        patient = self.store.patient_by_user(user.id) if user.role is Role.PATIENT else None
        allowed = (patient is not None and appointment.patient_id == patient.id) or (
            user.role is Role.DOCTOR and appointment.doctor_id == user.id
        )
        if not allowed:
            raise ForbiddenError("Отменить можно только свою запись")
        if appointment.status is AppointmentStatus.CANCELLED:
            raise ConflictError("Запись уже отменена")
        appointment.status = AppointmentStatus.CANCELLED
        audit.record(
            self.store,
            user,
            "appointment.cancelled",
            target_type="appointment",
            target_id=appointment.id,
        )
        return self._view(appointment)
