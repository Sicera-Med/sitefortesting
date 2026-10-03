"""Сценарий: врач решает и уведомляет → пациент читает и записывается → дашборд."""

from tests.conftest import login

API = "/api/v1"


def _first_free_slot(client, headers, doctor_id):
    days = client.get(f"{API}/doctors/{doctor_id}/slots", headers=headers).json()
    assert days, "у врача нет свободных слотов"
    return days[0]["slots"][0]


def _my_notification(client, headers):
    items = client.get(f"{API}/patients/me/notifications", headers=headers).json()
    assert len(items) == 1
    return items[0]


# --- Уведомление пациента из seed (живой демо-сценарий) ---


def test_patient_books_from_notification(client, kuznetsova, petrov):
    item = _my_notification(client, kuznetsova)
    assert item["notification"]["patient_action"] is None
    assert item["recommendation"] == "specialist_consult"
    assert item["suggested_specialty"] == "pulmonologist"
    doctor = item["suggested_doctors"][0]
    assert doctor["full_name"].startswith("Сидорова")
    assert "report_text" not in item["study"]  # заключение пациенту не показываем

    nid = item["notification"]["id"]
    read = client.post(f"{API}/notifications/{nid}/read", headers=kuznetsova).json()
    assert read["notification"]["status"] == "read"

    slot = _first_free_slot(client, kuznetsova, doctor["id"])
    r = client.post(
        f"{API}/appointments",
        headers=kuznetsova,
        json={"doctor_id": doctor["id"], "scheduled_for": slot, "notification_id": nid},
    )
    assert r.status_code == 200, r.text
    appointment = r.json()
    assert appointment["doctor"]["id"] == doctor["id"]

    # слот исчез из свободных
    days = client.get(f"{API}/doctors/{doctor['id']}/slots", headers=kuznetsova).json()
    assert all(slot not in d["slots"] for d in days)

    # повторно ответить на уведомление нельзя
    assert client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova).status_code == 409

    # Study лечащего врача завершено, запись видна в карточке
    study_id = item["study"]["id"]
    card = client.get(f"{API}/studies/{study_id}", headers=petrov).json()
    assert card["status"] == "completed"
    assert card["appointment"]["id"] == appointment["id"]
    actions = [
        e["action"] for e in client.get(f"{API}/studies/{study_id}/audit", headers=petrov).json()
    ]
    assert actions[-2:] == ["notification.read", "patient.booked"]

    # запись видна у врача-консультанта
    sidorova = login(client, "sidorova@clinic.demo")
    mine = client.get(f"{API}/appointments", headers=sidorova).json()
    assert appointment["id"] in {a["id"] for a in mine}


def test_patient_declines(client, kuznetsova):
    nid = _my_notification(client, kuznetsova)["notification"]["id"]
    r = client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova)
    assert r.status_code == 200
    assert r.json()["notification"]["patient_action"] == "declined"


def test_slot_conflicts_and_validation(client, kuznetsova):
    doctor = _my_notification(client, kuznetsova)["suggested_doctors"][0]
    slot = _first_free_slot(client, kuznetsova, doctor["id"])
    body = {"doctor_id": doctor["id"], "scheduled_for": slot}
    assert client.post(f"{API}/appointments", headers=kuznetsova, json=body).status_code == 200

    # тот же слот другим пациентом — занято
    other = login(client, "ivanov@patient.demo")
    r = client.post(f"{API}/appointments", headers=other, json=body)
    assert r.status_code == 409

    # невыровненное время и время без пояса
    r = client.post(
        f"{API}/appointments",
        headers=other,
        json={**body, "scheduled_for": slot.replace(":00", ":07", 1)},
    )
    assert r.status_code in (409, 422)
    r = client.post(
        f"{API}/appointments", headers=other, json={**body, "scheduled_for": "2030-01-01T10:00:00"}
    )
    assert r.status_code == 422


def test_foreign_notification_is_hidden(client, kuznetsova):
    nid = _my_notification(client, kuznetsova)["notification"]["id"]
    other = login(client, "ivanov@patient.demo")
    assert client.post(f"{API}/notifications/{nid}/read", headers=other).status_code == 404


def test_cancel_appointment(client, kuznetsova):
    appointments = client.get(f"{API}/appointments", headers=kuznetsova).json()
    doctor = _my_notification(client, kuznetsova)["suggested_doctors"][0]
    slot = _first_free_slot(client, kuznetsova, doctor["id"])
    created = client.post(
        f"{API}/appointments",
        headers=kuznetsova,
        json={"doctor_id": doctor["id"], "scheduled_for": slot},
    ).json()
    assert (
        len(client.get(f"{API}/appointments", headers=kuznetsova).json()) == len(appointments) + 1
    )

    r = client.patch(
        f"{API}/appointments/{created['id']}", headers=kuznetsova, json={"status": "cancelled"}
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    other = login(client, "ivanov@patient.demo")
    r = client.patch(
        f"{API}/appointments/{created['id']}", headers=other, json={"status": "cancelled"}
    )
    assert r.status_code == 403


def test_doctor_cannot_book_and_patient_cannot_notify(client, petrov, kuznetsova):
    doctors = client.get(f"{API}/doctors", headers=petrov).json()
    slot = _first_free_slot(client, petrov, doctors[0]["id"])
    r = client.post(
        f"{API}/appointments",
        headers=petrov,
        json={"doctor_id": doctors[0]["id"], "scheduled_for": slot},
    )
    assert r.status_code == 403
    assert client.post(f"{API}/decisions/dc_x/notify", headers=kuznetsova).status_code == 403


def test_doctors_filter(client, petrov):
    items = client.get(
        f"{API}/doctors", params={"specialty": "neurosurgeon"}, headers=petrov
    ).json()
    assert [d["full_name"] for d in items] == ["Захаров Игорь Валентинович"]


# --- Уведомление от врача ---


def test_doctor_notifies_after_decision(client, sidorova):
    decided = client.get(f"{API}/studies", params={"status": "decided"}, headers=sidorova).json()
    study = client.get(f"{API}/studies/{decided[0]['id']}", headers=sidorova).json()
    did = study["decision"]["id"]

    r = client.post(f"{API}/decisions/{did}/notify", headers=sidorova, json={"channel": "email"})
    assert r.status_code == 200, r.text
    assert r.json()["channel"] == "email"
    assert "Здравствуйте" in r.json()["text"]
    assert (
        client.get(f"{API}/studies/{study['id']}", headers=sidorova).json()["status"] == "notified"
    )
    assert client.post(f"{API}/decisions/{did}/notify", headers=sidorova).status_code == 409


def test_other_doctor_cannot_notify(client, sidorova, petrov):
    decided = client.get(f"{API}/studies", params={"status": "decided"}, headers=sidorova).json()
    did = client.get(f"{API}/studies/{decided[0]['id']}", headers=sidorova).json()["decision"]["id"]
    assert client.post(f"{API}/decisions/{did}/notify", headers=petrov).status_code == 403


# --- Метрики ---


def test_dashboard_from_seed(client, head):
    d = client.get(f"{API}/metrics/dashboard", headers=head).json()
    assert d["agreement"] == {"agreed": 4, "total": 6, "rate": 0.6667}
    assert d["agreement_by_confidence"]["high"]["rate"] == 1.0
    assert d["agreement_by_confidence"]["low"]["rate"] == 0.0
    assert sum(map(sum, d["confusion_matrix"]["matrix"])) == 6
    assert d["summary"]["studies_total"] == 15
    assert d["summary"]["ai_failures"] == 1
    assert d["latency"]["count"] == 9 and d["latency"]["p95_ms"] >= d["latency"]["avg_ms"]
    assert len(d["recent_decisions"]) == 6
    consult = next(r for r in d["notifications"] if r["recommendation"] == "specialist_consult")
    assert consult["sent"] == 3 and consult["booked"] == 1


def test_dashboard_updates_after_decision(client, head, petrov):
    item = client.get(f"{API}/studies", params={"status": "ai_ready"}, headers=petrov).json()[0]
    rec = item["ai"]["recommendation"]
    other = next(t for t in ("repeat_appointment", "specialist_consult") if t != rec)
    details = (
        {"interval_days": 14} if other == "repeat_appointment" else {"specialist": "oncologist"}
    )
    r = client.post(
        f"{API}/studies/{item['id']}/decision",
        headers=petrov,
        json={"chosen_type": other, "details": details},
    )
    assert r.status_code == 200
    d = client.get(f"{API}/metrics/dashboard", headers=head).json()
    assert d["agreement"]["total"] == 7 and d["agreement"]["agreed"] == 4


def test_dashboard_head_only(client, petrov):
    assert client.get(f"{API}/metrics/dashboard", headers=petrov).status_code == 403
