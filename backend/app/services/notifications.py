from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.clock import utcnow
from app.core.errors import ConflictError, ForbiddenError, InvalidTransitionError, NotFoundError
from app.core.ids import new_id
from app.domain import rules
from app.domain.enums import NotificationChannel, NotificationStatus, PatientActionType, StudyStatus
from app.domain.models import Decision, Notification, Patient, Study, User
from app.domain.texts import notification_text
from app.services import audit
from app.store import Store

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PatientNotificationView:
    notification: Notification
    decision: Decision
    study: Study
    treating_doctor: User
    suggested_specialty: str | None
    suggested_doctors: list[User]


class NotificationService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # --- Врач ---

    def notify(
        self, user: User, decision_id: str, channel: NotificationChannel | None
    ) -> Notification:
        decision = self.store.get_decision(decision_id)
        if decision is None:
            raise NotFoundError("Решение не найдено", details={"decision_id": decision_id})
        study = self.store.get_study(decision.study_id)
        if not rules.is_treating_doctor(user, study):
            raise ForbiddenError("Уведомление отправляет лечащий врач")
        if self.store.notification_for_decision(decision.id) is not None:
            raise ConflictError("Уведомление по этому решению уже отправлено")
        if not rules.can_transition(study.status, StudyStatus.NOTIFIED):
            raise InvalidTransitionError(
                "Уведомление можно отправить только после решения",
                details={"status": str(study.status)},
            )
        patient = self.store.get_patient(study.patient_id)
        channel = channel or NotificationChannel.SMS
        notification = self.store.add_notification(
            Notification(
                id=new_id("nt"),
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channel=channel,
                text=notification_text(decision.chosen_type, decision.details),
                status=NotificationStatus.SENT,
                sent_at=utcnow(),
            )
        )
        # Мок-адаптер: реальной отправки нет, только лог
        logger.info(
            "MOCK %s to %s (%s): %s", channel, patient.full_name, patient.phone, notification.text
        )
        study.status = StudyStatus.NOTIFIED
        audit.record(
            self.store, user, "notification.sent", target_id=study.id,
            notification_id=notification.id, channel=str(channel),
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
        specialty = rules.suggested_specialty(decision)
        doctors = self.store.list_doctors(specialty) if specialty else [treating]
        return PatientNotificationView(
            notification=notification,
            decision=decision,
            study=study,
            treating_doctor=treating,
            suggested_specialty=specialty,
            suggested_doctors=doctors,
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
                self.store, user, "notification.read", target_id=notification.study_id,
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
            self.store, user, "patient.declined", target_id=notification.study_id,
            notification_id=notification.id,
        )
        return self._view(notification)


def complete_study(store: Store, study_id: str) -> None:
    study = store.get_study(study_id)
    if rules.can_transition(study.status, StudyStatus.COMPLETED):
        study.status = StudyStatus.COMPLETED
