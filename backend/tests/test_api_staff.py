"""Главврач: врачи с нагрузкой, добавление, отключение, смена лечащего врача."""

from tests.conftest import login

API = "/api/v1"


def test_staff_is_chief_only(client, petrov, manager):
    assert client.get(f"{API}/staff/doctors", headers=petrov).status_code == 403
    assert client.get(f"{API}/staff/doctors", headers=manager).status_code == 403


def test_doctors_with_load(client, chief):
    items = client.get(f"{API}/staff/doctors", headers=chief).json()
    petrov = next(d for d in items if d["full_name"].startswith("Петров"))
    assert petrov["active"] and petrov["open_studies"] > 0 and petrov["decisions"] > 0


def test_create_update_and_disable_doctor(client, chief):
    body = {
        "full_name": "Новикова Елена Петровна",
        "email": "novikova@clinic.demo",
        "specialty": "urologist",
        "password": "secret",
    }
    r = client.post(f"{API}/staff/doctors", headers=chief, json=body)
    assert r.status_code == 200, r.text
    doctor = r.json()
    assert client.post(f"{API}/staff/doctors", headers=chief, json=body).status_code == 409
    bad = {**body, "email": "x@clinic.demo", "specialty": "astrologer"}
    assert client.post(f"{API}/staff/doctors", headers=chief, json=bad).status_code == 422

    # Новый врач входит и виден пациентам для записи
    token = login(client, "novikova@clinic.demo", "secret")
    urologists = client.get(
        f"{API}/doctors", params={"specialty": "urologist"}, headers=token
    ).json()
    assert [d["id"] for d in urologists] == [doctor["id"]]

    r = client.patch(
        f"{API}/staff/doctors/{doctor['id']}", headers=chief, json={"specialty": "therapist"}
    )
    assert r.json()["specialty"] == "therapist"

    # Отключённый врач не входит, его нет в записи, старый токен не работает
    r = client.patch(f"{API}/staff/doctors/{doctor['id']}", headers=chief, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    r = client.post(
        f"{API}/auth/login", json={"email": "novikova@clinic.demo", "password": "secret"}
    )
    assert r.status_code == 401
    assert client.get(f"{API}/auth/me", headers=token).status_code == 401
    therapists = client.get(
        f"{API}/doctors", params={"specialty": "therapist"}, headers=chief
    ).json()
    assert doctor["id"] not in {d["id"] for d in therapists}


def test_reassign_treating_doctor(client, chief, petrov, sidorova):
    study = client.get(f"{API}/studies", params={"status": "new"}, headers=petrov).json()[0]
    sidorova_id = client.get(f"{API}/auth/me", headers=sidorova).json()["id"]

    r = client.post(
        f"{API}/studies/{study['id']}/reassign", headers=petrov, json={"doctor_id": sidorova_id}
    )
    assert r.status_code == 403
    r = client.post(
        f"{API}/studies/{study['id']}/reassign", headers=chief, json={"doctor_id": sidorova_id}
    )
    assert r.status_code == 200, r.text
    assert r.json()["doctor"]["id"] == sidorova_id
    # Теперь решает Сидорова, а не Петров
    card = client.get(f"{API}/studies/{study['id']}", headers=sidorova).json()
    assert card["can_act"]
    # Пациент больше не Петрова — его карточка ему недоступна
    assert client.get(f"{API}/studies/{study['id']}", headers=petrov).status_code == 403
    actions = [
        e["action"] for e in client.get(f"{API}/studies/{study['id']}/audit", headers=chief).json()
    ]
    assert "study.reassigned" in actions

    # После решения сменить нельзя
    done = client.get(f"{API}/studies", params={"status": "completed"}, headers=chief).json()[0]
    r = client.post(
        f"{API}/studies/{done['id']}/reassign", headers=chief, json={"doctor_id": sidorova_id}
    )
    assert r.status_code == 409
