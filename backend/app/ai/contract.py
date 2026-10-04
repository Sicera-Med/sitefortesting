"""AI-контракт v1.3 (SPEC §6) — формат обмена с AI-сервисом коллег.

ВНИМАНИЕ: менять формат только по согласованию с AI-командой.

Модель коллег (ai_service/analysis.py) отвечает:
  recommendation, options_order, specialists, research_types, reasons[{code, label}]
— без уверенности и весов. Старый формат v1 (confidence, ranked_options со score,
details, weight у причин) тоже принимается.

Валидация двухуровневая (§6.3):
- строго — recommendation и непустые reasons с label; нарушение → AIContractError;
- мягко — confidence, порядок вариантов, детали, request_id, model: чиним сами и пишем warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.decisions import normalize_ai_details
from app.domain.enums import RecommendationType, Sex, StudyType
from app.domain.models import RankedOption, Reason

# --- Запрос (backend → AI) ---


class PatientContext(BaseModel):
    age: int | None = Field(default=None, ge=0, le=130)
    sex: Sex | None = None


class AIRequest(BaseModel):
    request_id: str
    study_id: str | None
    study_type: StudyType
    body_region: str
    report_text: str = Field(min_length=1)
    patient_context: PatientContext = Field(default_factory=PatientContext)


# --- Ответ (AI → backend) ---


class _ModelInfo(BaseModel):
    name: str = "unknown"
    version: str = "unknown"


class _Option(BaseModel):
    type: str
    score: float | None = None


class _Reason(BaseModel):
    code: str = ""
    label: str = Field(min_length=1)
    weight: float | None = Field(default=None, ge=0, le=1)


class _RawResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    request_id: str | None = None
    model: _ModelInfo | None = None
    recommendation: RecommendationType
    confidence: float | None = Field(default=None, ge=0, le=1)  # модель коллег не даёт
    ranked_options: list[_Option] = Field(default_factory=list)  # v1: варианты со score
    options_order: list[str] = Field(default_factory=list)  # коллеги: порядок без оценок
    reasons: list[_Reason] = Field(min_length=1)
    # Детали: v1 — объект details; коллеги — specialists/research_types на верхнем уровне
    details: Any = None
    specialists: Any = None
    research_types: Any = None
    # Замечания проверки на стороне AI-сервиса (их validate()) — попадают в наши warnings
    warnings: list[str] = Field(default_factory=list)


class AIContractError(ValueError):
    """Ответ AI нарушает строгую часть контракта."""


@dataclass(frozen=True, slots=True)
class AIResult:
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float | None
    ranked_options: tuple[RankedOption, ...]
    reasons: tuple[Reason, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    details: dict[str, Any] = field(default_factory=dict)

    def to_contract_json(self) -> dict[str, Any]:
        """Обратно в формат §6.2 — для /ai/test и отладки."""
        return {
            "request_id": self.request_id,
            "model": {"name": self.model_name, "version": self.model_version},
            "recommendation": str(self.recommendation),
            "confidence": self.confidence,
            "options_order": [str(o.type) for o in self.ranked_options],
            "ranked_options": [
                {"type": str(o.type), "score": o.score} for o in self.ranked_options
            ],
            "reasons": [
                {"code": r.code, "label": r.label, "weight": r.weight} for r in self.reasons
            ],
            "details": self.details,
        }


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "<root>"
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)


def _known_types(raw: list[str], field_name: str, warnings: list[str]) -> list[RecommendationType]:
    """Коды вариантов по порядку: неизвестные и повторы отбрасываем."""
    result: list[RecommendationType] = []
    for code in raw:
        try:
            kind = RecommendationType(code)
        except ValueError:
            warnings.append(f"{field_name}: unknown type {code!r} ignored")
            continue
        if kind in result:
            warnings.append(f"{field_name}: duplicate {kind} ignored")
            continue
        result.append(kind)
    return result


def _order_options(
    order: list[RecommendationType], recommendation: RecommendationType, warnings: list[str]
) -> tuple[RankedOption, ...]:
    """Порядок без оценок (формат коллег): рекомендация первой, недостающие — в конец."""
    if order and order[0] is not recommendation:
        warnings.append("options_order: recommendation is not first, moved")
    ordered = [recommendation] + [t for t in order if t is not recommendation]
    missing = [t for t in RecommendationType if t not in ordered]
    if order and missing:
        warnings.append(f"options_order: missing {', '.join(missing)}, appended")
    return tuple(RankedOption(t, None) for t in ordered + missing)


def _scored_options(
    raw: list[_Option], recommendation: RecommendationType, confidence: float, warnings: list[str]
) -> tuple[RankedOption, ...]:
    """v1: варианты со score — чиним сумму, порядок и score рекомендации."""
    scores: dict[RecommendationType, float] = {}
    given = _known_types([o.type for o in raw], "ranked_options", warnings)
    for opt in raw:
        if opt.type in given and opt.type not in scores and opt.score is not None:
            scores[RecommendationType(opt.type)] = min(max(opt.score, 0.0), 1.0)

    if scores.get(recommendation) != confidence:
        if recommendation in scores:
            warnings.append("ranked_options: score of recommendation != confidence, fixed")
        scores[recommendation] = confidence

    missing = [t for t in RecommendationType if t not in scores]
    if missing:
        warnings.append(f"ranked_options: missing {', '.join(missing)}, filled")
        rest = max(0.0, 1.0 - sum(scores.values()))
        for t in missing:
            scores[t] = round(rest / len(missing), 4)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if given != [t for t, _ in ordered if t in given]:
        warnings.append("ranked_options: reordered by score")
    if ordered[0][0] is not recommendation:
        warnings.append("ranked_options: recommendation is not the top-scored option")
    return tuple(RankedOption(t, s) for t, s in ordered)


def _raw_details(raw: _RawResponse, warnings: list[str]) -> Any:
    """Детали из объекта details (v1) или из полей верхнего уровня (формат коллег)."""
    if raw.specialists is None and raw.research_types is None:
        return raw.details
    if raw.details is not None:
        warnings.append(
            "details and top-level specialists/research_types both given, top-level used"
        )
    merged: dict[str, Any] = {}
    if raw.specialists is not None:
        merged["specialists"] = raw.specialists
    if raw.research_types is not None:
        merged["research_types"] = raw.research_types
    return merged


def parse_ai_response(data: Any, *, expected_request_id: str) -> AIResult:
    """Разбирает ответ AI по контракту. Бросает AIContractError при нарушении строгой части."""
    if not isinstance(data, dict):
        raise AIContractError("response must be a JSON object")
    try:
        raw = _RawResponse.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(_format_errors(exc)) from exc

    warnings: list[str] = [f"ai_service: {w}" for w in raw.warnings]
    if raw.request_id != expected_request_id:
        warnings.append("request_id missing or mismatched, replaced")
    model = raw.model or _ModelInfo()
    if raw.model is None:
        warnings.append("model info missing")

    reasons = tuple(
        Reason(r.code or f"reason_{i + 1}", r.label, r.weight) for i, r in enumerate(raw.reasons)
    )
    details = normalize_ai_details(raw.recommendation, _raw_details(raw, warnings), warnings)
    key = {
        RecommendationType.SPECIALIST_CONSULT: "specialists",
        RecommendationType.ADDITIONAL_RESEARCH: "research_types",
    }.get(raw.recommendation)
    if key and not details.get(key):
        warnings.append(f"{raw.recommendation} without {key}")

    # Уверенность есть — v1 со score; нет — только порядок вариантов
    if raw.confidence is not None:
        options = _scored_options(raw.ranked_options, raw.recommendation, raw.confidence, warnings)
    else:
        order = raw.options_order or [o.type for o in raw.ranked_options]
        options = _order_options(
            _known_types(order, "options_order", warnings), raw.recommendation, warnings
        )

    return AIResult(
        request_id=expected_request_id,
        model_name=model.name,
        model_version=model.version,
        recommendation=raw.recommendation,
        confidence=raw.confidence,
        ranked_options=options,
        reasons=reasons,
        warnings=tuple(warnings),
        details=details,
    )
