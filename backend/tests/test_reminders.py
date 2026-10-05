"""Уведомления: история отправок по всем контактам и напоминания раз в неделю, до 3 раз."""

from datetime import UTC, datetime, timedelta

from tests.conftest import login

API = "/api/v1"


def _remind(client) -> int:
    return client.app.state.reminders.run_once()


def _notification(client, nid):
    return client.app.state.store.get_notification(nid)


def test_seed_has_no_fake_history_and_nothing_sent_on_start(client):
    sokolov = login(client, "sokolov@patient.demo")
    items = client.get(f"{API}/patients/me/notifications", headers=sokolov).json()
    # КТ ГМ у Кима — уведомление 9 дней назад, записи нет. Демо-уведомление никуда
    # не отправлялось: истории нет, первое напоминание — через неделю от запуска
    head = next(i for i in items if i["study"]["body_region"] == "head")["notification"]
    assert head["deliveries"] == [] and head["reminders_sent"] == 0
    due = datetime.fromisoformat(head["next_reminder_at"])
    assert due > datetime.now(UTC) + timedelta(days=6)
    assert _remind(client) == 0  # при старте ничего не уходит


def test_reminders_weekly_up_to_three(client, petrov):
    kuz = login(client, "kuznetsova@patient.demo")
    nid = client.get(f"{API}/patients/me/notifications", headers=kuz).json()[0]["notification"][
        "id"
    ]
    n = _notification(client, nid)
    assert _remind(client) == 0  # неделя ещё не прошла
    for i in range(1, 4):
        n.next_reminder_at -= timedelta(days=8)
        assert _remind(client) == 1
        assert n.reminders_sent == i
    assert n.next_reminder_at is None  # лимит 3 исчерпан
    assert _remind(client) == 0
    view = client.get(f"{API}/patients/me/notifications", headers=kuz).json()[0]
    assert {d["attempt"] for d in view["notification"]["deliveries"]} == {1, 2, 3}
    reminder = next(
        d
        for d in view["notification"]["deliveries"]
        if d["attempt"] == 1 and d["channel"] == "email"
    )
    assert reminder["text"].startswith("Здравствуйте") and "Напоминаем" in reminder["text"]
    assert reminder["text"].endswith(f"/patient#n-{nid}")
    events = client.get(f"{API}/studies/{n.study_id}/audit", headers=petrov).json()
    reminders = [e for e in events if e["action"] == "notification.reminder"]
    assert [e["payload"]["attempt"] for e in reminders] == [1, 2, 3]


def test_no_reminders_after_decline(client):
    kuz = login(client, "kuznetsova@patient.demo")
    nid = client.get(f"{API}/patients/me/notifications", headers=kuz).json()[0]["notification"][
        "id"
    ]
    client.post(f"{API}/notifications/{nid}/decline", headers=kuz)
    n = _notification(client, nid)
    assert n.next_reminder_at is None
    n.next_reminder_at = n.sent_at  # даже если срок «подошёл» — отказ важнее
    assert _remind(client) == 0


def test_no_reminders_for_no_pathology(client, petrov):
    item = client.get(f"{API}/studies", params={"status": "new"}, headers=petrov).json()[0]
    client.post(
        f"{API}/studies/{item['id']}/decision",
        headers=petrov,
        json={"chosen_types": ["no_pathology"]},
    )
    card = client.get(f"{API}/studies/{item['id']}", headers=petrov).json()
    assert card["notification"]["next_reminder_at"] is None
    assert card["notification"]["deliveries"]


def test_patient_studies_screen(client):
    popov = login(client, "popov@patient.demo")
    items = client.get(f"{API}/patients/me/studies", headers=popov).json()
    # У Попова два исследования: КТ без решения и МРТ с уведомлением
    assert len(items) == 2
    pending = next(i for i in items if i["recommendations"] is None)
    assert pending["notification_id"] is None and pending["booking"] is None
    done = next(i for i in items if i["recommendations"])
    assert done["notification_id"] and done["booking"] == {"booked": 0, "required": 1}
    assert all("report_text" not in i for i in items)


def test_explanation_b2c(client, kuznetsova):
    item = client.get(f"{API}/patients/me/notifications", headers=kuznetsova).json()[0]
    assert item["explanation"] is None
    nid = item["notification"]["id"]
    r = client.post(f"{API}/notifications/{nid}/explain", headers=kuznetsova)
    assert r.status_code == 200, r.text
    assert r.json()["summary"] and r.json()["terms"]
    # Сохранено — второй запрос отдаёт готовое, в AI не идёт
    assert client.post(f"{API}/notifications/{nid}/explain", headers=kuznetsova).status_code == 200
    item = client.get(f"{API}/patients/me/notifications", headers=kuznetsova).json()[0]
    assert item["explanation"]["summary"] == r.json()["summary"]
    # Чужое уведомление — как несуществующее
    other = login(client, "ivanov@patient.demo")
    assert client.post(f"{API}/notifications/{nid}/explain", headers=other).status_code == 404
