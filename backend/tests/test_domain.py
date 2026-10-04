from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.security import hash_password, verify_password
from app.domain import rules, schedule
from app.domain.enums import RecommendationType as R
from app.domain.enums import Role, Sex, StudyStatus, StudyType
from app.domain.models import Patient, Study, User

S = StudyStatus
TZ = ZoneInfo("Europe/Moscow")


def _user(role: Role, uid: str = "usr_1") -> User:
    return User(id=uid, role=role, email=f"{uid}@x", password_hash="", full_name=uid)


def _study(status: StudyStatus = S.AI_READY, doctor_id: str = "usr_1") -> Study:
    now = datetime.now(UTC)
    return Study(
        id="st_1",
        patient_id="pat_1",
        treating_doctor_id=doctor_id,
        study_type=StudyType.CT,
        body_region="chest",
        status=status,
        performed_at=now,
        created_at=now,
    )


# --- Переходы ---


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (S.NEW, S.AI_READY),
        (S.NEW, S.AI_FAILED),
        (S.AI_READY, S.AI_READY),  # повторный анализ
        (S.AI_FAILED, S.AI_READY),
        (S.AI_READY, S.DECIDED),
        (S.AI_FAILED, S.DECIDED),  # решение без AI
        (S.NEW, S.DECIDED),  # врач может не ждать AI
        (S.DECIDED, S.NOTIFIED),
        (S.NOTIFIED, S.COMPLETED),
    ],
)
def test_allowed_transitions(src, dst):
    assert rules.can_transition(src, dst)


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (S.DECIDED, S.AI_READY),  # после решения анализ не перезапускается
        (S.DECIDED, S.COMPLETED),
        (S.COMPLETED, S.NEW),
    ],
)
def test_forbidden_transitions(src, dst):
    assert not rules.can_transition(src, dst)


def test_every_status_has_transition_entry():
    assert set(rules.TRANSITIONS) == set(StudyStatus)


# --- Права ---


def test_treating_doctor_can_decide_others_cannot():
    study = _study(doctor_id="usr_1")
    assert rules.can_decide(_user(Role.DOCTOR, "usr_1"), study)
    assert not rules.can_decide(_user(Role.DOCTOR, "usr_2"), study)
    assert rules.can_decide(_user(Role.CHIEF, "usr_9"), study)
    assert not rules.can_decide(_user(Role.MANAGER, "usr_1"), study)


def test_chief_can_analyze_but_patient_cannot_view():
    study = _study()
    assert rules.can_analyze(_user(Role.CHIEF, "usr_9"), study)
    assert not rules.can_analyze(_user(Role.DOCTOR, "usr_2"), study)
    assert not rules.can_view_study(_user(Role.PATIENT, "usr_3"), study)


def test_can_act_flag():
    doctor, other = _user(Role.DOCTOR, "usr_1"), _user(Role.DOCTOR, "usr_2")
    assert rules.can_act(doctor, _study(S.DECIDED))
    assert not rules.can_act(doctor, _study(S.COMPLETED))
    assert not rules.can_act(other, _study(S.AI_READY))
    chief = _user(Role.CHIEF, "usr_9")
    assert rules.can_act(chief, _study(S.NEW))
    assert not rules.can_act(chief, _study(S.COMPLETED))
    assert not rules.can_act(_user(Role.MANAGER, "usr_8"), _study(S.NEW))


def test_accepted_ai():
    consult = (R.SPECIALIST_CONSULT,)
    assert rules.compute_accepted_ai(consult, R.SPECIALIST_CONSULT) is True
    assert rules.compute_accepted_ai(consult, R.REPEAT_APPOINTMENT) is False
    assert rules.compute_accepted_ai(consult, None) is None
    # принял вариант AI и дополнил своим — согласие
    both = (R.REPEAT_APPOINTMENT, R.SPECIALIST_CONSULT)
    assert rules.compute_accepted_ai(both, R.SPECIALIST_CONSULT) is True


def test_details_match_compares_ai_option_only():
    chosen = (R.SPECIALIST_CONSULT, R.ADDITIONAL_RESEARCH)
    details = {"specialists": ["oncologist", "urologist"], "research_types": ["ct"]}
    ai = {"specialists": ["urologist", "oncologist"]}
    assert rules.compute_details_match(chosen, details, R.SPECIALIST_CONSULT, ai) is True
    ai = {"specialists": ["oncologist"]}
    assert rules.compute_details_match(chosen, details, R.SPECIALIST_CONSULT, ai) is False
    assert rules.compute_details_match(chosen, details, R.REPEAT_APPOINTMENT, {}) is None


def test_patient_age():
    p = Patient(
        id="p", user_id="u", full_name="", birth_date=date(1968, 3, 14), sex=Sex.M, phone=""
    )
    assert p.age_on(date(2026, 3, 13)) == 57
    assert p.age_on(date(2026, 3, 14)) == 58


# --- Слоты ---

MONDAY = date(2026, 10, 5)


def test_day_slots_workday_and_weekend():
    slots = schedule.day_slots(MONDAY, TZ)
    assert len(slots) == 16  # 09:00–16:30 шагом 30 мин
    assert slots[0].astimezone(TZ).hour == 9
    assert slots[-1].astimezone(TZ).strftime("%H:%M") == "16:30"
    assert all(s.tzinfo is UTC for s in slots)
    assert schedule.day_slots(date(2026, 10, 4), TZ) == []  # воскресенье


def test_free_slots_exclude_busy_past_and_far_future():
    now = datetime(2026, 10, 5, 9, 10, tzinfo=TZ).astimezone(UTC)
    slots = schedule.day_slots(MONDAY, TZ)
    busy = {slots[4]}
    free = schedule.free_slots(MONDAY, TZ, now, busy)
    assert slots[4] not in free
    assert min(free) >= now + timedelta(hours=1)  # 09:00, 09:30, 10:00 недоступны
    assert free[0].astimezone(TZ).strftime("%H:%M") == "10:30"
    assert schedule.free_slots(MONDAY + timedelta(days=21), TZ, now, set()) == []


def test_is_bookable_rejects_unaligned_time():
    now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    good = datetime(2026, 10, 5, 10, 0, tzinfo=TZ)
    assert schedule.is_bookable(good, now, TZ)
    assert not schedule.is_bookable(good + timedelta(minutes=10), now, TZ)
    assert not schedule.is_bookable(datetime(2026, 10, 5, 18, 0, tzinfo=TZ), now, TZ)


# --- Пароли ---


def test_password_hash_roundtrip():
    h = hash_password("demo", rounds=4)
    assert verify_password("demo", h)
    assert not verify_password("wrong", h)
    assert not verify_password("demo", "not-a-hash")
    assert not verify_password("x" * 100, h)
