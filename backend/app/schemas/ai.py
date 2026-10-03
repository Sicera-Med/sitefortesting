from __future__ import annotations

from pydantic import BaseModel, Field

from app.ai.contract import AIResult, PatientContext
from app.domain.enums import StudyType
from app.schemas.studies import RankedOptionOut, ReasonOut


class AITestIn(BaseModel):
    report_text: str = Field(min_length=1, max_length=20_000)
    study_type: StudyType
    body_region: str
    patient_context: PatientContext = Field(default_factory=PatientContext)


class AIResultOut(BaseModel):
    request_id: str
    model_name: str
    model_version: str
    recommendation: str
    confidence: float
    ranked_options: list[RankedOptionOut]
    reasons: list[ReasonOut]
    warnings: list[str]

    @classmethod
    def build(cls, r: AIResult) -> AIResultOut:
        return cls(
            request_id=r.request_id,
            model_name=r.model_name,
            model_version=r.model_version,
            recommendation=str(r.recommendation),
            confidence=r.confidence,
            ranked_options=[RankedOptionOut(type=o.type, score=o.score) for o in r.ranked_options],
            reasons=[ReasonOut(code=x.code, label=x.label, weight=x.weight) for x in r.reasons],
            warnings=list(r.warnings),
        )


class AITestOut(BaseModel):
    provider: str
    latency_ms: int
    result: AIResultOut
    raw_contract: dict  # нормализованный ответ в формате §6.2 — удобно AI-команде


class AIModelOut(BaseModel):
    name: str
    version: str
    source: str
