"""HTTP-обёртка: промт и разбор — код AI-команды, вызов модели подменён."""

import json

import pytest
from fastapi.testclient import TestClient

import main

ANSWER = {
    "recommendation": "specialist_consult",
    "options_order": ["specialist_consult", "additional_research", "repeat_appointment"],
    "specialists": ["cardiologist"],
    "research_types": [],
    "reasons": [{"code": "cardiomegaly", "label": "Кардиомегалия, КТИ 0,6"}],
}
REQUEST = {
    "request_id": "req_1",
    "study_id": "st_1",
    "study_type": "xray",
    "body_region": "chest",
    "report_text": "Сердце: тень расширена, КТИ 0,6.\nЗаключение: кардиомегалия.",
    "patient_context": {"age": 64, "sex": "m"},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "HF_TOKEN", "test")
    monkeypatch.setattr(main, "MODEL", "test-model")
    return TestClient(main.app)


def test_analyze_returns_colleagues_format(client, monkeypatch):
    seen = {}

    def fake_ask(messages):
        seen["messages"] = messages
        return "<think>…</think>\n" + json.dumps(ANSWER, ensure_ascii=False)

    monkeypatch.setattr(main, "ask", fake_ask)
    r = client.post("/ai/v1/analyze", json=REQUEST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendation"] == "specialist_consult"
    assert body["request_id"] == "req_1"
    assert body["model"] == {"name": "test-model", "version": "hf-inference"}
    assert body["warnings"] == []
    system, user = seen["messages"]
    assert "РГ ОГК" in system["content"]  # шаблон БФТ подставлен
    assert "возраст 64, пол мужской" in user["content"]


def test_validate_errors_become_warnings(client, monkeypatch):
    bad = {**ANSWER, "specialists": []}
    monkeypatch.setattr(main, "ask", lambda m: json.dumps(bad))
    body = client.post("/ai/v1/analyze", json=REQUEST).json()
    assert body["warnings"] == ["specialist_consult без specialists"]


def test_not_json_and_model_errors_are_502(client, monkeypatch):
    monkeypatch.setattr(main, "ask", lambda m: "извините, не могу")
    assert client.post("/ai/v1/analyze", json=REQUEST).status_code == 502

    def boom(messages):
        raise RuntimeError("rate limit")

    monkeypatch.setattr(main, "ask", boom)
    r = client.post("/ai/v1/analyze", json=REQUEST)
    assert r.status_code == 502 and "rate limit" in r.json()["detail"]


def test_not_configured_is_503(monkeypatch):
    monkeypatch.setattr(main, "settings", lambda: ("", "test-model"))
    assert TestClient(main.app).post("/ai/v1/analyze", json=REQUEST).status_code == 503


def test_study_type_mapping():
    assert main.study_type_for_model("ct", "chest") == "ct_chest"
    assert main.study_type_for_model("mammography", "breast") == "mammography"
    assert main.study_type_for_model("ultrasound", "kidneys") == "УЗИ, почки"


def test_hf_errors_are_short(client, monkeypatch):
    class Resp:
        status_code = 402

    class HfError(Exception):
        response = Resp()

    def broke(messages):
        raise HfError("Client error '402 Payment Required' for url ... very long text")

    monkeypatch.setattr(main, "ask", broke)
    detail = client.post("/ai/v1/analyze", json=REQUEST).json()["detail"]
    assert detail == (
        "Модель недоступна: закончились кредиты Hugging Face — нужен другой токен или оплата"
        " (HTTP 402)"
    )
