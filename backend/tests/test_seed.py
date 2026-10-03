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
    assert roles[Role.HEAD] == 1
    assert roles[Role.DOCTOR] == 7
    assert roles[Role.PATIENT] == 10
    assert len(store.studies) == 15
    assert Counter(s.status for s in store.studies.values()) == {
        S.NEW: 5,
        S.AI_READY: 3,
        S.AI_FAILED: 1,
        S.DECIDED: 3,
        S.NOTIFIED: 2,
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
    for study in store.studies.values():
        inference = store.latest_inference(study.id)
        decision = store.decision_for_study(study.id)
        notification = store.notification_for_decision(decision.id) if decision else None

        assert (inference is None) == (study.status in {S.NEW, S.AI_FAILED})
        assert (decision is None) == (study.status in {S.NEW, S.AI_READY, S.AI_FAILED})
        assert (notification is None) == (study.status not in {S.NOTIFIED, S.COMPLETED})
        if study.status is S.COMPLETED:
            assert notification.patient_action is not None
        if study.status is S.NOTIFIED:
            assert notification.patient_action is None


def test_decision_snapshot_and_accepted_ai(store):
    for d in store.decisions.values():
        latest = store.latest_inference(d.study_id)
        assert d.ai_inference_id == latest.id
        assert d.ai_recommendation == latest.recommendation
        assert d.accepted_ai == rules.compute_accepted_ai(d.chosen_type, d.ai_recommendation)


def test_dashboard_story(store):
    """4 из 6 решений совпадают с AI; все расхождения — при confidence < 0.7."""
    decisions = list(store.decisions.values())
    assert sum(d.accepted_ai for d in decisions) == 4
    assert all(d.accepted_ai for d in decisions if d.ai_confidence >= 0.7)
    assert not any(d.accepted_ai for d in decisions if d.ai_confidence < 0.7)


def test_ranked_options_valid(store):
    for inf in store.inferences.values():
        scores = [o.score for o in inf.ranked_options]
        assert len({o.type for o in inf.ranked_options}) == 3
        assert scores == sorted(scores, reverse=True)
        assert inf.ranked_options[0].type == inf.recommendation
        assert abs(sum(scores) - 1) < 0.02


def test_appointments_are_bookable_slots_without_conflicts(store):
    from zoneinfo import ZoneInfo

    from app.domain.schedule import is_work_slot

    tz = ZoneInfo("Europe/Moscow")
    seen = set()
    for a in store.list_appointments(status=AppointmentStatus.SCHEDULED):
        assert a.scheduled_for > NOW
        assert is_work_slot(a.scheduled_for, tz)
        assert (a.doctor_id, a.scheduled_for) not in seen
        seen.add((a.doctor_id, a.scheduled_for))


def test_live_demo_patient_has_unanswered_notification(store):
    user = store.user_by_email("kuznetsova@patient.demo")
    patient = store.patient_by_user(user.id)
    [notification] = store.notifications_for_patient(patient.id)
    assert notification.patient_action is None
    decision = store.get_decision(notification.decision_id)
    specialty = rules.suggested_specialty(decision)
    assert store.list_doctors(specialty)  # есть к кому записаться


def test_every_study_has_audit_trail(store):
    for study in store.studies.values():
        actions = [e.action for e in store.audit_for_target("study", study.id)]
        assert actions[0] == "study.created"
