from collections import Counter
from datetime import UTC, datetime

import pytest

from app.core.security import verify_password
from app.domain import rules
from app.domain.enums import AppointmentStatus, Role, StudyStatus
from app.seed import DEMO_PASSWORD, seed_demo
from app.store import Store

S = StudyStatus
NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)  # суббота — проверяем перенос слотов


@pytest.fixture(scope="module")
def store() -> Store:
    s = Store()
    seed_demo(s, now=NOW)
    return s


def test_counts(store):
    roles = Counter(u.role for u in store.users.values())
    assert roles[Role.CHIEF] == 1
    assert roles[Role.MANAGER] == 1
    assert roles[Role.DOCTOR] == 7
    assert roles[Role.PATIENT] == 10
    assert len(store.studies) == 15
    # Ответов AI в seed нет: всё, что без решения, ждёт автоанализа
    assert Counter(s.status for s in store.studies.values()) == {
        S.NEW: 9,
        S.NOTIFIED: 5,  # уведомление уходит сразу после решения
        S.COMPLETED: 1,
    }


def test_demo_password_works(store):
    user = store.user_by_email("PETROV@clinic.demo")
    assert user is not None
    assert verify_password(DEMO_PASSWORD, user.password_hash)


def test_every_patient_has_login(store):
    for p in store.patients.values():
        user = store.get_user(p.user_id)
        assert user is not None and user.role is Role.PATIENT


def test_status_consistency(store):
    assert not store.inferences  # никаких «готовых» ответов AI
    for study in store.studies.values():
        decision = store.decision_for_study(study.id)
        notification = store.notification_for_decision(decision.id) if decision else None

        assert (decision is None) == (study.status is S.NEW)
        assert (notification is None) == (study.status not in {S.NOTIFIED, S.COMPLETED})
        if notification:
            # Завершено ⇔ записи есть по всем направлениям решения
            appointments = store.list_appointments(notification_id=notification.id)
            assert (study.status is S.COMPLETED) == rules.all_covered(decision, appointments)


def test_seed_decisions_are_without_ai(store):
    for d in store.decisions.values():
        assert d.ai_inference_id is None and d.accepted_ai is None
        assert d.chosen_types
    assert any(len(d.chosen_types) > 1 for d in store.decisions.values())  # есть комбинированные


def test_appointments_are_bookable_slots_without_conflicts(store):
    from zoneinfo import ZoneInfo

    from app.domain.schedule import is_work_slot

    tz = ZoneInfo("Europe/Moscow")
    seen = set()
    for a in store.list_appointments(status=AppointmentStatus.SCHEDULED):
        assert a.scheduled_for > NOW
        assert is_work_slot(a.scheduled_for, tz)
        resource = a.doctor_id or a.research_type
        assert (resource, a.scheduled_for) not in seen
        seen.add((resource, a.scheduled_for))


def test_live_demo_patient_has_unanswered_notification(store):
    user = store.user_by_email("kuznetsova@patient.demo")
    patient = store.patient_by_user(user.id)
    [notification] = store.notifications_for_patient(patient.id)
    assert notification.patient_action is None
    decision = store.get_decision(notification.decision_id)
    for req in rules.required_bookings(decision):
        if req.kind == "specialist":
            assert store.list_doctors(req.code)  # есть к кому записаться


def test_every_study_has_audit_trail(store):
    for study in store.studies.values():
        actions = [e.action for e in store.audit_for_target("study", study.id)]
        assert actions[0] == "study.created"
