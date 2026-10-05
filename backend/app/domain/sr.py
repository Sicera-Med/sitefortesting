"""Протокол исследования — раздел «Описание» DICOM SR по шаблону БФТ (как на thirdopinion.ai).

Строки «Поле- значение» хранятся как есть; для AI собираются в текст в формате AI-команды
(`report_text(t)` в их test_of_models.py): «Описание: …». Заключение рентгенолога не берём.
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
    """«Поле- значение» → (поле, значение) по ПЕРВОМУ разделителю.

    Первый — потому что в значениях бывают и тире, и двоеточия: «Грудная аорта- диаметр: 40 мм».
    Дефис без пробела после («S9-S10», «КТ-признаки») разделителем не считается.
    """
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


def parse_sr(text: str) -> list[SRField]:
    """Текст протокола → поля описания («Поле- значение»).

    Вставляют его из PACS или с сайта заказчика как есть, поэтому разбор терпимый:
    маркеры списков и заголовок «Описание» пропускаются; строка без разделителя — продолжение
    предыдущего значения (перенос строки). Заключение рентгенолога в систему не берём (решение
    v2.15): всё начиная со строки «Заключение» отбрасывается. Значения не меняются — модель
    видит цифры и формулировки рентгенолога дословно.
    """
    fields: list[SRField] = []
    for raw in text.splitlines():
        line = _BULLET.sub("", raw.strip())
        if not line or line.rstrip(":").lower() == "описание":
            continue
        if _CONCLUSION.match(line):
            break
        pair = _split(line)
        if pair:
            fields.append(SRField(*pair))
        elif fields:
            last = fields[-1]
            fields[-1] = SRField(last.name, f"{last.value} {line}")
        else:
            fields.append(SRField("Описание", line))
    return fields


def report_text(fields: tuple[SRField, ...] | list[SRField]) -> str:
    """Протокол для AI — как report_text(t) у AI-команды: «Описание: Поле: значение. …»."""
    if not fields:
        return ""
    return "Описание: " + " ".join(f"{f.name}: {f.value.rstrip('.;')}." for f in fields)
