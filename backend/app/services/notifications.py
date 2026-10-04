from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.clock import utcnow
from app.core.errors import ConflictError, ForbiddenError, InvalidTransitionError, NotFoundError
from app.core.ids import new_id
from app.domain import rules
from app.domain.enums import (
    AppointmentStatus,
    NotificationStatus,
    PatientActionType,
    StudyStatus,
)
from app.domain.models import Appointment, Decision, Notification, Patient, Study, User
from app.domain.texts import notification_text
from app.services import audit
from app.store import Store

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RequirementView:
    """Направление из решения врача и запись, которая его закрывает (если есть)."""

    requirement: rules.Requirement
    appointment: Appointment | None
    doctor: User | None  # врач записи; для повторного приёма до записи — лечащий врач


@dataclass(slots=True)
class PatientNotificationView:
    notification: Notification
    decision: Decision
    study: Study
    treating_doctor: User
    requirements: list[RequirementView]
    appointments: list[tuple[Appointment, User | None]]


class NotificationService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # --- Автоотправка после решения врача ---

    def notify(self, user: User, decision: Decision) -> Notification:
        """Уведомить пациента по решению — во все доступные каналы (мок-адаптер)."""
        study = self.store.get_study(decision.study_id)
        if self.store.notification_for_decision(decision.id) is not None:
            raise ConflictError("Уведомление по этому решению уже отправлено")
        if not rules.can_transition(study.status, StudyStatus.NOTIFIED):
            raise InvalidTransitionError(
                "Уведомление можно отправить только после решения",
                details={"status": str(study.status)},
            )
        patient = self.store.get_patient(study.patient_id)
        channels = rules.contact_channels(patient, self.store.get_user(patient.user_id))
        notification = self.store.add_notification(
            Notification(
                id=new_id("nt"),
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channels=channels,
                text=notification_text(decision.chosen_types, decision.details),
                status=NotificationStatus.SENT,
                sent_at=utcnow(),
            )
        )
        # Мок-адаптер: реальной отправки нет, только лог
        for channel in channels:
            logger.info("MOCK %s to %s: %s", channel, patient.full_name, notification.text)
        study.status = StudyStatus.NOTIFIED
        audit.record(
            self.store,
            user,
            "notification.sent",
            target_id=study.id,
            notification_id=notification.id,
            channels=[str(c) for c in channels],
        )
        return notification

    # --- Пациент ---

    def _patient(self, user: User) -> Patient:
        patient = self.store.patient_by_user(user.id)
        if patient is None:
            raise ForbiddenError("Профиль пациента не найден")
        return patient

    def own_notification(self, user: User, notification_id: str) -> Notification:
        notification = self.store.get_notification(notification_id)
        patient = self._patient(user)
        # Чужое уведомление выглядит как несуществующее
        if notification is None or notification.patient_id != patient.id:
            raise NotFoundError("Уведомление не найдено")
        return notification

    def _view(self, notification: Notification) -> PatientNotificationView:
        decision = self.store.get_decision(notification.decision_id)
        study = self.store.get_study(notification.study_id)
        treating = self.store.get_user(study.treating_doctor_id)
        appointments = self.store.list_appointments(notification_id=notification.id)
        return PatientNotificationView(
            notification=notification,
            decision=decision,
            study=study,
            treating_doctor=treating,
            requirements=requirement_views(self.store, decision, appointments, treating),
            appointments=[
                (a, self.store.get_user(a.doctor_id) if a.doctor_id else None) for a in appointments
            ],
        )

    def patient_notifications(self, user: User) -> list[PatientNotificationView]:
        patient = self._patient(user)
        return [self._view(n) for n in self.store.notifications_for_patient(patient.id)]

    def mark_read(self, user: User, notification_id: str) -> PatientNotificationView:
        notification = self.own_notification(user, notification_id)
        if notification.read_at is None:
            notification.read_at = utcnow()
            notification.status = NotificationStatus.READ
            audit.record(
                self.store,
                user,
                "notification.read",
                target_id=notification.study_id,
                notification_id=notification.id,
            )
        return self._view(notification)

    def decline(self, user: User, notification_id: str) -> PatientNotificationView:
        notification = self.own_notification(user, notification_id)
        if not rules.can_respond_to_notification(notification):
            raise ConflictError("Вы уже ответили на это уведомление")
        now = utcnow()
        notification.patient_action = PatientActionType.DECLINED
        notification.action_at = now
        if notification.read_at is None:
            notification.read_at = now
            notification.status = NotificationStatus.READ
        complete_study(self.store, notification.study_id)
        audit.record(
            self.store,
            user,
            "patient.declined",
            target_id=notification.study_id,
            notification_id=notification.id,
        )
        return self._view(notification)


def requirement_views(
    store: Store, decision: Decision, appointments: list[Appointment], treating: User
) -> list[RequirementView]:
    active = {
        a.requirement: a
        for a in appointments
        if a.requirement and a.status is AppointmentStatus.SCHEDULED
    }
    result = []
    for req in rules.required_bookings(decision):
        a = active.get(req.key)
        if a is not None:
            doctor = store.get_user(a.doctor_id) if a.doctor_id else None
        else:
            doctor = treating if req.kind == "treating" else None
        result.append(RequirementView(req, a, doctor))
    return result


def complete_study(store: Store, study_id: str) -> None:
    study = store.get_study(study_id)
    if rules.can_transition(study.status, StudyStatus.COMPLETED):
        study.status = StudyStatus.COMPLETED


def reopen_study(store: Store, study_id: str) -> None:
    """Пациент отменил запись — направление снова не закрыто, кейс ждёт записи."""
    study = store.get_study(study_id)
    if study.status is StudyStatus.COMPLETED:
        study.status = StudyStatus.NOTIFIED
