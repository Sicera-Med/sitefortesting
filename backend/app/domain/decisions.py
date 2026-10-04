"""Валидация details решения врача (SPEC §5.5)."""

from typing import Any

from app.domain.dictionaries import RESEARCH_TYPES, SPECIALISTS
from app.domain.enums import RecommendationType


def _codes(details: dict[str, Any], key: str, legacy: str) -> Any:
    """Список кодов; старый формат — одно значение под ключом legacy."""
    value = details.get(key)
    if value is None and legacy in details:
        value = [details[legacy]]
    return value


# Исходы, которые не сочетаются с другими направлениями
EXCLUSIVE_TYPES = (RecommendationType.NO_PATHOLOGY, RecommendationType.URGENT_HOSPITALIZATION)


def normalize_chosen(raw: Any) -> tuple[RecommendationType, ...]:
    """Выбранные врачом варианты без повторов, в порядке справочника.

    Направлений — от одного до трёх; «патологии не выявлено» и «экстренная госпитализация» —
    только отдельно.
    """
    if not isinstance(raw, list | tuple) or not raw:
        raise ValueError("chosen_types must be a non-empty list")
    chosen = {RecommendationType(t) for t in raw}
    for single in EXCLUSIVE_TYPES:
        if single in chosen and len(chosen) > 1:
            raise ValueError(f"{single} cannot be combined with other options")
    return tuple(t for t in RecommendationType if t in chosen)


def normalize_details(
    chosen: tuple[RecommendationType, ...], details: dict[str, Any]
) -> dict[str, Any]:
    """Возвращает очищенные details (только для выбранных вариантов) или бросает ValueError.

    Повторный приём деталей не требует — дату выбирает пациент.
    """
    clean: dict[str, Any] = {}
    if RecommendationType.SPECIALIST_CONSULT in chosen:
        items = _codes(details, "specialists", "specialist")
        if not isinstance(items, list) or not items:
            raise ValueError("specialists must be a non-empty list")
        if any(s not in SPECIALISTS for s in items):
            raise ValueError(f"specialists must be from: {', '.join(SPECIALISTS)}")
        clean["specialists"] = list(dict.fromkeys(items))
    if RecommendationType.ADDITIONAL_RESEARCH in chosen:
        items = _codes(details, "research_types", "research_type")
        if not isinstance(items, list) or not items:
            raise ValueError("research_types must be a non-empty list")
        if any(r not in RESEARCH_TYPES for r in items):
            raise ValueError(f"research_types must be from: {', '.join(RESEARCH_TYPES)}")
        clean["research_types"] = list(dict.fromkeys(items))
    return clean


def normalize_ai_details(
    recommendation: RecommendationType, raw: Any, warnings: list[str]
) -> dict[str, Any]:
    """Детали из ответа AI (§6.3, мягко): неизвестное отбрасываем и пишем warning."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        warnings.append("details: not an object, ignored")
        return {}
    match recommendation:
        case RecommendationType.SPECIALIST_CONSULT:
            items = _codes(raw, "specialists", "specialist")
            if not isinstance(items, list):
                if items is not None:
                    warnings.append("details.specialists: not a list, ignored")
                return {}
            known = [x for x in items if x in SPECIALISTS]
            for x in items:
                if x not in SPECIALISTS:
                    warnings.append(f"details.specialists: unknown code {x!r} ignored")
            return {"specialists": list(dict.fromkeys(known))} if known else {}
        case RecommendationType.ADDITIONAL_RESEARCH:
            items = _codes(raw, "research_types", "research_type")
            if not isinstance(items, list):
                if items is not None:
                    warnings.append("details.research_types: not a list, ignored")
                return {}
            known = [r for r in items if r in RESEARCH_TYPES]
            for r in items:
                if r not in RESEARCH_TYPES:
                    warnings.append(f"details.research_types: unknown code {r!r} ignored")
            return {"research_types": list(dict.fromkeys(known))} if known else {}
    return {}
