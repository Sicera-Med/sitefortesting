import pytest

from app.ai.contract import AIContractError, parse_ai_response

GOOD = {
    "request_id": "req_1",
    "model": {"name": "m", "version": "1"},
    "recommendation": "additional_research",
    "confidence": 0.87,
    "ranked_options": [
        {"type": "additional_research", "score": 0.87},
        {"type": "specialist_consult", "score": 0.09},
        {"type": "repeat_appointment", "score": 0.04},
        {"type": "no_pathology", "score": 0.0},
    ],
    "reasons": [{"code": "nodule", "label": "Узел 8 мм", "weight": 0.42}],
    "details": {"research_types": ["ct"]},
}

# Формат модели коллег (ai_service/analysis.py): без уверенности и весов
COLLEAGUES = {
    "request_id": "req_1",
    "model": {"name": "Qwen/Qwen2.5-72B-Instruct", "version": "hf-inference"},
    "recommendation": "specialist_consult",
    "options_order": [
        "specialist_consult",
        "additional_research",
        "repeat_appointment",
        "no_pathology",
    ],
    "specialists": ["cardiologist"],
    "research_types": [],
    "reasons": [
        {"code": "cardiomegaly", "label": "Кардиомегалия, КТИ 0,6"},
        {"code": "rib_fracture", "label": "Консолидированный перелом ребра"},
    ],
}


def test_valid_response_has_no_warnings():
    r = parse_ai_response(GOOD, expected_request_id="req_1")
    assert r.warnings == ()
    assert r.to_contract_json()["ranked_options"] == GOOD["ranked_options"]


@pytest.mark.parametrize(
    "patch",
    [
        {"recommendation": "surgery"},
        {"confidence": 1.5},
        {"reasons": []},
        {"reasons": [{"label": "", "weight": 0.1}]},
        {"reasons": [{"label": "x", "weight": 2}]},
    ],
)
def test_strict_violations(patch):
    with pytest.raises(AIContractError):
        parse_ai_response({**GOOD, **patch}, expected_request_id="req_1")


def test_not_an_object():
    with pytest.raises(AIContractError):
        parse_ai_response([1, 2], expected_request_id="req_1")


def test_soft_fixes():
    data = {
        "recommendation": "specialist_consult",
        "confidence": 0.6,
        "ranked_options": [
            {"type": "repeat_appointment", "score": 0.1},
            {"type": "specialist_consult", "score": 0.6},
            {"type": "magic", "score": 0.3},
        ],
        "reasons": [{"label": "Без кода", "weight": 0.3}],
        "extra_field": "ignored",
    }
    r = parse_ai_response(data, expected_request_id="req_9")
    assert r.request_id == "req_9"
    assert r.model_name == "unknown"
    # недостающие варианты делят остаток поровну: 0.3 / 2 = 0.15 > 0.1
    assert [o.type for o in r.ranked_options] == [
        "specialist_consult",
        "additional_research",
        "no_pathology",
        "repeat_appointment",
    ]
    assert r.reasons[0].code == "reason_1"
    joined = " ".join(r.warnings)
    for fragment in ("request_id", "model", "magic", "missing", "reordered"):
        assert fragment in joined


def test_details_research_types_kept():
    data = {**GOOD, "details": {"research_types": ["ct_contrast", "lab_tests"]}}
    r = parse_ai_response(data, expected_request_id="req_1")
    assert r.details == {"research_types": ["ct_contrast", "lab_tests"]}
    assert r.warnings == ()
    assert r.to_contract_json()["details"] == r.details


def test_details_are_optional():
    data = {k: v for k, v in GOOD.items() if k != "details"}
    r = parse_ai_response(data, expected_request_id="req_1")
    assert r.details == {}
    assert r.warnings == ("additional_research without research_types",)  # как их validate()


def test_colleagues_format():
    r = parse_ai_response(COLLEAGUES, expected_request_id="req_1")
    assert r.warnings == ()
    assert r.confidence is None
    assert [str(o.type) for o in r.ranked_options] == COLLEAGUES["options_order"]
    assert all(o.score is None for o in r.ranked_options)
    assert r.details == {"specialists": ["cardiologist"]}
    assert [x.weight for x in r.reasons] == [None, None]
    assert r.to_contract_json()["options_order"] == COLLEAGUES["options_order"]


def test_colleagues_format_soft_fixes():
    data = {
        **COLLEAGUES,
        "options_order": ["repeat_appointment", "specialist_consult", "magic"],
        "specialists": ["cardiologist", "astrologer"],
        "warnings": ["коды не из справочника: ['astrologer']"],
    }
    r = parse_ai_response(data, expected_request_id="req_1")
    assert [str(o.type) for o in r.ranked_options] == [
        "specialist_consult",
        "repeat_appointment",
        "additional_research",
        "no_pathology",
    ]
    assert r.details == {"specialists": ["cardiologist"]}
    assert any(w.startswith("ai_service:") for w in r.warnings)
    assert any("astrologer" in w for w in r.warnings)
    assert any("magic" in w for w in r.warnings)
    # без recommendation или причин — ответ отклоняется
    with pytest.raises(AIContractError):
        parse_ai_response({**COLLEAGUES, "reasons": []}, expected_request_id="req_1")


def test_details_soft_validation():
    data = {**GOOD, "details": {"research_types": ["ct", "mri_of_soul", "ct"]}}
    r = parse_ai_response(data, expected_request_id="req_1")
    assert r.details == {"research_types": ["ct"]}  # неизвестное выброшено, дубли схлопнуты
    assert any("mri_of_soul" in w for w in r.warnings)

    legacy = parse_ai_response(
        {**GOOD, "details": {"research_type": "biopsy"}}, expected_request_id="req_1"
    )
    assert legacy.details == {"research_types": ["biopsy"]}

    consult = {**GOOD, "recommendation": "specialist_consult", "confidence": 0.9}
    ok = parse_ai_response(
        {**consult, "details": {"specialist": "oncologist"}}, expected_request_id="req_1"
    )
    assert ok.details == {"specialists": ["oncologist"]}  # старый формат → список
    many = parse_ai_response(
        {**consult, "details": {"specialists": ["oncologist", "pulmonologist"]}},
        expected_request_id="req_1",
    )
    assert many.details == {"specialists": ["oncologist", "pulmonologist"]}
    bad = parse_ai_response(
        {**consult, "details": {"specialist": "shaman"}}, expected_request_id="req_1"
    )
    assert bad.details == {} and any("shaman" in w for w in bad.warnings)


def test_no_pathology_recommendation():
    data = {
        **COLLEAGUES,
        "recommendation": "no_pathology",
        "options_order": [
            "no_pathology",
            "repeat_appointment",
            "specialist_consult",
            "additional_research",
        ],
        "specialists": [],
        "reasons": [{"code": "normal", "label": "Патологических изменений не выявлено"}],
    }
    r = parse_ai_response(data, expected_request_id="req_1")
    assert r.recommendation == "no_pathology" and r.details == {} and r.warnings == ()
