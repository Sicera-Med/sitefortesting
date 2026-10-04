"""Протокол исследования — раздел «Описание» DICOM SR по шаблону БФТ (как на thirdopinion.ai).

Строки «Поле- значение» хранятся как есть; для AI собираются в текст в формате AI-команды
(`report_text(t)` в их test_of_models.py): «Описание: …\nЗаключение: …».
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.enums import StudyType

# Типы с шаблоном БФТ или справочником «находка → действие» у AI-команды
STUDY_KINDS: dict[tuple[StudyType, str], str] = {
    (StudyType.CT, "chest"): "КТ ОГК",
    (StudyType.XRAY, "chest"): "РГ/ФЛГ ОГК",
    (StudyType.MAMMOGRAPHY, "breast"): "Маммография",
    (StudyType.CT, "head"): "КТ ГМ",
}


@dataclass(frozen=True, slots=True)
class SRField:
    name: str
    value: str


# «Поле- значение» (как у заказчика), «Поле — значение» или «Поле: значение»
_DASH = re.compile(r"\s*[-—–]\s+")
_CONCLUSION = re.compile(r"^заключение\s*[:\-—–]?\s*(.*)$", re.I)
_BULLET = re.compile(r"^[•*·\-–—]\s+")


def _split(line: str) -> tuple[str, str] | None:
    dash = _DASH.search(line)
    colon = line.find(":")
    cut = [
        p
        for p in (
            (dash.start(), dash.end()) if dash else None,
            (colon, colon + 1) if colon > 0 else None,
        )
        if p
    ]
    if not cut:
        return None
    start, end = min(cut)
    name, value = line[:start].strip(), line[end:].strip()
    return (name, value) if name and value else None


def parse_sr(text: str) -> tuple[list[SRField], str | None]:
    """Текст протокола → (поля «Описание», заключение). Строка без разделителя — продолжение."""
    fields: list[SRField] = []
    conclusion: list[str] = []
    in_conclusion = False
    for raw in text.splitlines():
        line = _BULLET.sub("", raw.strip())
        if not line or line.rstrip(":").lower() == "описание":
            continue
        m = _CONCLUSION.match(line)
        if m:
            in_conclusion = True
            if m.group(1):
                conclusion.append(m.group(1))
            continue
        if in_conclusion:
            conclusion.append(line)
            continue
        pair = _split(line)
        if pair:
            fields.append(SRField(*pair))
        elif fields:
            last = fields[-1]
            fields[-1] = SRField(last.name, f"{last.value} {line}")
        else:
            fields.append(SRField("Описание", line))
    return fields, " ".join(conclusion).strip() or None


def report_text(fields: tuple[SRField, ...] | list[SRField], conclusion: str | None) -> str:
    """Протокол для AI — как report_text(t) у AI-команды."""
    parts = []
    if fields:
        items = [f"{f.name}: {f.value.rstrip('.;')}." for f in fields]
        parts.append("Описание: " + " ".join(items))
    if conclusion:
        parts.append(f"Заключение: {conclusion}")
    return "\n".join(parts)
