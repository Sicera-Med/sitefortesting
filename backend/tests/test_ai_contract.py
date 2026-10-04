"""Контракт с AI: формат v2 модели AI-команды (options) и старые форматы v1 / v1.3."""

import pytest

from app.ai.contract import AIContractError, parse_ai_response

AORTA_REF = {
    "document": "Клинические рекомендации «Аневризмы грудной и торакоабдоминальной аорты»",
    "organization": "Рубрикатор клинических рекомендаций Минздрава России, ID 919_1",
    "year": 2025,
    "pages": "89",
    "file": "x.pdf",
    "verified_by": None,
    "text": "Клинические рекомендации «Аневризмы…» (Минздрав, 2025), стр. 89",
    "url": "https://cr.minzdrav.gov.ru/view-cr/919_1",
}

# Формат analysis.py AI-команды после validate + attach_sources (ai_service)
V2 = {
    "request_id": "req_1",
    "model": {"name": "Qwen/Qwen3-4B-Instruct-2507", "version": "hf-inference"},
    "options": [
        {
            "type": "additional_research",
            "recommended": True,
            "items": [
                {
                    "code": "ct_angiography",
                    "reason": "Дилатация восходящей аорты 40 мм",
                    "timing": "через 6–12 месяцев",
                    "sources": ["kr_aorta_followup"],
                    "source_refs": [AORTA_REF],
                    "unconfirmed_sources": [],
                },
                {
                    "code": "echocardiography",
                    "reason": "Паракардиальный жир 387 мл",
                    "timing": None,
                    "sources": [],
                    "source_refs": [],
                    "unconfirmed_sources": ["kr_mesothelioma_x"],
                },
            ],
            "sources": [],
            "source_refs": [],
            "rationale": "Дилатация аорты — КТА и ЭхоКГ по КР.",
        },
        {
            "type": "specialist_consult",
            "recommended": False,
            "items": [{"code": "vascular_surgeon", "reason": "Аорта 40 мм", "source_refs": []}],
            "rationale": "Сосудистый хирург для решения о вмешательстве.",
        },
    ],
    "reasons": [
        {"code": "aorta_dilation", "label": "Дилатация восходящей аорты 40 мм"},
        {"code": "cac", "label": "CAC-DRS A2"},
    ],
    "guidelines_mode": "по словам протокола",
    "warnings": [],
}


def _parse(data):
    return parse_ai_response(data, expected_request_id="req_1")


def test_v2_options():
    r = _parse(V2)
    assert r.warnings == ()
    assert r.recommendation == "additional_research" and r.confidence is None
    assert r.details == {"research_types": ["ct_angiography", "echocardiography"]}
    assert [str(o.type) for o in r.ranked_options][:2] == [
        "additional_research",
        "specialist_consult",
    ]
    assert len(r.ranked_options) == 5  # остальные типы — в конце
    main, alt = r.options
    assert main["recommended"] and not alt["recommended"]
    item = main["items"][0]
    assert item["timing"] == "через 6–12 месяцев"
    assert item["source_refs"][0]["url"] == "https://cr.minzdrav.gov.ru/view-cr/919_1"
    assert "file" not in item["source_refs"][0]  # лишнее не храним
    assert main["items"][1]["unconfirmed_sources"] == ["kr_mesothelioma_x"]
    assert r.guidelines_mode == "по словам протокола"
    assert [x.weight for x in r.reasons] == [None, None]
    assert r.to_contract_json()["options"][0]["type"] == "additional_research"


def test_v2_soft_fixes():
    data = {
        **V2,
        "request_id": None,
        "options": [
            {"type": "magic", "recommended": True, "items": []},
            {
                "type": "specialist_consult",
                "recommended": False,
                "items": [{"code": "astrologer"}, {"code": "cardiologist"}],
            },
            {"type": "no_pathology", "recommended": False, "items": [{"code": "x"}]},
        ],
        "warnings": ["options: тип повторяется"],
    }
    r = _parse(data)
    # «magic» отброшен; основного нет — основным стал первый валидный
    assert r.recommendation == "specialist_consult"
    assert r.details == {"specialists": ["cardiologist"]}
    assert r.options[1]["items"] == []  # у «патологии не выявлено» пунктов нет
    joined = " ".join(r.warnings)
    for fragment in ("magic", "astrologer", "exactly one recommended", "ai_service:", "request_id"):
        assert fragment in joined


def test_v2_strict():
    with pytest.raises(AIContractError):
        _parse({**V2, "options": [{"type": "magic"}]})
    with pytest.raises(AIContractError):
        _parse({**V2, "reasons": []})


def test_v2_urgent_and_no_pathology():
    for kind in ("urgent_hospitalization", "no_pathology"):
        data = {**V2, "options": [{"type": kind, "recommended": True, "items": []}]}
        r = _parse(data)
        assert r.recommendation == kind and r.details == {} and r.warnings == ()


# --- Старые форматы: v1 (уверенность, ranked_options) и v1.3 (options_order) ---

V1 = {
    "request_id": "req_1",
    "model": {"name": "m", "version": "1"},
    "recommendation": "additional_research",
    "confidence": 0.87,
    "ranked_options": [
        {"type": "additional_research", "score": 0.87},
        {"type": "specialist_consult", "score": 0.09},
    ],
    "reasons": [{"code": "nodule", "label": "Узел 8 мм", "weight": 0.42}],
    "details": {"research_types": ["ct", "mri_of_soul", "ct"]},
}


def test_v1_scored():
    r = _parse(V1)
    assert r.confidence == 0.87 and r.ranked_options[0].score == 0.87
    assert r.details == {"research_types": ["ct"]}  # неизвестное выброшено, дубли схлопнуты
    assert any("mri_of_soul" in w for w in r.warnings)
    assert r.options == ()


def test_v13_options_order():
    r = _parse(
        {
            "request_id": "req_1",
            "recommendation": "specialist_consult",
            "options_order": ["specialist_consult", "repeat_appointment"],
            "specialists": ["cardiologist"],
            "reasons": [{"code": "cardiomegaly", "label": "Кардиомегалия"}],
        }
    )
    assert r.details == {"specialists": ["cardiologist"]}
    assert [str(o.type) for o in r.ranked_options][:2] == [
        "specialist_consult",
        "repeat_appointment",
    ]


def test_strict_old_formats():
    with pytest.raises(AIContractError):
        _parse({**V1, "recommendation": "magic"})
    with pytest.raises(AIContractError):
        _parse({**V1, "reasons": []})
    with pytest.raises(AIContractError):
        _parse([1, 2])
