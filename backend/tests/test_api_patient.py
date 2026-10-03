"""Сценарий: врач решает и уведомляет → пациент читает и записывается → дашборд."""

from tests.conftest import analyze_all, login

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
    # Петров назначил и контрольный приём, и консультацию пульмонолога
    assert item["recommendations"] == ["repeat_appointment", "specialist_consult"]
    assert item["suggested_specialties"] == ["pulmonologist"]
    assert item["only_treating_doctor"] is False
    names = [d["full_name"] for d in item["suggested_doctors"]]
    assert names[0].startswith("Петров") and any(n.startswith("Сидорова") for n in names[1:])
    assert "report_text" not in item["study"]  # заключение пациенту не показываем

    nid = item["notification"]["id"]
    read = client.post(f"{API}/notifications/{nid}/read", headers=kuznetsova).json()
    assert read["notification"]["status"] == "read"

    def book(doctor_id, nth=0):
        days = client.get(f"{API}/doctors/{doctor_id}/slots", headers=kuznetsova).json()
        slot = days[0]["slots"][nth]
        return client.post(
            f"{API}/appointments",
            headers=kuznetsova,
            json={"doctor_id": doctor_id, "scheduled_for": slot, "notification_id": nid},
        )

    sidorova_id = next(
        d["id"] for d in item["suggested_doctors"] if d["specialty"] == "pulmonologist"
    )
    r = book(sidorova_id)
    assert r.status_code == 200, r.text
    first = r.json()
    assert book(sidorova_id).status_code == 409  # к тому же врачу второй раз нельзя

    # по тому же уведомлению — ещё и контрольный приём у лечащего врача
    petrov_id = item["treating_doctor"]["id"]
    r = book(petrov_id, nth=1)  # другое время — две записи на одно время нельзя
    assert r.status_code == 200, r.text
    second = r.json()

    view = _my_notification(client, kuznetsova)
    assert {a["id"] for a in view["appointments"]} == {first["id"], second["id"]}

    # отказаться после записи нельзя
    assert client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova).status_code == 409

    # Study завершено после первой записи, все записи видны в карточке
    study_id = item["study"]["id"]
    card = client.get(f"{API}/studies/{study_id}", headers=petrov).json()
    assert card["status"] == "completed"
    assert {a["id"] for a in card["appointments"]} == {first["id"], second["id"]}
    actions = [
        e["action"] for e in client.get(f"{API}/studies/{study_id}/audit", headers=petrov).json()
    ]
    assert actions[-3:] == ["notification.read", "patient.booked", "patient.booked"]

    # запись видна у врача-консультанта
    sidorova = login(client, "sidorova@clinic.demo")
    mine = client.get(f"{API}/appointments", headers=sidorova).json()
    assert first["id"] in {a["id"] for a in mine}


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


def test_rebook_by_notification_after_cancel(client, kuznetsova):
    item = _my_notification(client, kuznetsova)
    nid = item["notification"]["id"]
    doctor = item["suggested_doctors"][0]
    days = client.get(f"{API}/doctors/{doctor['id']}/slots", headers=kuznetsova).json()
    first, second = days[0]["slots"][:2]

    def book(slot):
        return client.post(
            f"{API}/appointments",
            headers=kuznetsova,
            json={"doctor_id": doctor["id"], "scheduled_for": slot, "notification_id": nid},
        )

    aid = book(first).json()["id"]
    assert book(second).status_code == 409  # запись активна — второй раз нельзя
    client.patch(f"{API}/appointments/{aid}", headers=kuznetsova, json={"status": "cancelled"})
    r = book(second)
    assert r.status_code == 200, r.text
    view = _my_notification(client, kuznetsova)
    assert view["notification"]["appointment_id"] == r.json()["id"]


def test_doctor_cannot_book_and_patient_cannot_notify(client, petrov, kuznetsova):
    doctors = client.get(f"{API}/doctors", headers=petrov).json()
    slot = _first_free_slot(client, petrov, doctors[0]["id"])
    r = client.post(
        f"{API}/appointments",
        headers=petrov,
        json={"doctor_id": doctors[0]["id"], "scheduled_for": slot},
    )
    assert r.status_code == 403


def test_doctors_filter(client, petrov):
    items = client.get(
        f"{API}/doctors", params={"specialty": "neurosurgeon"}, headers=petrov
    ).json()
    assert [d["full_name"] for d in items] == ["Захаров Игорь Валентинович"]


# --- Уведомление после решения ---


def test_decision_notifies_all_contacts(client, sidorova):
    # Волков: телефон и email, соцсети нет → SMS + email
    study = next(
        s
        for s in client.get(f"{API}/studies", params={"status": "new"}, headers=sidorova).json()
        if s["patient"]["full_name"].startswith("Волков")
    )
    sid = study["id"]
    client.post(f"{API}/studies/{sid}/analyze", headers=sidorova)
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={"chosen_type": "specialist_consult", "details": {"specialist": "oncologist"}},
    )
    assert r.status_code == 200, r.text
    card = client.get(f"{API}/studies/{sid}", headers=sidorova).json()
    assert card["status"] == "notified"
    assert card["notification"]["channels"] == ["sms", "email"]
    assert "Онколог" in card["notification"]["text"]


def test_seed_notification_uses_social_when_present(client, kuznetsova):
    item = _my_notification(client, kuznetsova)  # у Кузнецовой указан Telegram
    assert item["notification"]["channels"] == ["sms", "email", "social"]


def test_manual_notify_endpoint_removed(client, petrov):
    assert client.post(f"{API}/decisions/dc_x/notify", headers=petrov).status_code in (404, 405)


def test_repeat_appointment_only_with_treating_doctor(client, petrov):
    item = client.get(f"{API}/studies", params={"status": "new"}, headers=petrov).json()[0]
    sid = item["id"]
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=petrov,
        json={"chosen_types": ["repeat_appointment"], "details": {"interval_days": 30}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["details"] == {}  # дату выбирает пациент, interval_days отброшен
    n = client.get(f"{API}/studies/{sid}", headers=petrov).json()["notification"]
    assert "через" not in n["text"]

    accounts = client.get(f"{API}/auth/demo-users").json()
    email = next(a["email"] for a in accounts if a["full_name"] == item["patient"]["full_name"])
    patient = login(client, email)
    view = next(
        x
        for x in client.get(f"{API}/patients/me/notifications", headers=patient).json()
        if x["notification"]["id"] == n["id"]
    )
    assert view["only_treating_doctor"] is True
    assert [d["id"] for d in view["suggested_doctors"]] == [item["doctor"]["id"]]

    doctors = client.get(f"{API}/doctors", headers=patient).json()
    other = next(d for d in doctors if d["id"] != item["doctor"]["id"])
    slot = _first_free_slot(client, patient, other["id"])
    r = client.post(
        f"{API}/appointments",
        headers=patient,
        json={"doctor_id": other["id"], "scheduled_for": slot, "notification_id": n["id"]},
    )
    assert r.status_code == 422

    slot = _first_free_slot(client, patient, item["doctor"]["id"])
    r = client.post(
        f"{API}/appointments",
        headers=patient,
        json={"doctor_id": item["doctor"]["id"], "scheduled_for": slot, "notification_id": n["id"]},
    )
    assert r.status_code == 200, r.text


def test_details_match_with_ai(client, petrov):
    analyze_all(client)
    study = next(
        s
        for s in client.get(f"{API}/studies", params={"status": "ai_ready"}, headers=petrov).json()
        if s["ai"]["recommendation"] == "specialist_consult"
    )
    card = client.get(f"{API}/studies/{study['id']}", headers=petrov).json()
    ai_specialists = card["ai"]["details"]["specialists"]
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=petrov,
        json={
            "chosen_types": ["specialist_consult"],
            "details": {"specialists": ai_specialists},
        },
    )
    d = r.json()
    assert d["accepted_ai"] is True and d["details_match"] is True
    assert d["ai_details"] == {"specialists": ai_specialists}


def test_additional_research_validation(client, sidorova):
    sid = client.get(f"{API}/studies", params={"status": "new"}, headers=sidorova).json()[0]["id"]

    def decide(details):
        return client.post(
            f"{API}/studies/{sid}/decision",
            headers=sidorova,
            json={"chosen_types": ["additional_research"], "details": details},
        )

    assert decide({"research_types": []}).status_code == 422
    assert decide({"research_types": ["ct", "voodoo"]}).status_code == 422
    r = decide({"research_types": ["ct", "lab_tests", "ct"]})
    assert r.status_code == 200, r.text
    assert r.json()["details"] == {"research_types": ["ct", "lab_tests"]}


# --- Метрики ---


def test_dashboard_from_seed(client, head):
    d = client.get(f"{API}/metrics/dashboard", headers=head).json()
    # В seed нет ответов AI — согласия пока не с чем считать
    assert d["agreement"] == {"agreed": 0, "total": 0, "rate": None}
    assert d["details_agreement"]["total"] == 0
    assert sum(map(sum, d["confusion_matrix"]["matrix"])) == 0
    assert d["summary"]["studies_total"] == 15
    assert d["summary"]["decisions_total"] == 6
    assert d["summary"]["decisions_without_ai"] == 6
    assert d["latency"]["count"] == 0
    assert len(d["recent_decisions"]) == 6
    consult = next(r for r in d["notifications"] if r["recommendation"] == "specialist_consult")
    assert consult["sent"] == 4 and consult["booked"] == 1


def test_dashboard_updates_after_ai_and_decision(client, head, petrov):
    analyze_all(client)
    d = client.get(f"{API}/metrics/dashboard", headers=head).json()
    assert d["latency"]["count"] == 9  # 9 исследований без решения проанализированы

    item = client.get(f"{API}/studies", params={"status": "ai_ready"}, headers=petrov).json()[0]
    rec = item["ai"]["recommendation"]
    other = next(t for t in ("repeat_appointment", "specialist_consult") if t != rec)
    details = {} if other == "repeat_appointment" else {"specialists": ["oncologist"]}
    r = client.post(
        f"{API}/studies/{item['id']}/decision",
        headers=petrov,
        json={"chosen_types": [other], "details": details},
    )
    assert r.status_code == 200
    d = client.get(f"{API}/metrics/dashboard", headers=head).json()
    assert d["agreement"] == {"agreed": 0, "total": 1, "rate": 0.0}
    assert sum(map(sum, d["confusion_matrix"]["matrix"])) == 1


def test_dashboard_head_only(client, petrov):
    assert client.get(f"{API}/metrics/dashboard", headers=petrov).status_code == 403
