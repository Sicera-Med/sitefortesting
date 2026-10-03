"""AI-контракт v1 (SPEC §6) — формат обмена с AI-сервисом коллег.

ВНИМАНИЕ: менять формат только по согласованию с AI-командой.

Валидация двухуровневая (§6.3):
- строго — recommendation, confidence, reasons; нарушение → AIContractError;
- мягко — ranked_options, request_id, model: чиним сами и пишем warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    score: float


class _Reason(BaseModel):
    code: str = ""
    label: str = Field(min_length=1)
    weight: float = Field(ge=0, le=1)


class _RawResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    request_id: str | None = None
    model: _ModelInfo | None = None
    recommendation: RecommendationType
    confidence: float = Field(ge=0, le=1)
    ranked_options: list[_Option] = Field(default_factory=list)
    reasons: list[_Reason] = Field(min_length=1)


class AIContractError(ValueError):
    """Ответ AI нарушает строгую часть контракта."""


@dataclass(frozen=True, slots=True)
class AIResult:
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float
    ranked_options: tuple[RankedOption, ...]
    reasons: tuple[Reason, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_contract_json(self) -> dict[str, Any]:
        """Обратно в формат §6.2 — для /ai/test и отладки."""
        return {
            "request_id": self.request_id,
            "model": {"name": self.model_name, "version": self.model_version},
            "recommendation": str(self.recommendation),
            "confidence": self.confidence,
            "ranked_options": [
                {"type": str(o.type), "score": o.score} for o in self.ranked_options
            ],
            "reasons": [
                {"code": r.code, "label": r.label, "weight": r.weight} for r in self.reasons
            ],
        }


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "<root>"
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)


def _normalize_options(
    raw: list[_Option], recommendation: RecommendationType, confidence: float, warnings: list[str]
) -> tuple[RankedOption, ...]:
    scores: dict[RecommendationType, float] = {}
    given: dict[RecommendationType, None] = {}  # упорядоченное множество
    for opt in raw:
        try:
            kind = RecommendationType(opt.type)
        except ValueError:
            warnings.append(f"ranked_options: unknown type {opt.type!r} ignored")
            continue
        if kind in scores:
            warnings.append(f"ranked_options: duplicate {kind} ignored")
            continue
        scores[kind] = min(max(opt.score, 0.0), 1.0)
        given[kind] = None

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
    given_order = list(given)  # порядок, в котором прислала модель
    if given_order != [t for t, _ in ordered if t in given]:
        warnings.append("ranked_options: reordered by score")
    if ordered[0][0] is not recommendation:
        warnings.append("ranked_options: recommendation is not the top-scored option")
    return tuple(RankedOption(t, s) for t, s in ordered)


def parse_ai_response(data: Any, *, expected_request_id: str) -> AIResult:
    """Разбирает ответ AI по контракту. Бросает AIContractError при нарушении строгой части."""
    if not isinstance(data, dict):
        raise AIContractError("response must be a JSON object")
    try:
        raw = _RawResponse.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(_format_errors(exc)) from exc

    warnings: list[str] = []
    if raw.request_id != expected_request_id:
        warnings.append("request_id missing or mismatched, replaced")
    model = raw.model or _ModelInfo()
    if raw.model is None:
        warnings.append("model info missing")

    reasons = tuple(
        Reason(r.code or f"reason_{i + 1}", r.label, r.weight) for i, r in enumerate(raw.reasons)
    )
    return AIResult(
        request_id=expected_request_id,
        model_name=model.name,
        model_version=model.version,
        recommendation=raw.recommendation,
        confidence=raw.confidence,
        ranked_options=_normalize_options(
            raw.ranked_options, raw.recommendation, raw.confidence, warnings
        ),
        reasons=reasons,
        warnings=tuple(warnings),
    )
