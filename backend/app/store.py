"""In-memory хранилище (хакатон: без БД, данные живут до перезапуска).

Store только хранит и выбирает данные: никаких прав и бизнес-правил —
это забота сервисов и domain/rules.py. get_* возвращают None, если объекта нет.

Объекты добавляются только через add_*: там же пополняются индексы по полям-связям
(study_id, decision_id, patient_id, …), которые после создания не меняются. Без индексов
очередь врача и дашборд проходили по всем записям на каждое исследование — под нагрузкой
это было главным узким местом (scripts/loadtest.py, docs/load-testing.md).
"""

from __future__ import annotations

from collections import Counter, defaultdict
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
        # Индексы (см. докстринг модуля)
        self._patient_by_user: dict[str, Patient] = {}
        self._inferences_by_study: defaultdict[str, list[AIInference]] = defaultdict(list)
        self._decision_by_study: dict[str, Decision] = {}
        self._notification_by_decision: dict[str, Notification] = {}
        self._notifications_by_patient: defaultdict[str, list[Notification]] = defaultdict(list)
        self._appointments_by: dict[str, defaultdict[str, list[Appointment]]] = {
            key: defaultdict(list)
            for key in ("patient_id", "doctor_id", "notification_id", "research_type")
        }
        self._audit_by_target: defaultdict[tuple[str, str], list[AuditEvent]] = defaultdict(list)
        self._audit_actions: Counter[str] = Counter()

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
        self._patient_by_user[patient.user_id] = patient
        return patient

    def get_patient(self, patient_id: str) -> Patient | None:
        return self.patients.get(patient_id)

    def list_patients(self) -> list[Patient]:
        return sorted(self.patients.values(), key=lambda p: p.full_name)

    def patient_by_user(self, user_id: str) -> Patient | None:
        return self._patient_by_user.get(user_id)

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
        self._inferences_by_study[inference.study_id].append(inference)
        return inference

    def inferences_for_study(self, study_id: str) -> list[AIInference]:
        items = self._inferences_by_study.get(study_id, [])
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
        self._decision_by_study[decision.study_id] = decision
        return decision

    def get_decision(self, decision_id: str) -> Decision | None:
        return self.decisions.get(decision_id)

    def decision_for_study(self, study_id: str) -> Decision | None:
        return self._decision_by_study.get(study_id)

    def list_decisions(self) -> list[Decision]:
        return sorted(self.decisions.values(), key=lambda d: d.created_at, reverse=True)

    # --- Notifications ---

    def add_notification(self, notification: Notification) -> Notification:
        self.notifications[notification.id] = notification
        self._notification_by_decision[notification.decision_id] = notification
        self._notifications_by_patient[notification.patient_id].append(notification)
        return notification

    def get_notification(self, notification_id: str) -> Notification | None:
        return self.notifications.get(notification_id)

    def notification_for_decision(self, decision_id: str) -> Notification | None:
        return self._notification_by_decision.get(decision_id)

    def notifications_for_patient(self, patient_id: str) -> list[Notification]:
        items = self._notifications_by_patient.get(patient_id, [])
        return sorted(items, key=lambda n: n.sent_at, reverse=True)

    def list_notifications(self) -> list[Notification]:
        return list(self.notifications.values())

    # --- Appointments ---

    def add_appointment(self, appointment: Appointment) -> Appointment:
        self.appointments[appointment.id] = appointment
        for key, index in self._appointments_by.items():
            value = getattr(appointment, key)
            if value is not None:
                index[value].append(appointment)
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
        # Кандидаты — из самого узкого индекса по заданным фильтрам, дальше — обычная проверка
        keys = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "notification_id": notification_id,
            "research_type": research_type,
        }
        pools = [self._appointments_by[k].get(v, []) for k, v in keys.items() if v is not None]
        candidates = min(pools, key=len) if pools else self.appointments.values()
        result = [
            a
            for a in candidates
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
        self._audit_by_target[(event.target_type, event.target_id)].append(event)
        self._audit_actions[event.action] += 1
        return event

    def audit_for_target(self, target_type: str, target_id: str) -> list[AuditEvent]:
        return list(self._audit_by_target.get((target_type, target_id), []))

    def audit_count(self, action: str) -> int:
        return self._audit_actions[action]

    def recent_audit(self, limit: int = 100) -> list[AuditEvent]:
        return sorted(self.audit, key=lambda e: e.at, reverse=True)[:limit]
