"""Личный кабинет: профиль, контакты, каналы уведомлений, смена пароля."""

from tests.conftest import login

API = "/api/v1"


def test_staff_account(client, petrov):
    me = client.get(f"{API}/account", headers=petrov).json()
    assert me["role"] == "doctor" and me["specialty"] == "therapist"
    assert me["phone"] is None and me["notify_channels"] == []
    # У сотрудника нет телефона и каналов уведомлений
    r = client.patch(f"{API}/account", headers=petrov, json={"phone": "+7 900 000-00-00"})
    assert r.status_code == 422


def test_patient_contacts_and_email(client, kuznetsova):
    me = client.get(f"{API}/account", headers=kuznetsova).json()
    assert me["available_channels"] == ["sms", "email", "social"]
    assert me["notify_channels"] == ["sms", "email", "social"]

    r = client.patch(f"{API}/account", headers=kuznetsova, json={"email": "petrov@clinic.demo"})
    assert r.status_code == 409  # email занят
    r = client.patch(
        f"{API}/account",
        headers=kuznetsova,
        json={"email": "kuz@patient.demo", "socials": [], "phone": "+7 999 111-22-33"},
    )
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["email"] == "kuz@patient.demo" and me["socials"] == []
    assert me["available_channels"] == ["sms", "email"]

    # Несколько соцсетей: пустые отбрасываются, повторы схлопываются
    r = client.patch(
        f"{API}/account",
        headers=kuznetsova,
        json={
            "socials": [
                {"network": "telegram", "handle": " @kuz "},
                {"network": "telegram", "handle": "@KUZ"},
                {"network": "max", "handle": "+7 999 111-22-33"},
                {"network": "vk", "handle": "  "},
            ]
        },
    )
    assert r.json()["socials"] == [
        {"network": "telegram", "handle": "@kuz"},
        {"network": "max", "handle": "+7 999 111-22-33"},
    ]
    assert "social" in r.json()["available_channels"]
    login(client, "kuz@patient.demo")  # вход по новому email


def test_disabled_channel_is_not_used(client, chief):
    # Волков (seed): телефон и email, соцсети нет; выключает SMS
    volkov = login(client, "volkov@patient.demo")
    r = client.patch(f"{API}/account", headers=volkov, json={"notify_channels": ["email"]})
    assert r.json()["notify_channels"] == ["email"]

    study = next(
        s
        for s in client.get(f"{API}/studies", params={"status": "new"}, headers=chief).json()
        if s["patient"]["full_name"].startswith("Волков")
    )
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=chief,
        json={"chosen_types": ["repeat_appointment"]},
    )
    assert r.status_code == 200
    card = client.get(f"{API}/studies/{study['id']}", headers=chief).json()
    assert card["notification"]["channels"] == ["email"]


def test_change_password(client, petrov):
    body = {"old_password": "wrong", "new_password": "newpass"}
    assert client.post(f"{API}/account/password", headers=petrov, json=body).status_code == 422
    body = {"old_password": "demo", "new_password": "ab"}
    assert client.post(f"{API}/account/password", headers=petrov, json=body).status_code == 422
    body = {"old_password": "demo", "new_password": "newpass"}
    assert client.post(f"{API}/account/password", headers=petrov, json=body).status_code == 204
    r = client.post(f"{API}/auth/login", json={"email": "petrov@clinic.demo", "password": "demo"})
    assert r.status_code == 401
    login(client, "petrov@clinic.demo", "newpass")
