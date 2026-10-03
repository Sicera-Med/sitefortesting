"""Тексты, которые видит пациент."""

from typing import Any

from app.domain.dictionaries import RESEARCH_TYPES, SPECIALISTS
from app.domain.enums import RecommendationType

_GREETING = "Здравствуйте! По результатам вашего исследования врач рекомендует"


def notification_text(chosen_type: RecommendationType, details: dict[str, Any]) -> str:
    match chosen_type:
        case RecommendationType.REPEAT_APPOINTMENT:
            days = details.get("interval_days")
            when = f" через {days} дн." if days else ""
            return f"{_GREETING} повторный приём{when} Запишитесь, пожалуйста, на удобное время."
        case RecommendationType.SPECIALIST_CONSULT:
            who = SPECIALISTS.get(details.get("specialist", ""), "специалиста")
            return f"{_GREETING} консультацию: {who}. Запишитесь, пожалуйста, на приём."
        case RecommendationType.ADDITIONAL_RESEARCH:
            what = RESEARCH_TYPES.get(details.get("research_type", ""), "дополнительное")
            return f"{_GREETING} дополнительное исследование: {what}. Запишитесь, пожалуйста."
