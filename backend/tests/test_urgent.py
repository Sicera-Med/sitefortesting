"""«Экстренная госпитализация»: только отдельно, без записи, кейс закрыт сразу, без напоминаний.
И справочники кодов совпадают с промтом AI-команды (ai_service/analysis.py)."""

import sys
from pathlib import Path

from tests.conftest import login

API = "/api/v1"


def test_urgent_hospitalization(client, petrov):
    item = client.get(f"{API}/studies", params={"status": "new"}, headers=petrov).json()[0]
    sid = item["id"]
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=petrov,
        json={"chosen_types": ["urgent_hospitalization", "repeat_appointment"]},
    )
    assert r.status_code == 422  # только отдельно
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=petrov,
        json={"chosen_types": ["urgent_hospitalization"]},
    )
    assert r.status_code == 200, r.text
    card = client.get(f"{API}/studies/{sid}", headers=petrov).json()
    n = card["notification"]
    assert card["status"] == "completed" and card["requirements"] == []
    assert n["next_reminder_at"] is None
    assert "ЭКСТРЕННУЮ ГОСПИТАЛИЗАЦИЮ" in n["text"] and "103" in n["text"]
    assert n["short_text"].startswith("Здравствуйте") and "СРОЧНО" in n["short_text"]

    accounts = client.get(f"{API}/auth/demo-users").json()
    email = next(a["email"] for a in accounts if a["full_name"] == item["patient"]["full_name"])
    patient = login(client, email)
    nid = n["id"]
    assert client.post(f"{API}/notifications/{nid}/decline", headers=patient).status_code == 409


def test_dictionaries_match_ai_prompt():
    """Коды, которыми отвечает модель, = коды нашего справочника (иначе пункты потеряются)."""
    ai_dir = Path(__file__).resolve().parents[2] / "ai_service"
    sys.path.insert(0, str(ai_dir))
    try:
        import analysis  # код AI-команды
    finally:
        sys.path.remove(str(ai_dir))
    from app.domain.dictionaries import RECOMMENDATION_TYPES, RESEARCH_TYPES, SPECIALISTS

    assert set(analysis.SPECIALISTS) == set(SPECIALISTS)
    assert set(analysis.RESEARCH_TYPES) == set(RESEARCH_TYPES)
    assert set(analysis.RECOMMENDATION_TYPES) == {str(t) for t in RECOMMENDATION_TYPES}
