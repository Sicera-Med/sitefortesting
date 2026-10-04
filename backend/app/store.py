"""In-memory хранилище (хакатон: без БД, данные живут до перезапуска).

Store только хранит и выбирает данные: никаких прав и бизнес-правил —
это забота сервисов и domain/rules.py. get_* возвращают None, если объекта нет.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from app.domain.enums import AppointmentStatus, Role, StudyStatus
from app.domain.models import (
    AIInference,
    Appointment,
    AuditEvent,
    Decision,
    Notification,
    Patient,
    Study,
    User,
)


class Store:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.patients: dict[str, Patient] = {}
        self.studies: dict[str, Study] = {}
        self.inferences: dict[str, AIInference] = {}
        self.decisions: dict[str, Decision] = {}
        self.notifications: dict[str, Notification] = {}
        self.appointments: dict[str, Appointment] = {}
        self.audit: list[AuditEvent] = []  # append-only
        self.ai_in_flight: set[str] = set()  # Study, по которым запрос в AI уже идёт
        self.ai_last_sent: dict[str, datetime] = {}  # когда Study последний раз ушло в AI

    # --- Users ---

    def add_user(self, user: User) -> User:
        if self.user_by_email(user.email) is not None:
            raise ValueError(f"duplicate email: {user.email}")
        self.users[user.id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def user_by_email(self, email: str) -> User | None:
        email = email.strip().lower()
        return next((u for u in self.users.values() if u.email.lower() == email), None)

    def list_doctors(
        self, specialty: str | None = None, *, include_inactive: bool = False
    ) -> list[User]:
        doctors = [
            u
            for u in self.users.values()
            if u.role is Role.DOCTOR
            and (include_inactive or u.active)
            and (specialty is None or u.specialty == specialty)
        ]
        return sorted(doctors, key=lambda u: u.full_name)

    # --- Patients ---

    def add_patient(self, patient: Patient) -> Patient:
        self.patients[patient.id] = patient
        return patient

    def get_patient(self, patient_id: str) -> Patient | None:
        return self.patients.get(patient_id)

    def patient_by_user(self, user_id: str) -> Patient | None:
        return next((p for p in self.patients.values() if p.user_id == user_id), None)

    # --- Studies ---

    def add_study(self, study: Study) -> Study:
        self.studies[study.id] = study
        return study

    def get_study(self, study_id: str) -> Study | None:
        return self.studies.get(study_id)

    def list_studies(
        self,
        *,
        doctor_id: str | None = None,
        patient_id: str | None = None,
        statuses: Iterable[StudyStatus] | None = None,
    ) -> list[Study]:
        wanted = set(statuses) if statuses else None
        result = [
            s
            for s in self.studies.values()
            if (doctor_id is None or s.treating_doctor_id == doctor_id)
            and (patient_id is None or s.patient_id == patient_id)
            and (wanted is None or s.status in wanted)
        ]
        return sorted(result, key=lambda s: s.performed_at, reverse=True)

    # --- AI inferences ---

    def add_inference(self, inference: AIInference) -> AIInference:
        self.inferences[inference.id] = inference
        return inference

    def inferences_for_study(self, study_id: str) -> list[AIInference]:
        items = [i for i in self.inferences.values() if i.study_id == study_id]
        return sorted(items, key=lambda i: (i.created_at, i.id))

    def latest_inference(self, study_id: str) -> AIInference | None:
        items = self.inferences_for_study(study_id)
        return items[-1] if items else None

    def list_inferences(self) -> list[AIInference]:
        return list(self.inferences.values())

    # --- Decisions ---

    def add_decision(self, decision: Decision) -> Decision:
        if self.decision_for_study(decision.study_id) is not None:
            raise ValueError(f"study {decision.study_id} already has a decision")
        self.decisions[decision.id] = decision
        return decision

    def get_decision(self, decision_id: str) -> Decision | None:
        return self.decisions.get(decision_id)

    def decision_for_study(self, study_id: str) -> Decision | None:
        return next((d for d in self.decisions.values() if d.study_id == study_id), None)

    def list_decisions(self) -> list[Decision]:
        return sorted(self.decisions.values(), key=lambda d: d.created_at, reverse=True)

    # --- Notifications ---

    def add_notification(self, notification: Notification) -> Notification:
        self.notifications[notification.id] = notification
        return notification

    def get_notification(self, notification_id: str) -> Notification | None:
        return self.notifications.get(notification_id)

    def notification_for_decision(self, decision_id: str) -> Notification | None:
        return next((n for n in self.notifications.values() if n.decision_id == decision_id), None)

    def notifications_for_patient(self, patient_id: str) -> list[Notification]:
        items = [n for n in self.notifications.values() if n.patient_id == patient_id]
        return sorted(items, key=lambda n: n.sent_at, reverse=True)

    def list_notifications(self) -> list[Notification]:
        return list(self.notifications.values())

    # --- Appointments ---

    def add_appointment(self, appointment: Appointment) -> Appointment:
        self.appointments[appointment.id] = appointment
        return appointment

    def get_appointment(self, appointment_id: str) -> Appointment | None:
        return self.appointments.get(appointment_id)

    def list_appointments(
        self,
        *,
        patient_id: str | None = None,
        doctor_id: str | None = None,
        status: AppointmentStatus | None = None,
        notification_id: str | None = None,
        research_type: str | None = None,
    ) -> list[Appointment]:
        result = [
            a
            for a in self.appointments.values()
            if (patient_id is None or a.patient_id == patient_id)
            and (doctor_id is None or a.doctor_id == doctor_id)
            and (status is None or a.status is status)
            and (notification_id is None or a.notification_id == notification_id)
            and (research_type is None or a.research_type == research_type)
        ]
        return sorted(result, key=lambda a: a.scheduled_for)

    def busy_slots(
        self, *, doctor_id: str | None = None, research_type: str | None = None
    ) -> set[datetime]:
        """Занятое время врача или кабинета исследования."""
        assert (doctor_id is None) != (research_type is None)
        return {
            a.scheduled_for
            for a in self.list_appointments(
                doctor_id=doctor_id,
                research_type=research_type,
                status=AppointmentStatus.SCHEDULED,
            )
            if doctor_id is not None or a.doctor_id is None
        }

    # --- Audit ---

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        self.audit.append(event)
        return event

    def audit_for_target(self, target_type: str, target_id: str) -> list[AuditEvent]:
        return [e for e in self.audit if e.target_type == target_type and e.target_id == target_id]

    def recent_audit(self, limit: int = 100) -> list[AuditEvent]:
        return sorted(self.audit, key=lambda e: e.at, reverse=True)[:limit]
