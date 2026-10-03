"""Сценарий врача: вход → очередь → карточка → анализ → решение."""

from tests.conftest import login

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
    assert {u["role"] for u in users} == {"doctor", "head", "patient"}
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


def test_head_sees_all(client, head):
    assert len(client.get(f"{API}/studies", headers=head).json()) == 15


def test_patient_cannot_see_studies(client, kuznetsova):
    assert client.get(f"{API}/studies", headers=kuznetsova).status_code == 403


def test_card(client, petrov):
    item = _study(client, petrov, status="ai_ready")
    card = client.get(f"{API}/studies/{item['id']}", headers=petrov).json()
    assert card["report_text"]
    assert card["ai"]["reasons"] and len(card["ai"]["ranked_options"]) == 3
    assert card["patient"]["age"] > 0


def test_unknown_study_404(client, petrov):
    assert client.get(f"{API}/studies/st_nope", headers=petrov).status_code == 404


# --- Сквозной сценарий ---


def test_analyze_then_decide(client, sidorova):
    study = _study(client, sidorova, status="new")
    sid = study["id"]

    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={"chosen_type": "repeat_appointment", "details": {"interval_days": 30}},
    )
    assert r.status_code == 409  # без анализа решать нельзя
    assert r.json()["error"]["code"] == "invalid_transition"

    r = client.post(f"{API}/studies/{sid}/analyze", headers=sidorova)
    assert r.status_code == 200, r.text
    ai = r.json()
    assert ai["source"] == "mock"

    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={"chosen_type": "specialist_consult", "details": {"specialist": "nope"}},
    )
    assert r.status_code == 422

    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={
            "chosen_type": ai["recommendation"],
            "details": _details(ai["recommendation"]),
            "comment": "Согласна",
        },
    )
    assert r.status_code == 200, r.text
    decision = r.json()
    assert decision["accepted_ai"] is True
    assert decision["ai_inference_id"] == ai["id"]

    card = client.get(f"{API}/studies/{sid}", headers=sidorova).json()
    assert card["status"] == "decided"

    # повторное решение и повторный анализ после решения запрещены
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=sidorova,
        json={"chosen_type": "repeat_appointment", "details": {"interval_days": 5}},
    )
    assert r.status_code == 409
    assert client.post(f"{API}/studies/{sid}/analyze", headers=sidorova).status_code == 409

    actions = [
        e["action"] for e in client.get(f"{API}/studies/{sid}/audit", headers=sidorova).json()
    ]
    assert actions == ["study.created", "ai.analyzed", "decision.created"]


def _details(kind):
    return {
        "repeat_appointment": {"interval_days": 30},
        "specialist_consult": {"specialist": "oncologist"},
        "additional_research": {"research_type": "biopsy"},
    }[kind]


def test_other_doctor_cannot_act(client, petrov, sidorova):
    study = _study(client, sidorova, status="ai_ready", scope="all")  # не Сидоровой — проверим
    owner = study["doctor"]["full_name"]
    actor = sidorova if owner.startswith("Петров") else petrov
    sid = study["id"]
    assert client.post(f"{API}/studies/{sid}/analyze", headers=actor).status_code == 403
    r = client.post(
        f"{API}/studies/{sid}/decision",
        headers=actor,
        json={"chosen_type": "repeat_appointment", "details": {"interval_days": 7}},
    )
    assert r.status_code == 403


def test_head_can_analyze_but_not_decide(client, head):
    study = _study(client, head, status="new", scope="all")
    assert client.post(f"{API}/studies/{study['id']}/analyze", headers=head).status_code == 200
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=head,
        json={"chosen_type": "repeat_appointment", "details": {"interval_days": 7}},
    )
    assert r.status_code == 403


def test_reanalyze_keeps_history(client, petrov):
    study = _study(client, petrov, status="ai_ready")
    r = client.post(f"{API}/studies/{study['id']}/analyze", headers=petrov)
    assert r.status_code == 200
    history = client.get(f"{API}/studies/{study['id']}/history", headers=petrov).json()
    assert len(history["inferences"]) == 2
    actions = [
        e["action"] for e in client.get(f"{API}/studies/{study['id']}/audit", headers=petrov).json()
    ]
    assert actions[-1] == "ai.reanalyzed"


def test_decision_without_ai_after_failure(client, petrov):
    study = _study(client, petrov, status="ai_failed")
    r = client.post(
        f"{API}/studies/{study['id']}/decision",
        headers=petrov,
        json={"chosen_type": "specialist_consult", "details": {"specialist": "urologist"}},
    )
    assert r.status_code == 200
    assert r.json()["accepted_ai"] is None


def test_ai_failure_marks_study(client, petrov):
    # Подменяем текст заключения маркером сбоя mock-провайдера
    store = client.app.state.store
    study = _study(client, petrov, status="new")
    store.get_study(study["id"]).report_text += " [[ai_fail]]"
    r = client.post(f"{API}/studies/{study['id']}/analyze", headers=petrov)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "ai_failed"
    assert (
        client.get(f"{API}/studies/{study['id']}", headers=petrov).json()["status"] == "ai_failed"
    )


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


def test_ai_test_bench(client, head):
    before = len(client.app.state.store.inferences)
    r = client.post(
        f"{API}/ai/test",
        headers=head,
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


def test_patient_can_login_but_not_use_ai(client):
    headers = login(client, "ivanov@patient.demo")
    r = client.post(
        f"{API}/ai/test",
        headers=headers,
        json={"report_text": "x", "study_type": "ct", "body_region": "chest"},
    )
    assert r.status_code == 403
