"""Тексты, которые видит пациент.

Два уровня (позже их заменит B2C-часть AI коллег, `test_of_b2c.py`):
- на сайте — подробный текст: что решил врач и что делать по каждому направлению;
- в SMS / email / соцсети — коротко, без медицинских подробностей, со ссылкой на сайт.
"""

from datetime import date
from typing import Any

from app.domain.dictionaries import BODY_REGIONS, RESEARCH_TYPES, SPECIALISTS, STUDY_TYPES
from app.domain.enums import RecommendationType

SOCIAL_LABELS = {"telegram": "Telegram", "vk": "VK", "whatsapp": "WhatsApp", "max": "MAX"}

R = RecommendationType


def study_title(study_type: str, body_region: str) -> str:
    """«КТ, органы грудной клетки» — как в кабинете пациента."""
    region = BODY_REGIONS.get(body_region, body_region)
    return f"{STUDY_TYPES.get(study_type, study_type)}, {region[:1].lower()}{region[1:]}"


def _greeting(patient_name: str) -> str:
    # «Иванов Сергей Петрович» → «Сергей Петрович»
    parts = patient_name.split()
    return f"Здравствуйте, {' '.join(parts[1:]) or patient_name}!"


def notification_text(
    chosen: tuple[RecommendationType, ...],
    details: dict[str, Any],
    *,
    patient_name: str,
    doctor_name: str,
    study: str,
    performed: date,
) -> str:
    """Подробный текст для сайта: итог и что сделать по каждому направлению."""
    head = (
        f"{_greeting(patient_name)}\n"
        f"Ваш лечащий врач {doctor_name} изучил результат исследования «{study}» "
        f"от {performed:%d.%m.%Y}."
    )
    if R.URGENT_HOSPITALIZATION in chosen:
        return (
            f"{head}\n"
            "Врач рекомендует ЭКСТРЕННУЮ ГОСПИТАЛИЗАЦИЮ. Пожалуйста, как можно скорее обратитесь "
            "в приёмное отделение стационара. При ухудшении самочувствия звоните 103 или 112.\n"
            "Возьмите с собой паспорт, полис ОМС и результаты исследования."
        )
    if R.NO_PATHOLOGY in chosen:
        return (
            f"{head}\n"
            "Патологии не выявлено — изменений, требующих лечения или наблюдения, нет. "
            "Записываться на приём не нужно.\n"
            "Если появятся жалобы, обратитесь к лечащему врачу."
        )
    steps: list[str] = []
    if R.REPEAT_APPOINTMENT in chosen:
        steps.append(
            f"• Повторный приём у лечащего врача — выберите удобное время у врача {doctor_name}."
        )
    if R.SPECIALIST_CONSULT in chosen:
        who = ", ".join(SPECIALISTS.get(s, s) for s in details.get("specialists", []))
        steps.append(
            f"• Консультация специалиста: {who or 'по назначению врача'} — "
            "запишитесь к каждому специалисту."
        )
    if R.ADDITIONAL_RESEARCH in chosen:
        what = ", ".join(RESEARCH_TYPES.get(r, r) for r in details.get("research_types", []))
        steps.append(
            f"• Дополнительное обследование: {what or 'по назначению врача'} — "
            "запишитесь на каждое исследование."
        )
    return (
        f"{head} Врач рекомендует:\n"
        + "\n".join(steps)
        + "\nЗапишитесь по каждому направлению ниже. Если появятся вопросы, "
        "обратитесь к лечащему врачу."
    )


def short_text(patient_name: str, study: str, url: str, *, urgent: bool = False) -> str:
    """SMS / email / соцсеть: только факт готовности и ссылка, без медицинских данных."""
    if urgent:
        return (
            f"{_greeting(patient_name)} СРОЧНО: по результату исследования «{study}» врач "
            f"рекомендует экстренную госпитализацию. Подробнее: {url}. При ухудшении — 103."
        )
    return (
        f"{_greeting(patient_name)} Готов результат исследования «{study}» "
        f"и рекомендации врача: {url}"
    )


def sms_text(url: str, *, urgent: bool = False) -> str:
    """SMS — короче всего: кириллица идёт сегментами по 70 знаков, без имени и деталей."""
    if urgent:
        return f"Третье мнение: СРОЧНО — врач рекомендует госпитализацию. {url} При ухудшении — 103"
    return f"Третье мнение: готов результат исследования и рекомендации врача: {url}"


def sms_reminder_text(url: str) -> str:
    return f"Третье мнение: напоминаем записаться по рекомендациям врача: {url}"


def reminder_text(patient_name: str, study: str, url: str) -> str:
    """Напоминание (раз в неделю, пока пациент не записался) — тоже коротко, со ссылкой."""
    return (
        f"{_greeting(patient_name)} Напоминаем: по исследованию «{study}» врач дал "
        f"рекомендации, а запись ещё не завершена. Записаться: {url}"
    )
