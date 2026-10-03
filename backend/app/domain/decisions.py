"""Валидация details решения врача (SPEC §5.5)."""

from typing import Any

from app.domain.dictionaries import RESEARCH_TYPES, SPECIALISTS
from app.domain.enums import RecommendationType


def normalize_details(chosen: RecommendationType, details: dict[str, Any]) -> dict[str, Any]:
    """Возвращает очищенные details (только нужные поля) или бросает ValueError."""
    match chosen:
        case RecommendationType.REPEAT_APPOINTMENT:
            days = details.get("interval_days")
            if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
                raise ValueError("interval_days must be an integer from 1 to 365")
            return {"interval_days": days}
        case RecommendationType.SPECIALIST_CONSULT:
            specialist = details.get("specialist")
            if specialist not in SPECIALISTS:
                raise ValueError(f"specialist must be one of: {', '.join(SPECIALISTS)}")
            return {"specialist": specialist}
        case RecommendationType.ADDITIONAL_RESEARCH:
            research = details.get("research_type")
            if research not in RESEARCH_TYPES:
                raise ValueError(f"research_type must be one of: {', '.join(RESEARCH_TYPES)}")
            return {"research_type": research}
    raise ValueError(f"unknown recommendation type: {chosen}")
