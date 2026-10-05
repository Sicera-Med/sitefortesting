from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)
from app.core.ids import new_id
from app.domain import rules
from app.domain.enums import (
    AppointmentStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    StudyStatus,
)
from app.domain.models import (
    Appointment,
    Decision,
    Delivery,
    Notification,
    Patient,
    Study,
    User,
)
from app.domain.texts import (
    SOCIAL_LABELS,
    notification_text,
    reminder_text,
    short_text,
    sms_reminder_text,
    sms_text,
    study_title,
)
from app.services import audit, channels
from app.services.cooldown import check_cooldown
from app.store import Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingText:
    """Что уходит в каналы: email / соцсеть — коротко со ссылкой, SMS — ещё короче."""

    message: str
    sms: str

    def for_channel(self, channel: NotificationChannel) -> str:
        return self.sms if channel is NotificationChannel.SMS else self.message


@dataclass(slots=True)
class RequirementView:
    """Направление из решения врача и запись, которая его закрывает (если есть)."""

    requirement: rules.Requirement
    appointment: Appointment | None
    doctor: User | None  # врач записи; для повторного приёма до записи — лечащий врач


@dataclass(slots=True)
class PatientStudyView:
    """Исследование глазами пациента: решение и уведомление — только когда уведомление ушло."""

    study: Study
    treating_doctor: User
    decision: Decision | None
    notification: Notification | None
    requirements: list[RequirementView]


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
        """Уведомить пациента по решению — во все доступные каналы (через очередь outbox)."""
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
        now = utcnow()
        nid = new_id("nt")
        text, short = patient_texts(self.store, decision, study, nid)
        notification = self.store.add_notification(
            Notification(
                id=nid,
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channels=channels,
                text=text,
                short_text=short.message,
                status=NotificationStatus.SENT,
                sent_at=now,
            )
        )
        deliver(self.store, notification, attempt=0, text=short, at=now)
        if rules.needs_booking(decision):
            notification.next_reminder_at = now + rules.REMINDER_INTERVAL
        study.status = StudyStatus.NOTIFIED
        audit.record(
            self.store,
            user,
            "notification.sent",
            target_id=study.id,
            notification_id=notification.id,
            channels=[str(c) for c in channels],
        )
        # Записываться некуда (патологии не выявлено) — кейс закрыт уведомлением
        if not rules.needs_booking(decision):
            complete_study(self.store, study.id)
        return notification

    # --- Пациент ---

    # --- Врач: «Напомнить сейчас» ---

    def remind(self, user: User, notification_id: str, *, cooldown_s: float = 0) -> Notification:
        """Следующее напоминание сразу, не дожидаясь недели (для демо на сцене)."""
        notification = self.store.get_notification(notification_id)
        if notification is None:
            raise NotFoundError("Уведомление не найдено")
        study = self.store.get_study(notification.study_id)
        if not rules.is_responsible(user, study):
            raise ForbiddenError("Напомнить может лечащий врач или главврач")
        decision = self.store.get_decision(notification.decision_id)
        appointments = self.store.list_appointments(notification_id=notification.id)
        if not rules.needs_reminder(notification, decision, appointments):
            raise ConflictError("Напоминать не о чем: пациент записался или отказался")
        if notification.reminders_sent >= rules.MAX_REMINDERS:
            raise ConflictError(f"Все {rules.MAX_REMINDERS} напоминания уже отправлены")
        now = utcnow()
        last = max((d.at for d in notification.deliveries), default=None)
        check_cooldown(last, now, cooldown_s, "Напомнить снова можно через {s} с")
        send_reminder(self.store, notification, now, actor=user)
        return notification

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

    def patient_studies(self, user: User) -> list[PatientStudyView]:
        """Все исследования пациента — и те, по которым врач ещё не решил. Без протокола."""
        patient = self._patient(user)
        result = []
        for study in self.store.list_studies(patient_id=patient.id):
            decision = self.store.decision_for_study(study.id)
            notification = self.store.notification_for_decision(decision.id) if decision else None
            treating = self.store.get_user(study.treating_doctor_id)
            requirements = (
                requirement_views(
                    self.store,
                    decision,
                    self.store.list_appointments(notification_id=notification.id),
                    treating,
                )
                if decision and notification
                else []
            )
            result.append(
                PatientStudyView(
                    study=study,
                    treating_doctor=treating,
                    decision=decision if notification else None,
                    notification=notification,
                    requirements=requirements,
                )
            )
        return sorted(result, key=lambda v: v.study.performed_at, reverse=True)

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
        if not rules.needs_booking(self.store.get_decision(notification.decision_id)):
            raise ConflictError("Записываться по этому уведомлению не нужно")
        now = utcnow()
        notification.patient_action = PatientActionType.DECLINED
        notification.action_at = now
        if notification.read_at is None:
            notification.read_at = now
            notification.status = NotificationStatus.READ
        complete_study(self.store, notification.study_id)
        notification.next_reminder_at = None  # отказался — не напоминаем
        audit.record(
            self.store,
            user,
            "patient.declined",
            target_id=notification.study_id,
            notification_id=notification.id,
        )
        return self._view(notification)


def notification_url(notification_id: str) -> str:
    """Ссылка из SMS / email / соцсети — на карточку рекомендации в кабинете."""
    return f"{get_settings().SITE_URL.rstrip('/')}/patient#n-{notification_id}"


def patient_texts(
    store: Store, decision: Decision, study: Study, notification_id: str
) -> tuple[str, OutgoingText]:
    """(подробный текст для сайта, короткие со ссылкой — для каналов)."""
    patient = store.get_patient(study.patient_id)
    doctor = store.get_user(decision.doctor_id)
    title = study_title(study.study_type, study.body_region)
    detailed = notification_text(
        decision.chosen_types,
        decision.details,
        patient_name=patient.full_name,
        doctor_name=doctor.full_name,
        study=title,
        performed=study.performed_at.date(),
    )
    urgent = RecommendationType.URGENT_HOSPITALIZATION in decision.chosen_types
    url = notification_url(notification_id)
    return detailed, OutgoingText(
        short_text(patient.full_name, title, url, urgent=urgent), sms_text(url, urgent=urgent)
    )


def reminder_for(store: Store, notification: Notification) -> OutgoingText:
    study = store.get_study(notification.study_id)
    patient = store.get_patient(notification.patient_id)
    url = notification_url(notification.id)
    return OutgoingText(
        reminder_text(patient.full_name, study_title(study.study_type, study.body_region), url),
        sms_reminder_text(url),
    )


def send_reminder(
    store: Store, notification: Notification, now: datetime, *, actor: User | None
) -> None:
    """Очередное напоминание: по расписанию (actor=None) или кнопкой врача."""
    notification.reminders_sent += 1
    deliver(
        store,
        notification,
        attempt=notification.reminders_sent,
        text=reminder_for(store, notification),
        at=now,
    )
    notification.next_reminder_at = (
        now + rules.REMINDER_INTERVAL if notification.reminders_sent < rules.MAX_REMINDERS else None
    )
    audit.record(
        store,
        actor,
        "notification.reminder",
        target_id=notification.study_id,
        notification_id=notification.id,
        attempt=notification.reminders_sent,
        of=rules.MAX_REMINDERS,
        manual=actor is not None,
    )


def delivery_targets(store: Store, patient: Patient) -> list[tuple[NotificationChannel, str]]:
    """Куда уходит уведомление: (канал, адрес) по всем включённым контактам пациента."""
    user = store.get_user(patient.user_id)
    targets: list[tuple[NotificationChannel, str]] = []
    for channel in rules.contact_channels(patient, user):
        match channel:
            case NotificationChannel.SMS:
                targets.append((channel, patient.phone))
            case NotificationChannel.EMAIL:
                targets.append((channel, patient.contact_email or user.email))
            case NotificationChannel.SOCIAL:
                targets += [
                    (channel, f"{SOCIAL_LABELS.get(s.network, s.network)} {s.handle}")
                    for s in patient.socials
                ]
    return targets


def deliver(
    store: Store, notification: Notification, *, attempt: int, text: OutgoingText, at: datetime
) -> list[Delivery]:
    """Доставки по всем контактам пациента: настоящие — в очередь outbox, остальные — имитация."""
    settings = get_settings()
    patient = store.get_patient(notification.patient_id)
    sent = []
    for channel, target in delivery_targets(store, patient):
        status, detail = channels.plan(settings, channel)
        body = text.for_channel(channel)
        logger.info("%s %s to %s (%s): %s", status, channel, target, patient.full_name, body)
        sent.append(
            Delivery(
                at=at,
                channel=channel,
                target=target,
                attempt=attempt,
                text=body,
                status=status,
                detail=detail,
            )
        )
    notification.deliveries.extend(sent)
    return sent


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
