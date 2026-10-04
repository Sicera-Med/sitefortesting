"""Сценарий врача: вход → очередь → карточка (AI — автоматически) → решение."""

from tests.conftest import analyze_all, login

API = "/api/v1"


def _study(client, headers, *, status, scope="mine"):
    r = client.get(f"{API}/studies", params={"scope": scope, "status": status}, headers=headers)
    assert r.status_code == 200
    return r.json()[0]


# --- Auth ---


def test_login_wrong_password(client):
    r = client.post(f"{API}/auth/login", json={"email": "petrov@clinic.demo", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_and_patient_profile(client, petrov, kuznetsova):
    me = client.get(f"{API}/auth/me", headers=petrov).json()
    assert me["role"] == "doctor" and me["specialty"] == "therapist"
    me = client.get(f"{API}/auth/me", headers=kuznetsova).json()
    assert me["role"] == "patient" and me["patient_id"].startswith("pat_")


def test_no_token_and_bad_token(client):
    r = client.get(f"{API}/studies")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    r = client.get(f"{API}/studies", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_demo_users(client):
    users = client.get(f"{API}/auth/demo-users").json()
    assert {u["role"] for u in users} == {"doctor", "chief", "manager", "patient"}
    assert all(u["password"] == "demo" for u in users)


# --- Списки и права ---


def test_doctor_queue_is_mine_by_default(client, petrov):
    items = client.get(f"{API}/studies", headers=petrov).json()
    assert len(items) == 8
    assert all(i["doctor"]["full_name"].startswith("Петров") for i in items)
    assert all(i["can_act"] for i in items if i["status"] != "completed")


def test_doctor_scope_all_is_read_only_for_others(client, petrov):
    items = client.get(f"{API}/studies", params={"scope": "all"}, headers=petrov).json()
    assert len(items) == 15
    others = [i for i in items if not i["doctor"]["full_name"].startswith("Петров")]
    assert others and not any(i["can_act"] for i in others)


def test_chief_and_manager_see_all(client, chief, manager):
    assert len(client.get(f"{API}/studies", headers=chief).json()) == 15
    items = client.get(f"{API}/studies", headers=manager).json()
    assert len(items) == 15 and not any(i["can_act"] for i in items)


def test_patient_cannot_see_studies(client, kuznetsova):
    assert client.get(f"{API}/studies", headers=kuznetsova).status_code == 403


def test_card(client, petrov):
    analyze_all(client)
    item = _study(client, petrov, status="ai_ready")
    card = client.get(f"{API}/studies/{item['id']}", headers=petrov).json()
    assert card["report_text"]
    assert card["ai"]["reasons"] and len(card["ai"]["ranked_options"]) == 3
    assert card["patient"]["age"] > 0


def test_unknown_study_404(client, petrov):
    assert client.get(f"{API}/studies/st_nope", headers=petrov).status_code == 404


# --- Сквозной сценарий ---


def test_seed_has_no_ai_answers(client, chief):
    """Ответы AI — только от сервиса; в seed их нет."""
    items = client.get(f"{API}/studies", headers=chief).json()
    assert all(i["ai"] is None for i in items)


def test_auto_analysis_then_decide(client, sidorova):
    sid = _study(client, sidorova, status="new")["id"]
    assert analyze_all(client) > 0  # врач ничего не запускает — анализ идёт сам

    card = client.get(f"{API}/studies/{sid}", headers=sidorova).json()
    assert card["status"] == "ai_ready"
    ai = card["ai"]
    assert ai["source"] == "mock"

    other = next(
        t for t in ("repeat_appointment", "specialist_consult") if t != ai["recommendation"]
    )
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={
            "chosen_types": [ai["recommendation"], other],  # принял вариант AI и дополнил
            "details": {**_details(ai["recommendation"]), **_details(other)},
            "comment": "Согласна, плюс контроль",
        },
    )
    assert r.status_code == 200, r.text
    decision = r.json()
    assert decision["accepted_ai"] is True
    assert decision["ai_inference_id"] == ai["id"]
    assert len(decision["chosen_types"]) == 2

    card = client.get(f"{API}/studies/{sid}", headers=sidorova).json()
    assert card["status"] == "notified"  # уведомление ушло автоматически

    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={"chosen_types": ["repeat_appointment"]},
    )
    assert r.status_code == 409

    events = client.get(f"{API}/studies/{sid}/audit", headers=sidorova).json()
    assert [e["action"] for e in events] == [
        "study.created",
        "ai.analyzed",
        "decision.created",
        "notification.sent",
    ]
    assert events[1]["actor_id"] is None  # анализ запустила система


def test_decision_without_ai(client, petrov):
    """Врач может решить, не дожидаясь AI; потом анализ это решение не трогает."""
    sid = _study(client, petrov, status="new")["id"]
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=petrov,
        json={
            "chosen_types": ["specialist_consult", "additional_research"],
            "details": {"specialists": ["urologist", "oncologist"], "research_types": ["ct"]},
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["accepted_ai"] is None and d["ai_inference_id"] is None
    assert d["details"] == {"specialists": ["urologist", "oncologist"], "research_types": ["ct"]}

    analyze_all(client)
    card = client.get(f"{API}/studies/{sid}", headers=petrov).json()
    assert card["status"] == "notified" and card["ai"] is None


def test_decision_validation(client, petrov):
    sid = _study(client, petrov, status="new")["id"]

    def decide(body):
        return client.post(f"{API}/studies/{sid}/decision", headers=petrov, json=body)

    assert decide({"chosen_types": []}).status_code == 422  # минимум один вариант
    assert decide({"chosen_types": ["specialist_consult"]}).status_code == 422  # нет специалистов
    r = decide({"chosen_types": ["specialist_consult"], "details": {"specialists": ["shaman"]}})
    assert r.status_code == 422
    # старый формат (один вариант) принимается
    r = decide({"chosen_type": "specialist_consult", "details": {"specialist": "oncologist"}})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_types"] == ["specialist_consult"]
    assert r.json()["details"] == {"specialists": ["oncologist"]}


def _details(kind):
    return {
        "repeat_appointment": {},
        "specialist_consult": {"specialists": ["oncologist"]},
        "additional_research": {"research_types": ["biopsy"]},
    }[kind]


def test_other_doctor_cannot_decide(client, petrov, sidorova):
    study = _study(client, sidorova, status="new", scope="all")
    owner = study["doctor"]["full_name"]
    actor = sidorova if owner.startswith("Петров") else petrov
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=actor,
        json={"chosen_types": ["repeat_appointment"]},
    )
    assert r.status_code == 403


def test_manager_cannot_decide(client, manager):
    study = _study(client, manager, status="new", scope="all")
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=manager,
        json={"chosen_types": ["repeat_appointment"]},
    )
    assert r.status_code == 403


def test_chief_decides_for_any_patient(client, chief, manager):
    study = _study(client, chief, status="new", scope="all")
    assert study["can_act"]
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=chief,
        json={"chosen_types": ["repeat_appointment"]},
    )
    assert r.status_code == 200
    card = client.get(f"{API}/studies/{study['id']}", headers=chief).json()
    assert card["status"] == "notified"
    # Решение засчитано главврачу, лечащий врач не меняется
    assert card["doctor"]["id"] == study["doctor"]["id"]
    d = client.get(f"{API}/metrics/dashboard", headers=manager).json()
    assert any(row["full_name"].startswith("Смирнова") for row in d["by_doctor"])


def test_manual_analyze_endpoint_removed(client, petrov):
    study = _study(client, petrov, status="new")
    assert client.post(f"{API}/studies/{study['id']}/analyze", headers=petrov).status_code in (
        404,
        405,
    )


def test_ai_failure_then_automatic_retry(client, petrov):
    # Маркер сбоя mock-провайдера: AI «не отвечает»
    store = client.app.state.store
    sid = _study(client, petrov, status="new")["id"]
    study = store.get_study(sid)
    study.report_text += " [[ai_fail]]"
    analyze_all(client)
    card = client.get(f"{API}/studies/{sid}", headers=petrov).json()
    assert card["status"] == "ai_failed" and card["ai"] is None
    events = client.get(f"{API}/studies/{sid}/audit", headers=petrov).json()
    assert events[-1]["action"] == "ai.failed"

    # Повторные неудачи не засоряют таймлайн: одно событие на серию сбоев
    analyzer = client.app.state.analyzer
    analyzer.retry_s = 0
    analyze_all(client)
    events = client.get(f"{API}/studies/{sid}/audit", headers=petrov).json()
    assert [e["action"] for e in events].count("ai.failed") == 1

    # Сервис «поднялся» — следующий проход после паузы повторит анализ сам
    study.report_text = study.report_text.replace(" [[ai_fail]]", "")
    analyze_all(client)
    assert client.get(f"{API}/studies/{sid}", headers=petrov).json()["status"] == "ai_ready"


def test_reanalysis_not_repeated_after_success(client, petrov):
    analyze_all(client)
    assert analyze_all(client) == 0  # всё уже проанализировано


def test_manual_ai_result_upload(client, petrov):
    study = _study(client, petrov, status="new")
    payload = {
        "model": {"name": "team-model", "version": "1.0"},
        "recommendation": "additional_research",
        "confidence": 0.8,
        "reasons": [{"code": "x", "label": "Причина", "weight": 0.5}],
    }
    r = client.post(f"{API}/studies/{study['id']}/ai-result", headers=petrov, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "manual"
    assert body["ranked_options"][0]["type"] == "additional_research"

    bad = {"recommendation": "surgery", "confidence": 2, "reasons": []}
    r = client.post(f"{API}/studies/{study['id']}/ai-result", headers=petrov, json=bad)
    assert r.status_code == 502
    assert "recommendation" in r.json()["error"]["details"]["reason"]


# --- AI test bench и справочники ---


def test_ai_test_bench(client, chief):
    before = len(client.app.state.store.inferences)
    r = client.post(
        f"{API}/ai/test",
        headers=chief,
        json={
            "report_text": "УЗИ щитовидной железы: узел TI-RADS 5 с микрокальцинатами",
            "study_type": "ultrasound",
            "body_region": "neck",
            "patient_context": {"age": 40, "sex": "f"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["recommendation"] == "additional_research"
    assert body["raw_contract"]["model"]["name"] == "ultrasound-triage"
    assert len(client.app.state.store.inferences) == before  # ничего не сохранили


def test_ai_models_and_dictionaries(client, petrov):
    assert client.get(f"{API}/ai/models", headers=petrov).json()
    d = client.get(f"{API}/dictionaries", headers=petrov).json()
    assert {"recommendation_types", "specialists", "research_types"} <= d.keys()


def test_dictionaries_are_public(client):
    r = client.get(f"{API}/dictionaries")
    assert r.status_code == 200
    assert r.json()["specialists"]


def test_patient_can_login_but_not_use_ai(client):
    headers = login(client, "ivanov@patient.demo")
    r = client.post(
        f"{API}/ai/test",
        headers=headers,
        json={"report_text": "x", "study_type": "ct", "body_region": "chest"},
    )
    assert r.status_code == 403
