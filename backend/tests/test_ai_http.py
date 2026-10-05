"""Стык с AI-сервисом (ai_service/): HTTP-запрос backend и ответ в формате модели коллег.

Сам сервис здесь подменён транспортом httpx — проверяем только формат обмена.
"""

import json

import httpx

from app.ai.http_provider import ANALYZE_PATH, HttpAIProvider
from tests.conftest import analyze_all, login

API = "/api/v1"


def _answer(request: dict) -> dict:
    """Как отвечает ai_service/main.py: ответ analysis.py + request_id, model, warnings."""
    return {
        "recommendation": "specialist_consult",
        "options_order": ["specialist_consult", "repeat_appointment", "additional_research"],
        "specialists": ["pulmonologist"],
        "research_types": [],
        "reasons": [{"code": "consolidation", "label": "Консолидация в S9–S10"}],
        "request_id": request["request_id"],
        "model": {"name": "Qwen/Qwen2.5-72B-Instruct", "version": "hf-inference"},
        "warnings": [],
    }


def test_auto_analysis_through_ai_service_format(client, chief):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == ANALYZE_PATH
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json=_answer(body))

    transport = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ai")
    service = client.app.state.analyzer.service
    service.ai.provider = HttpAIProvider(base_url="http://ai", timeout_s=5, client=transport)

    assert analyze_all(client) > 0
    assert {"request_id", "study_type", "body_region", "report_text", "patient_context"} <= set(
        seen[0]
    )

    item = client.get(f"{API}/studies", params={"status": "ai_ready"}, headers=chief).json()[0]
    assert item["ai"] == {"recommendation": "specialist_consult", "confidence": None}
    card = client.get(f"{API}/studies/{item['id']}", headers=chief).json()
    ai = card["ai"]
    assert ai["source"] == "http"
    assert ai["model_name"] == "Qwen/Qwen2.5-72B-Instruct"
    assert ai["ranked_options"][0]["type"] == "specialist_consult"
    assert all(o["score"] is None for o in ai["ranked_options"])
    assert ai["reasons"] == [
        {"code": "consolidation", "label": "Консолидация в S9–S10", "weight": None}
    ]
    assert ai["details"] == {"specialists": ["pulmonologist"]}

    # Решение лечащего врача с этим ответом: согласие считается, уверенности нет
    treating = client.app.state.store.get_user(item["doctor"]["id"])
    r = client.post(
        f"{API}/studies/{item['id']}/decision",
        headers=login(client, treating.email),
        json={
            "chosen_types": ["specialist_consult"],
            "details": {"specialists": ["pulmonologist"]},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted_ai"] is True and r.json()["ai_confidence"] is None


def test_ai_service_error_is_ai_failed(client, chief):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "Модель вернула ответ не в формате JSON"})

    transport = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ai")
    client.app.state.analyzer.service.ai.provider = HttpAIProvider(
        base_url="http://ai", timeout_s=5, client=transport
    )
    analyze_all(client)
    items = client.get(f"{API}/studies", params={"status": "ai_failed"}, headers=chief).json()
    assert items
    # Врачу — понятная причина из detail сервиса, без технической обёртки
    event = client.get(f"{API}/studies/{items[0]['id']}/audit", headers=chief).json()[-1]
    assert event["payload"]["error"] == (
        "Ошибка AI-сервиса: Модель вернула ответ не в формате JSON"
    )
