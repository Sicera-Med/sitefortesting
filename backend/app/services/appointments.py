from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clock import utcnow
from app.core.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.core.ids import new_id
from app.domain import rules, schedule
from app.domain.dictionaries import RESEARCH_TYPES
from app.domain.enums import (
    AppointmentStatus,
    NotificationStatus,
    PatientActionType,
    Role,
)
from app.domain.models import Appointment, Notification, Patient, User
from app.services import audit
from app.services.notifications import NotificationService, complete_study, reopen_study
from app.store import Store


@dataclass(slots=True)
class AppointmentView:
    appointment: Appointment
    patient: Patient
    doctor: User | None  # None — запись на исследование
    study_id: str | None  # по какому исследованию (если запись по уведомлению)


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
        if doctor is None or doctor.role is not Role.DOCTOR or not doctor.active:
            raise NotFoundError("Врач не найден", details={"doctor_id": doctor_id})
        return doctor

    def _research(self, code: str) -> str:
        if code not in RESEARCH_TYPES:
            raise NotFoundError("Исследование не найдено", details={"research_type": code})
        return code

    def _free(self, busy: set[datetime], start: date | None, days: int) -> list[DaySlots]:
        now = utcnow()
        start = start or now.astimezone(self.tz).date()
        result = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            free = schedule.free_slots(day, self.tz, now, busy)
            if free:
                result.append(DaySlots(day=day, slots=free))
        return result

    def slots(self, doctor_id: str, *, start: date | None = None, days: int = 7) -> list[DaySlots]:
        """Свободные слоты врача по дням (выходные и пустые дни пропускаются)."""
        self._doctor(doctor_id)
        return self._free(self.store.busy_slots(doctor_id=doctor_id), start, days)

    def research_slots(
        self, code: str, *, start: date | None = None, days: int = 7
    ) -> list[DaySlots]:
        """Свободное время кабинета исследования — рабочие часы те же, что у врачей."""
        self._research(code)
        return self._free(self.store.busy_slots(research_type=code), start, days)

    # --- Записи ---

    def _view(self, a: Appointment) -> AppointmentView:
        notification = self.store.get_notification(a.notification_id) if a.notification_id else None
        return AppointmentView(
            appointment=a,
            patient=self.store.get_patient(a.patient_id),
            doctor=self.store.get_user(a.doctor_id) if a.doctor_id else None,
            study_id=notification.study_id if notification else None,
        )

    def list(self, user: User, *, doctor_id: str | None = None) -> list[AppointmentView]:
        match user.role:
            case Role.PATIENT:
                patient = self.store.patient_by_user(user.id)
                items = self.store.list_appointments(patient_id=patient.id) if patient else []
            case Role.DOCTOR:
                if doctor_id not in (None, user.id):
                    raise ForbiddenError("Врач видит только своё расписание")
                items = self.store.list_appointments(doctor_id=user.id)
            case Role.CHIEF:
                # Главврач видит расписание любого врача
                items = self.store.list_appointments(doctor_id=doctor_id)
            case _:
                raise ForbiddenError("Нет доступа к записям")
        return [self._view(a) for a in items]

    def _check_requirement(
        self,
        notification: Notification,
        requirement: str | None,
        doctor: User | None,
        research_type: str | None,
    ) -> str:
        """Запись по уведомлению закрывает одно незакрытое направление из решения врача."""
        decision = self.store.get_decision(notification.decision_id)
        study = self.store.get_study(notification.study_id)
        required = {r.key: r for r in rules.required_bookings(decision)}
        req = required.get(requirement or "")
        if req is None:
            raise InvalidInputError(
                "Выберите направление из рекомендации врача",
                details={"requirement": requirement, "allowed": list(required)},
            )
        if not rules.fits_requirement(req, study, doctor, research_type):
            raise InvalidInputError(
                "Этот врач не подходит для выбранного направления",
                details={"requirement": req.key},
            )
        appointments = self.store.list_appointments(notification_id=notification.id)
        if req.key in rules.covered_keys(appointments):
            raise ConflictError("Вы уже записаны по этому направлению")
        return req.key

    def book(
        self,
        user: User,
        *,
        doctor_id: str | None = None,
        research_type: str | None = None,
        scheduled_for: datetime,
        notification_id: str | None = None,
        requirement: str | None = None,
    ) -> AppointmentView:
        if user.role is not Role.PATIENT:
            raise ForbiddenError("Записаться может только пациент")
        patient = self.store.patient_by_user(user.id)
        if patient is None:
            raise ForbiddenError("Профиль пациента не найден")
        if (doctor_id is None) == (research_type is None):
            raise InvalidInputError("Укажите врача или исследование")
        doctor = self._doctor(doctor_id) if doctor_id else None
        research = self._research(research_type) if research_type else None
        moment = scheduled_for.astimezone(UTC)
        now = utcnow()

        notification = None
        if notification_id:
            notification = NotificationService(self.store).own_notification(user, notification_id)
            if notification.patient_action is PatientActionType.DECLINED:
                raise ConflictError("Вы отказались от этой рекомендации")
            requirement = self._check_requirement(notification, requirement, doctor, research)
        elif research:
            raise InvalidInputError("На исследование записывают по направлению врача")
        else:
            requirement = None

        if not schedule.is_bookable(moment, now, self.tz):
            raise InvalidInputError(
                "Это время недоступно для записи",
                details={"scheduled_for": moment.isoformat()},
            )
        busy = (
            self.store.busy_slots(doctor_id=doctor.id)
            if doctor
            else self.store.busy_slots(research_type=research)
        )
        if moment in busy:
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
                doctor_id=doctor.id if doctor else None,
                research_type=research,
                scheduled_for=moment,
                status=AppointmentStatus.SCHEDULED,
                created_at=now,
                notification_id=notification.id if notification else None,
                requirement=requirement,
            )
        )
        target = {"doctor_id": doctor.id} if doctor else {"research_type": research}
        if notification:
            first = notification.patient_action is None
            notification.patient_action = PatientActionType.BOOKED
            if first:
                notification.action_at = now
            notification.appointment_id = appointment.id  # последняя запись
            if notification.read_at is None:
                notification.read_at = now
                notification.status = NotificationStatus.READ
            audit.record(
                self.store,
                user,
                "patient.booked",
                target_id=notification.study_id,
                appointment_id=appointment.id,
                requirement=requirement,
                scheduled_for=moment.isoformat(),
                **target,
            )
            self._sync_study(notification)
        else:
            audit.record(
                self.store,
                user,
                "appointment.created",
                target_type="appointment",
                target_id=appointment.id,
                scheduled_for=moment.isoformat(),
                **target,
            )
        return self._view(appointment)

    def _sync_study(self, notification: Notification) -> None:
        """Кейс закрыт, только когда пациент записан по всем направлениям решения."""
        decision = self.store.get_decision(notification.decision_id)
        appointments = self.store.list_appointments(notification_id=notification.id)
        if rules.all_covered(decision, appointments):
            complete_study(self.store, notification.study_id)
            notification.next_reminder_at = None  # записался — напоминать не о чем
        else:
            reopen_study(self.store, notification.study_id)
            # Отменил запись — снова напоминаем (если лимит напоминаний не исчерпан)
            if (
                notification.next_reminder_at is None
                and notification.reminders_sent < rules.MAX_REMINDERS
            ):
                notification.next_reminder_at = utcnow() + rules.REMINDER_INTERVAL

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
        notification = (
            self.store.get_notification(appointment.notification_id)
            if appointment.notification_id
            else None
        )
        audit.record(
            self.store,
            user,
            "appointment.cancelled",
            target_type="study" if notification else "appointment",
            target_id=notification.study_id if notification else appointment.id,
            appointment_id=appointment.id,
        )
        if notification:
            self._sync_study(notification)
        return self._view(appointment)
