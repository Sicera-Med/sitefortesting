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
    ],
    "reasons": [{"code": "nodule", "label": "Узел 8 мм", "weight": 0.42}],
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
    assert [o.type for o in r.ranked_options] == [
        "specialist_consult",
        "additional_research",
        "repeat_appointment",
    ]
    assert r.reasons[0].code == "reason_1"
    joined = " ".join(r.warnings)
    for fragment in ("request_id", "model", "magic", "missing", "reordered"):
        assert fragment in joined
