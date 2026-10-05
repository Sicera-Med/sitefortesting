"""Наполнение Store демо-набором из seed/data.py. Детерминировано относительно `now`:
одинаковая картина при каждом старте, даты «свежие» относительно момента запуска.

Сюжеты: Кузнецова получила уведомление, но ещё не записалась — её путь показываем вживую;
Иванов записан по одному направлению из двух; Соколову уже ушло напоминание; часть кейсов
закрыта. История доставок — всегда имитация: при старте ничего не отправляется.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.ids import new_id
from app.core.security import hash_password
from app.domain.enums import (
    AppointmentStatus,
    NotificationStatus,
    PatientActionType,
    Role,
    StudyStatus,
)
from app.domain.models import (
    Appointment,
    AuditEvent,
    Decision,
    Delivery,
    Notification,
    Patient,
    Study,
    User,
)
from app.domain.rules import (
    MAX_REMINDERS,
    REMINDER_INTERVAL,
    all_covered,
    contact_channels,
    needs_booking,
    needs_reminder,
)
from app.domain.sr import parse_sr
from app.seed.data import (
    DEMO_PASSWORD,
    EXTRA_APPOINTMENTS,
    PATIENTS,
    SOCIAL,
    STAFF,
    STUDIES,
    NotificationSpec,
    StudySpec,
)
from app.services.notifications import delivery_targets, patient_texts, reminder_for
from app.store import Store


def _slot(now: datetime, tz: ZoneInfo, days_ahead: int, hour: int, minute: int = 0) -> datetime:
    """Рабочий слот через N дней (выходные пропускаем вперёд до понедельника)."""
    day = now.astimezone(tz).date() + timedelta(days=days_ahead)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(UTC)


class _Seeder:
    def __init__(
        self,
        store: Store,
        now: datetime,
        tz: ZoneInfo,
        password_hash: str,
        contact_phone: str = "",
        contact_email: str = "",
    ) -> None:
        self.store = store
        self.now = now
        self.tz = tz
        self.pw = password_hash
        # Демо на сцене: у всех пациентов один телефон и почта — уведомления придут одному человеку
        self.contact_phone = contact_phone
        self.contact_email = contact_email or None
        self.users: dict[str, User] = {}
        self.patients: dict[str, Patient] = {}

    def audit(
        self, actor: User | None, action: str, study_id: str, at: datetime, **payload: Any
    ) -> None:
        self.store.append_audit(
            AuditEvent(
                id=new_id("ev"),
                actor_id=actor.id if actor else None,
                actor_role=str(actor.role) if actor else None,
                action=action,
                target_type="study",
                target_id=study_id,
                at=at,
                payload=payload,
            )
        )

    def run(self) -> None:
        for key, name, email, role, specialty in STAFF:
            self.users[key] = self.store.add_user(
                User(
                    id=new_id("usr"),
                    role=role,
                    email=email,
                    password_hash=self.pw,
                    full_name=name,
                    specialty=specialty,
                )
            )
        for key, name, email, birth, sex, phone in PATIENTS:
            user = self.store.add_user(
                User(
                    id=new_id("usr"),
                    role=Role.PATIENT,
                    email=email,
                    password_hash=self.pw,
                    full_name=name,
                )
            )
            self.patients[key] = self.store.add_patient(
                Patient(
                    id=new_id("pat"),
                    user_id=user.id,
                    full_name=name,
                    birth_date=birth,
                    sex=sex,
                    phone=self.contact_phone or phone,
                    contact_email=self.contact_email,
                    socials=SOCIAL.get(key, ()),
                )
            )
        for spec in STUDIES:
            self.study(spec)
        for patient_key, doctor_key, days, hour, minute in EXTRA_APPOINTMENTS:
            self.store.add_appointment(
                Appointment(
                    id=new_id("ap"),
                    patient_id=self.patients[patient_key].id,
                    doctor_id=self.users[doctor_key].id,
                    scheduled_for=_slot(self.now, self.tz, days, hour, minute),
                    status=AppointmentStatus.SCHEDULED,
                    created_at=self.now - timedelta(days=1),
                )
            )

    def study(self, spec: StudySpec) -> None:
        doctor = self.users[spec.doctor]
        patient = self.patients[spec.patient]
        performed_at = self.now - timedelta(days=spec.days_ago, hours=3)
        created_at = performed_at + timedelta(hours=1)
        study = self.store.add_study(
            Study(
                id=new_id("st"),
                patient_id=patient.id,
                treating_doctor_id=doctor.id,
                study_type=spec.study_type,
                body_region=spec.body_region,
                status=spec.status,
                performed_at=performed_at,
                created_at=created_at,
                sr_fields=tuple(parse_sr(spec.sr)[0]),
                conclusion=spec.conclusion,
            )
        )
        self.audit(doctor, "study.created", study.id, created_at)

        # Ответов AI в seed нет — их даёт только реальный сервис (автоанализ после старта).
        # Решения в истории приняты врачами без AI.
        if not spec.decision:
            return
        t = created_at + timedelta(hours=4)
        decision = self.store.add_decision(
            Decision(
                id=new_id("dc"),
                study_id=study.id,
                doctor_id=doctor.id,
                chosen_types=spec.decision.chosen_types,
                details=spec.decision.details,
                comment=spec.decision.comment,
                ai_inference_id=None,
                ai_recommendation=None,
                ai_confidence=None,
                accepted_ai=None,
                created_at=t,
            )
        )
        self.audit(
            doctor,
            "decision.created",
            study.id,
            t,
            decision_id=decision.id,
            chosen_types=[str(c) for c in decision.chosen_types],
            accepted_ai=None,
        )

        # Уведомление уходит сразу после решения (во все доступные каналы)
        n = spec.notification or NotificationSpec()
        t += timedelta(seconds=1)
        nid = new_id("nt")
        text, short = patient_texts(self.store, decision, study, nid)
        notification = self.store.add_notification(
            Notification(
                id=nid,
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channels=contact_channels(patient, self.store.get_user(patient.user_id)),
                text=text,
                short_text=short.message,
                status=NotificationStatus.SENT,
                sent_at=t,
            )
        )
        self.audit(
            doctor,
            "notification.sent",
            study.id,
            t,
            notification_id=notification.id,
            channels=[str(c) for c in notification.channels],
        )

        patient_user = self.store.get_user(patient.user_id)
        if n.read:
            t += timedelta(hours=3)
            notification.status = NotificationStatus.READ
            notification.read_at = t
            self.audit(
                patient_user, "notification.read", study.id, t, notification_id=notification.id
            )
        for requirement, doctor_key, days, hour in n.bookings:
            t += timedelta(hours=1)
            appointment = self.store.add_appointment(
                Appointment(
                    id=new_id("ap"),
                    patient_id=patient.id,
                    doctor_id=self.users[doctor_key].id if doctor_key else None,
                    research_type=None if doctor_key else requirement.split(":", 1)[1],
                    scheduled_for=_slot(self.now, self.tz, days, hour),
                    status=AppointmentStatus.SCHEDULED,
                    created_at=t,
                    notification_id=notification.id,
                    requirement=requirement,
                )
            )
            if notification.patient_action is None:
                notification.action_at = t
            notification.patient_action = PatientActionType.BOOKED
            notification.appointment_id = appointment.id
            self.audit(
                patient_user,
                "patient.booked",
                study.id,
                t,
                appointment_id=appointment.id,
                requirement=requirement,
            )
        # Кейс закрыт, только если записи есть по всем направлениям
        appointments = self.store.list_appointments(notification_id=notification.id)
        completed = study.status is StudyStatus.COMPLETED
        assert completed == all_covered(decision, appointments), spec.patient

        # История отправок: первое уведомление и напоминания раз в неделю, пока пациент
        # не записался (как делает services/reminders.py)
        targets = delivery_targets(self.store, patient)
        sent_at = notification.sent_at
        notification.deliveries = [
            Delivery(sent_at, c, target, 0, short.for_channel(c)) for c, target in targets
        ]
        if not needs_booking(decision):
            return
        due = sent_at + REMINDER_INTERVAL
        while (
            needs_reminder(notification, decision, appointments)
            and notification.reminders_sent < MAX_REMINDERS
            and due <= self.now
        ):
            notification.reminders_sent += 1
            notification.deliveries += [
                Delivery(
                    due,
                    c,
                    target,
                    notification.reminders_sent,
                    reminder_for(self.store, notification).for_channel(c),
                )
                for c, target in targets
            ]
            self.audit(
                None,
                "notification.reminder",
                study.id,
                due,
                notification_id=notification.id,
                attempt=notification.reminders_sent,
                of=MAX_REMINDERS,
            )
            due += REMINDER_INTERVAL
        if needs_reminder(notification, decision, appointments):
            notification.next_reminder_at = (
                due if notification.reminders_sent < MAX_REMINDERS else None
            )


def seed_demo(
    store: Store,
    *,
    now: datetime | None = None,
    tz: str = "Europe/Moscow",
    contact_phone: str = "",
    contact_email: str = "",
) -> None:
    """contact_phone / contact_email — общие контакты всех пациентов (DEMO_CONTACT_* в .env).

    История доставок seed — всегда имитация: при старте ничего не отправляется."""
    now = now or datetime.now(UTC)
    # rounds=4: демо-пароль, а быстрый старт важнее стойкости хеша (bcrypt по умолчанию ~0.25 с)
    password_hash = hash_password(DEMO_PASSWORD, rounds=4)
    _Seeder(store, now, ZoneInfo(tz), password_hash, contact_phone, contact_email).run()
