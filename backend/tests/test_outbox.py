"""Настоящие рассылки: каналы SMSPilot / SMTP, очередь outbox, «Напомнить сейчас».

Сеть и SMTP подменены — из тестов ничего не отправляется.
"""

import pytest

from app.core.config import Settings, get_settings
from app.domain.enums import NotificationChannel as C
from app.seed import seed_demo
from app.services import channels
from app.store import Store
from tests.conftest import login

API = "/api/v1"


def _kuz_notification(client):
    kuz = login(client, "kuznetsova@patient.demo")
    return client.get(f"{API}/patients/me/notifications", headers=kuz).json()[0]["notification"]


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, APP_ENV="test", AI_PROVIDER="mock", **kw)


# --- Каналы ---


def test_plan_real_or_simulated():
    assert channels.plan(_settings(), C.SMS) == (
        "simulated",
        "рассылка выключена (NOTIFY_REAL=false)",
    )
    real = {"NOTIFY_REAL": True}
    assert channels.plan(_settings(**real), C.SMS) == (
        "simulated",
        "не настроено: SMSPILOT_API_KEY",
    )
    assert channels.plan(_settings(**real, SMSPILOT_API_KEY="k"), C.SMS) == ("pending", None)
    assert channels.plan(_settings(**real, SMSPILOT_API_KEY="k", NOTIFY_SMS=False), C.SMS)[1] == (
        "канал SMS выключен"
    )
    smtp = {"SMTP_USER": "a@yandex.ru", "SMTP_PASSWORD": "p"}
    assert channels.plan(_settings(**real, **smtp), C.EMAIL) == ("pending", None)


@pytest.mark.parametrize(
    "raw", ["+7 (900) 123-45-67", "89001234567", "9001234567", "7 900 123 45 67"]
)
def test_normalize_phone(raw):
    assert channels.normalize_phone(raw) == "79001234567"


def test_normalize_phone_rejects_foreign():
    with pytest.raises(channels.ChannelError):
        channels.normalize_phone("+1 555 0100")


class _Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_send_sms(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return _Resp({"send": [{"server_id": "1", "status": "0"}]})

    monkeypatch.setattr(channels.httpx, "get", fake_get)
    s = _settings(SMSPILOT_API_KEY="KEY", SMSPILOT_FROM="INFORM")
    channels.send_sms(s, "8 900 123-45-67", "Третье мнение: тест")
    [(url, params)] = calls
    assert url == channels.SMSPILOT_URL
    assert params == {
        "send": "Третье мнение: тест",
        "to": "79001234567",
        "apikey": "KEY",
        "format": "json",
        "from": "INFORM",
    }

    error = {"error": {"code": "10", "description_ru": "Недостаточно средств"}}
    monkeypatch.setattr(channels.httpx, "get", lambda *a, **kw: _Resp(error))
    with pytest.raises(channels.ChannelError, match="Недостаточно средств"):
        channels.send_sms(s, "+79001234567", "x")


def test_send_email(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"], msg.get_content().strip()))

    monkeypatch.setattr(channels.smtplib, "SMTP_SSL", FakeSMTP)
    s = _settings(SMTP_USER="clinic@yandex.ru", SMTP_PASSWORD="app-pass")
    channels.send_email(s, "patient@example.ru", "Готов результат: http://x")
    assert sent == [
        ("connect", "smtp.yandex.ru", 465),
        ("login", "clinic@yandex.ru", "app-pass"),
        ("send", "patient@example.ru", channels.EMAIL_SUBJECT, "Готов результат: http://x"),
    ]


# --- Очередь и «Напомнить сейчас» ---


def test_remind_now_goes_through_outbox(client, petrov, monkeypatch):
    monkeypatch.setenv("NOTIFY_REAL", "true")
    monkeypatch.setenv("SMSPILOT_API_KEY", "KEY")
    monkeypatch.setenv("SMTP_USER", "clinic@yandex.ru")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    get_settings.cache_clear()
    nid = _kuz_notification(client)["id"]

    r = client.post(f"{API}/notifications/{nid}/remind", headers=petrov)
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["reminders_sent"] == 1
    new = [d for d in n["deliveries"] if d["attempt"] == 1]
    status = {d["channel"]: d["status"] for d in new}
    assert status == {"sms": "pending", "email": "pending"}
    assert next(d for d in new if d["channel"] == "sms")["text"].startswith(
        "Третье мнение: напоминаем"
    )

    sent = []

    def fake_send(channel, target, text):
        if channel == "email":
            raise channels.ChannelError("SMTP: SMTPAuthenticationError")
        sent.append((channel, target, text))

    outbox = client.app.state.outbox
    monkeypatch.setattr(outbox, "send", fake_send)
    assert outbox.run_once() == 2
    assert outbox.run_once() == 0  # повторно не отправляется
    assert [s[0] for s in sent] == ["sms"]
    n = client.app.state.store.get_notification(nid)
    by_channel = {d.channel: d for d in n.deliveries if d.attempt == 1}
    assert by_channel["sms"].status == "sent"
    assert by_channel["email"].status == "failed"
    assert "SMTPAuthenticationError" in by_channel["email"].detail


def test_remind_now_rules(client, petrov, sidorova, chief, kuznetsova, monkeypatch):
    nid = _kuz_notification(client)["id"]
    url = f"{API}/notifications/{nid}/remind"
    assert client.post(url, headers=kuznetsova).status_code == 403  # пациент
    assert client.post(url, headers=sidorova).status_code == 403  # не лечащий врач
    assert client.post(url, headers=chief).status_code == 403  # главврач не напоминает

    monkeypatch.setenv("NOTIFY_REMIND_COOLDOWN_S", "10")
    get_settings.cache_clear()
    n = client.app.state.store.get_notification(nid)
    n.deliveries.clear()  # история seed старая — проверяем только свой лимит частоты
    assert client.post(url, headers=petrov).status_code == 200
    r = client.post(url, headers=petrov)
    assert r.status_code == 429 and r.json()["error"]["details"]["retry_after_s"] == 10

    monkeypatch.setenv("NOTIFY_REMIND_COOLDOWN_S", "0")
    get_settings.cache_clear()
    for _ in range(2):
        assert client.post(url, headers=petrov).status_code == 200
    r = client.post(url, headers=petrov)
    assert r.status_code == 409 and "3" in r.json()["error"]["message"]
    assert n.next_reminder_at is None
    audit = [e for e in client.app.state.store.audit if e.action == "notification.reminder"]
    assert audit[-1].payload["manual"] is True


def test_remind_not_needed_after_decline(client, petrov, kuznetsova):
    nid = _kuz_notification(client)["id"]
    assert client.post(f"{API}/notifications/{nid}/decline", headers=kuznetsova).status_code == 200
    r = client.post(f"{API}/notifications/{nid}/remind", headers=petrov)
    assert r.status_code == 409


# --- Контакты ---


def test_contact_email_used_for_delivery(client, kuznetsova, petrov):
    r = client.patch(
        f"{API}/account", headers=kuznetsova, json={"contact_email": "Real@Example.ru"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["contact_email"] == "real@example.ru"
    nid = _kuz_notification(client)["id"]
    n = client.post(f"{API}/notifications/{nid}/remind", headers=petrov).json()
    email = next(d for d in n["deliveries"] if d["attempt"] == 1 and d["channel"] == "email")
    assert email["target"] == "real@example.ru"

    bad = client.patch(f"{API}/account", headers=kuznetsova, json={"contact_email": "nope"})
    assert bad.status_code == 422
    # Пустая строка — снова на email входа
    r = client.patch(f"{API}/account", headers=kuznetsova, json={"contact_email": ""})
    assert r.json()["contact_email"] is None


def test_seed_demo_contacts():
    store = Store()
    seed_demo(store, contact_phone="+7 999 000-00-01", contact_email="colleague@example.ru")
    assert {p.phone for p in store.patients.values()} == {"+7 999 000-00-01"}
    assert {p.contact_email for p in store.patients.values()} == {"colleague@example.ru"}
    # Истории отправок у демо-уведомлений нет — при старте ничего не отправляется
    assert all(not n.deliveries for n in store.list_notifications())
