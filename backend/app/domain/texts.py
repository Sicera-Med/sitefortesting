"""Тексты, которые видит пациент."""

from typing import Any

from app.domain.dictionaries import RESEARCH_TYPES, SPECIALISTS
from app.domain.enums import RecommendationType

_GREETING = "Здравствуйте! По результатам вашего исследования врач рекомендует"


def notification_text(chosen: tuple[RecommendationType, ...], details: dict[str, Any]) -> str:
    parts: list[str] = []
    if RecommendationType.REPEAT_APPOINTMENT in chosen:
        parts.append("повторный приём")
    if RecommendationType.SPECIALIST_CONSULT in chosen:
        who = ", ".join(SPECIALISTS.get(s, s) for s in details.get("specialists", []))
        parts.append(f"консультацию: {who or 'специалиста'}")
    if RecommendationType.ADDITIONAL_RESEARCH in chosen:
        what = ", ".join(RESEARCH_TYPES.get(r, r) for r in details.get("research_types", []))
        parts.append(f"обследование: {what or 'по назначению врача'}")
    return f"{_GREETING} {'; '.join(parts)}. Запишитесь, пожалуйста, на удобное время."
