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
    # Петров назначил и контрольный приём, и консультацию пульмонолога — два направления
    assert item["recommendations"] == ["repeat_appointment", "specialist_consult"]
    keys = [r["key"] for r in item["requirements"]]
    assert keys == ["treating", "specialist:pulmonologist"]
    assert item["requirements"][0]["doctor"]["full_name"].startswith("Петров")
    assert item["booking"] == {"booked": 0, "required": 2}
    assert "report_text" not in item["study"]  # заключение пациенту не показываем

    nid = item["notification"]["id"]
    read = client.post(f"{API}/notifications/{nid}/read", headers=kuznetsova).json()
    assert read["notification"]["status"] == "read"

    def book(doctor_id, requirement, nth=0):
        days = client.get(f"{API}/doctors/{doctor_id}/slots", headers=kuznetsova).json()
        slot = days[0]["slots"][nth]
        return client.post(
            f"{API}/appointments",
            headers=kuznetsova,
            json={
                "doctor_id": doctor_id,
                "scheduled_for": slot,
                "notification_id": nid,
                "requirement": requirement,
            },
        )

    pulmonologists = client.get(
        f"{API}/doctors", params={"specialty": "pulmonologist"}, headers=kuznetsova
    ).json()
    sidorova_id = pulmonologists[0]["id"]
    r = book(sidorova_id, "specialist:pulmonologist")
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["requirement"] == "specialist:pulmonologist"
    # направление уже закрыто — второй раз нельзя
    assert book(sidorova_id, "specialist:pulmonologist", nth=1).status_code == 409

    # Кейс открыт, пока не закрыто второе направление
    study_id = item["study"]["id"]
    card = client.get(f"{API}/studies/{study_id}", headers=petrov).json()
    assert card["status"] == "notified"
    assert _my_notification(client, kuznetsova)["booking"] == {"booked": 1, "required": 2}

    # отказаться после записи нельзя
    assert client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova).status_code == 409

    petrov_id = item["treating_doctor"]["id"]
    r = book(petrov_id, "treating", nth=1)  # другое время — две записи на одно время нельзя
    assert r.status_code == 200, r.text
    second = r.json()

    view = _my_notification(client, kuznetsova)
    assert {a["id"] for a in view["appointments"]} == {first["id"], second["id"]}
    assert view["booking"] == {"booked": 2, "required": 2}

    # Закрыты все направления — кейс завершён
    card = client.get(f"{API}/studies/{study_id}", headers=petrov).json()
    assert card["status"] == "completed"
    assert {a["id"] for a in card["appointments"]} == {first["id"], second["id"]}
    actions = [
        e["action"] for e in client.get(f"{API}/studies/{study_id}/audit", headers=petrov).json()
    ]
    assert actions[-3:] == ["notification.read", "patient.booked", "patient.booked"]

    # запись видна у врача-консультанта, со ссылкой на исследование
    sidorova = login(client, "sidorova@clinic.demo")
    mine = client.get(f"{API}/appointments", headers=sidorova).json()
    booked = next(a for a in mine if a["id"] == first["id"])
    assert booked["study_id"] == study_id

    # Отмена одной записи снова открывает кейс
    r = client.patch(
        f"{API}/appointments/{second['id']}", headers=kuznetsova, json={"status": "cancelled"}
    )
    assert r.status_code == 200
    card = client.get(f"{API}/studies/{study_id}", headers=petrov).json()
    assert card["status"] == "notified"


def test_patient_declines(client, kuznetsova):
    nid = _my_notification(client, kuznetsova)["notification"]["id"]
    r = client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova)
    assert r.status_code == 200
    assert r.json()["notification"]["patient_action"] == "declined"


def test_slot_conflicts_and_validation(client, kuznetsova):
    doctor = _my_notification(client, kuznetsova)["treating_doctor"]
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
    doctor = _my_notification(client, kuznetsova)["treating_doctor"]
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
    doctor = item["treating_doctor"]
    days = client.get(f"{API}/doctors/{doctor['id']}/slots", headers=kuznetsova).json()
    first, second = days[0]["slots"][:2]

    def book(slot):
        return client.post(
            f"{API}/appointments",
            headers=kuznetsova,
            json={
                "doctor_id": doctor["id"],
                "scheduled_for": slot,
                "notification_id": nid,
                "requirement": "treating",
            },
        )

    aid = book(first).json()["id"]
    assert book(second).status_code == 409  # направление закрыто — второй раз нельзя
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


def test_research_booking_and_partial_seed(client, chief):
    """Иванов (seed) записан к пульмонологу, на КТ — нет: кейс открыт, 1 из 2."""
    ivanov = login(client, "ivanov@patient.demo")
    item = _my_notification(client, ivanov)
    assert item["booking"] == {"booked": 1, "required": 2}
    ct = next(r for r in item["requirements"] if r["key"] == "research:ct")
    assert ct["appointment_id"] is None
    study_id = item["study"]["id"]
    assert client.get(f"{API}/studies/{study_id}", headers=chief).json()["status"] == "notified"

    days = client.get(f"{API}/research/ct/slots", headers=ivanov).json()
    body = {
        "research_type": "ct",
        "scheduled_for": days[0]["slots"][0],
        "notification_id": item["notification"]["id"],
    }
    # без направления и к врачу на исследование — нельзя
    r = client.post(f"{API}/appointments", headers=ivanov, json=body)
    assert r.status_code == 422
    r = client.post(
        f"{API}/appointments", headers=ivanov, json={**body, "requirement": "research:mri"}
    )
    assert r.status_code == 422
    r = client.post(
        f"{API}/appointments", headers=ivanov, json={**body, "requirement": "research:ct"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["doctor"] is None and r.json()["research_type"] == "ct"

    card = client.get(f"{API}/studies/{study_id}", headers=chief).json()
    assert card["status"] == "completed"
    assert {r["key"] for r in card["requirements"] if r["appointment_id"]} == {
        "specialist:pulmonologist",
        "research:ct",
    }
    # слот кабинета занят
    days_after = client.get(f"{API}/research/ct/slots", headers=ivanov).json()
    assert body["scheduled_for"] not in days_after[0]["slots"]


def test_wrong_specialist_for_requirement(client, kuznetsova):
    item = _my_notification(client, kuznetsova)
    neuro = client.get(f"{API}/doctors", params={"specialty": "neurologist"}, headers=kuznetsova)
    doctor = neuro.json()[0]
    r = client.post(
        f"{API}/appointments",
        headers=kuznetsova,
        json={
            "doctor_id": doctor["id"],
            "scheduled_for": _first_free_slot(client, kuznetsova, doctor["id"]),
            "notification_id": item["notification"]["id"],
            "requirement": "specialist:pulmonologist",
        },
    )
    assert r.status_code == 422


def test_research_without_notification_is_rejected(client, kuznetsova):
    days = client.get(f"{API}/research/ct/slots", headers=kuznetsova).json()
    r = client.post(
        f"{API}/appointments",
        headers=kuznetsova,
        json={"research_type": "ct", "scheduled_for": days[0]["slots"][0]},
    )
    assert r.status_code == 422


# --- Уведомление после решения ---


def test_decision_notifies_all_contacts(client, sidorova):
    # Волков: телефон и email → SMS + email
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


def test_seed_notification_has_no_fake_history(client, kuznetsova):
    n = _my_notification(client, kuznetsova)["notification"]
    assert n["channels"] == ["sms", "email"]
    # Демо-уведомление на самом деле никуда не отправлялось — истории отправок нет
    assert n["deliveries"] == [] and n["reminders_sent"] == 0


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
    assert [r["key"] for r in view["requirements"]] == ["treating"]
    assert view["requirements"][0]["doctor"]["id"] == item["doctor"]["id"]

    doctors = client.get(f"{API}/doctors", headers=patient).json()
    other = next(d for d in doctors if d["id"] != item["doctor"]["id"])
    slot = _first_free_slot(client, patient, other["id"])
    r = client.post(
        f"{API}/appointments",
        headers=patient,
        json={
            "doctor_id": other["id"],
            "scheduled_for": slot,
            "notification_id": n["id"],
            "requirement": "treating",
        },
    )
    assert r.status_code == 422

    slot = _first_free_slot(client, patient, item["doctor"]["id"])
    r = client.post(
        f"{API}/appointments",
        headers=patient,
        json={
            "doctor_id": item["doctor"]["id"],
            "scheduled_for": slot,
            "notification_id": n["id"],
            "requirement": "treating",
        },
    )
    assert r.status_code == 200, r.text
    card = client.get(f"{API}/studies/{sid}", headers=petrov).json()
    assert card["status"] == "completed"  # единственное направление закрыто


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


def test_dashboard_from_seed(client, manager):
    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    # В seed нет ответов AI — согласия пока не с чем считать
    assert d["agreement"] == {"agreed": 0, "total": 0, "rate": None}
    assert d["details_agreement"]["total"] == 0
    assert sum(map(sum, d["confusion_matrix"]["matrix"])) == 0
    assert d["summary"]["studies_total"] == 16
    assert d["summary"]["decisions_total"] == 6
    assert d["summary"]["decisions_without_ai"] == 6
    assert d["latency"]["count"] == 0
    assert len(d["recent_decisions"]) == 6
    consult = next(r for r in d["notifications"] if r["recommendation"] == "specialist_consult")
    assert consult["sent"] == 4 and consult["booked"] == 1


def test_dashboard_updates_after_ai_and_decision(client, manager, petrov):
    analyze_all(client)
    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    assert d["latency"]["count"] == 10  # 10 исследований без решения проанализированы

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
    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    assert d["agreement"] == {"agreed": 0, "total": 1, "rate": 0.0}
    assert sum(map(sum, d["confusion_matrix"]["matrix"])) == 1


def test_dashboard_manager_only(client, petrov, chief):
    assert client.get(f"{API}/metrics/dashboard", headers=petrov).status_code == 403
    assert client.get(f"{API}/metrics/dashboard", headers=chief).status_code == 403


def test_schedule_access(client, petrov, chief, manager):
    doctors = client.get(f"{API}/doctors", headers=petrov).json()
    orlov = next(d for d in doctors if d["full_name"].startswith("Орлов"))
    # Врач — только своё расписание
    assert client.get(f"{API}/appointments", headers=petrov).status_code == 200
    r = client.get(f"{API}/appointments", params={"doctor_id": orlov["id"]}, headers=petrov)
    assert r.status_code == 403
    # Главврач — любого врача; в seed к Орлову записана Морозова по направлению
    items = client.get(
        f"{API}/appointments", params={"doctor_id": orlov["id"]}, headers=chief
    ).json()
    assert items and all(a["doctor"]["id"] == orlov["id"] for a in items)
    assert any(a["study_id"] for a in items)
    assert client.get(f"{API}/appointments", headers=manager).status_code == 403


def test_no_pathology_closes_case(client, petrov, manager):
    item = client.get(f"{API}/studies", params={"status": "new"}, headers=petrov).json()[0]
    sid = item["id"]
    # Только отдельно — вместе с другими направлениями нельзя
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=petrov,
        json={"chosen_types": ["no_pathology", "repeat_appointment"]},
    )
    assert r.status_code == 422

    r = client.post(
        f"{API}/studies/{sid}/decision", headers=petrov, json={"chosen_types": ["no_pathology"]}
    )
    assert r.status_code == 200, r.text
    card = client.get(f"{API}/studies/{sid}", headers=petrov).json()
    # Уведомление ушло, записываться некуда — кейс сразу завершён
    assert card["status"] == "completed"
    n = card["notification"]
    assert "патологии не выявлено" in n["text"].lower()
    # В каналы — коротко, без медицинских подробностей, со ссылкой на карточку на сайте
    assert "патолог" not in n["short_text"].lower()
    assert n["short_text"].endswith(f"/patient#n-{n['id']}")
    # SMS — свой, ещё более короткий текст; остальные каналы — short_text
    sms = {d["text"] for d in n["deliveries"] if d["channel"] == "sms"}
    assert {d["text"] for d in n["deliveries"] if d["channel"] != "sms"} == {n["short_text"]}
    assert len(sms) == 1 and sms.pop().startswith("Третье мнение: готов результат")
    assert {d["status"] for d in n["deliveries"]} == {"simulated"}
    assert card["requirements"] == []

    accounts = client.get(f"{API}/auth/demo-users").json()
    email = next(a["email"] for a in accounts if a["full_name"] == item["patient"]["full_name"])
    patient = login(client, email)
    view = next(
        x
        for x in client.get(f"{API}/patients/me/notifications", headers=patient).json()
        if x["notification"]["id"] == card["notification"]["id"]
    )
    assert view["requirements"] == [] and view["booking"] is None
    nid = view["notification"]["id"]
    assert client.post(f"{API}/notifications/{nid}/decline", headers=patient).status_code == 409

    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    assert d["confusion_matrix"]["labels"][-1] == "no_pathology"
    assert "no_pathology" not in {n["recommendation"] for n in d["notifications"]}


def test_dashboard_funnel_and_doctor_details(client, manager):
    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    total = next(r for r in d["funnel"] if r["scope"] == "all")
    # Seed: 6 уведомлений, все с направлениями; Морозова записана по всем,
    # Иванов — по одному из двух
    assert total["sent"] == 6
    assert total["booked_all"] == 1 and total["booked_any"] == 2
    assert total["read"] >= total["booked_any"]
    assert {r["scope"] for r in d["funnel"]} == {
        "all",
        "repeat_appointment",
        "specialist_consult",
        "additional_research",
    }
    assert all("details_rate" in row for row in d["by_doctor"])
    # Все 11 врачей, включая тех, у кого решений ещё нет; с решениями — сверху
    assert len(d["by_doctor"]) == 11
    assert d["by_doctor"][-1]["decisions"] == 0
