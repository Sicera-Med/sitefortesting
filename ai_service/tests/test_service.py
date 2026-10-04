"""HTTP-обёртка: промт, справочник и проверка — код AI-команды, вызов модели подменён."""

import json

import pytest
from fastapi.testclient import TestClient

import main

# Ответ в формате analysis.py AI-команды (options + reasons), кардиомегалия на РГ ОГК
ANSWER = {
    "options": [
        {
            "type": "additional_research",
            "recommended": True,
            "items": [
                {
                    "code": "echocardiography",
                    "reason": "Кардиомегалия, КТИ 0,6",
                    "timing": None,
                    "sources": ["kr_chf_suspected"],
                }
            ],
            "sources": [],
            "rationale": "Расширение тени сердца — ЭхоКГ по КР «ХСН».",
        },
        {
            "type": "specialist_consult",
            "recommended": False,
            "items": [
                {
                    "code": "cardiologist",
                    "reason": "Кардиомегалия",
                    "timing": None,
                    "sources": ["kr_pneumonia_xray"],  # в этой записи кардиолога нет
                }
            ],
            "sources": [],
            "rationale": "Консультация кардиолога.",
        },
    ],
    "reasons": [{"code": "cardiomegaly", "label": "Кардиомегалия, КТИ 0,6"}],
}
REQUEST = {
    "request_id": "req_1",
    "study_id": "st_1",
    "study_type": "xray",
    "body_region": "chest",
    "report_text": "Описание: Сердце: тень сердца расширена, КТИ 0,6.\nЗаключение: Кардиомегалия.",
    "patient_context": {"age": 64, "sex": "m"},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "HF_TOKEN", "test")
    monkeypatch.setattr(main, "MODEL", "test-model")
    return TestClient(main.app)


def test_analyze_returns_colleagues_format_with_sources(client, monkeypatch):
    seen = []

    def fake_ask(messages):
        seen.append(messages)
        return "<think>…</think>\n" + json.dumps(ANSWER, ensure_ascii=False)

    monkeypatch.setattr(main, "ask", fake_ask)
    r = client.post("/ai/v1/analyze", json=REQUEST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request_id"] == "req_1"
    assert body["model"] == {"name": "test-model", "version": "hf-inference"}
    assert body["warnings"] == []
    assert len(seen) == 1  # полный справочник модель не просила
    system, user = seen[0]
    assert "РГ" in system["content"] and "Справочник" in system["content"]
    assert "возраст 64, пол мужской" in user["content"]

    item = body["options"][0]["items"][0]
    # attach_sources AI-команды: документ и страницы по id; url — официальная страница
    [ref] = item["source_refs"]
    assert "Хроническая сердечная недостаточность" in ref["document"]
    assert ref["url"] == "https://cr.minzdrav.gov.ru/view-cr/156_2"
    # Ссылка на запись, где такого действия нет, — неподтверждённая
    alt = body["options"][1]["items"][0]
    assert alt["source_refs"] == [] and alt["unconfirmed_sources"] == ["kr_pneumonia_xray"]


def test_second_pass_with_full_guidelines(client, monkeypatch):
    answers = [{**ANSWER, "need_full_guidelines": True}, ANSWER]
    calls = []

    def fake_ask(messages):
        calls.append(messages)
        return json.dumps(answers[len(calls) - 1])

    monkeypatch.setattr(main, "ask", fake_ask)
    body = client.post("/ai/v1/analyze", json=REQUEST).json()
    assert len(calls) == 2
    assert body["guidelines_mode"] == "весь справочник по запросу модели"
    assert len(calls[1][0]["content"]) > len(calls[0][0]["content"])  # справочник целиком


def test_validate_errors_become_warnings(client, monkeypatch):
    bad = {**ANSWER, "options": [{**ANSWER["options"][0], "items": []}]}
    monkeypatch.setattr(main, "ask", lambda m: json.dumps(bad))
    body = client.post("/ai/v1/analyze", json=REQUEST).json()
    assert any("пустой items" in w for w in body["warnings"])


def test_no_pathology_is_valid(client, monkeypatch):
    normal = {
        "options": [{"type": "no_pathology", "recommended": True, "items": [], "sources": []}],
        "reasons": [{"code": "normal", "label": "Патологии не выявлено"}],
    }
    monkeypatch.setattr(main, "ask", lambda m: json.dumps(normal))
    assert client.post("/ai/v1/analyze", json=REQUEST).json()["warnings"] == []


def test_not_json_and_model_errors_are_502(client, monkeypatch):
    monkeypatch.setattr(main, "ask", lambda m: "извините, не могу")
    assert client.post("/ai/v1/analyze", json=REQUEST).status_code == 502

    def boom(messages):
        raise RuntimeError("rate limit")

    monkeypatch.setattr(main, "ask", boom)
    r = client.post("/ai/v1/analyze", json=REQUEST)
    assert r.status_code == 502 and "rate limit" in r.json()["detail"]


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


def test_not_configured_is_503(monkeypatch):
    monkeypatch.setattr(main, "settings", lambda: ("", "test-model"))
    assert TestClient(main.app).post("/ai/v1/analyze", json=REQUEST).status_code == 503


def test_explain_b2c(client, monkeypatch):
    seen = []

    def fake_ask(messages):
        seen.append(messages)
        return json.dumps(
            {
                "summary": "Тень сердца на снимке увеличена.",
                "explanations": [{"term": "КТИ", "explanation": "соотношение размеров"}],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(main, "ask", fake_ask)
    r = client.post(
        "/ai/v1/explain",
        json={
            "request_id": "req_2",
            "study_type": "xray",
            "body_region": "chest",
            "description": "Сердце: тень сердца расширена, КТИ 0,6.",
            "conclusion": "Кардиомегалия.",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["summary"].startswith("Тень сердца")
    system, user = seen[0]
    assert "пациент" in system["content"].lower()  # промт B2C AI-команды
    assert "Описание:" in user["content"] and "Заключение:" in user["content"]

    monkeypatch.setattr(main, "ask", lambda m: json.dumps({"summary": 1}))
    bad = client.post(
        "/ai/v1/explain",
        json={"request_id": "r", "study_type": "xray", "body_region": "chest"},
    )
    assert bad.status_code == 502


def test_study_type_mapping_and_urls():
    assert main.study_type_for_model("ct", "chest") == "ct_chest"
    assert main.study_type_for_model("ct", "head") == "КТ ГМ"
    assert main.study_type_for_model("mammography", "breast") == "mammography"
    # У каждого документа справочника — проверенный адрес
    assert set(main.SOURCE_URLS) == set(main.SOURCES)
    pdf = main.source_url({"file": main.SOURCES["lungrads"]["file"], "pages": "9–10, 15"})
    assert pdf.endswith(".pdf#page=9")
