"""AI-сервис: HTTP-обёртка над кодом AI-команды для backend (SPEC §6).

Промт, шаблоны БФТ и проверка ответа — из репозитория AI-команды без изменений
(analysis.py, bft_templates.py, bft_templates.json; источник — user_description @ 7017ae2).
Вызов модели повторяет их test_of_models.ask().

POST /ai/v1/analyze: запрос backend (AIRequest) → ответ модели в формате analysis.py
(recommendation, options_order, specialists, research_types, reasons) + request_id, model,
warnings (замечания их validate()). Приводит ответ к своему виду backend (ai/contract.py).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from huggingface_hub import InferenceClient
from pydantic import BaseModel, Field

from analysis import build_messages, parse_json, validate

logger = logging.getLogger("ai_service")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Заданы тестами напрямую; иначе берутся из .env при каждом запросе —
# токен можно вписать в .env без перезапуска сервиса
MODEL = ""
HF_TOKEN = ""


def settings() -> tuple[str, str]:
    """(HF_TOKEN, MODEL); MODEL в .env — одна модель или несколько через запятую, берём первую."""
    if HF_TOKEN and MODEL:
        return HF_TOKEN, MODEL
    load_dotenv(ENV_PATH, override=True)
    models = [m.strip() for m in os.environ.get("MODEL", "").split(",") if m.strip()]
    return os.environ.get("HF_TOKEN", "").strip(), models[0] if models else ""


# Тип исследования backend (study_type + body_region) → ключ шаблона БФТ
TEMPLATE_KEYS = {
    ("xray", "chest"): "xray_chest",
    ("ct", "chest"): "ct_chest",
    ("mammography", "breast"): "mammography",
}
# Для исследований без шаблона БФТ модель получает русское название (как в справочнике backend)
STUDY_LABELS = {
    "xray": "Рентгенография",
    "ct": "КТ",
    "mri": "МРТ",
    "ultrasound": "УЗИ",
    "mammography": "Маммография",
}
REGION_LABELS = {
    "chest": "органы грудной клетки",
    "head": "головной мозг",
    "spine": "позвоночник",
    "abdomen": "органы брюшной полости",
    "kidneys": "почки",
    "neck": "щитовидная железа",
    "knee": "коленный сустав",
    "breast": "молочные железы",
}


class PatientContext(BaseModel):
    age: int | None = None
    sex: str | None = None


class AnalyzeIn(BaseModel):
    """Запрос backend — app/ai/contract.py AIRequest."""

    request_id: str
    study_id: str | None = None
    study_type: str
    body_region: str
    report_text: str = Field(min_length=1)
    patient_context: PatientContext = Field(default_factory=PatientContext)


def study_type_for_model(study_type: str, body_region: str) -> str:
    """Ключ шаблона БФТ или «КТ, почки» — analysis.build_messages сам найдёт шаблон."""
    key = TEMPLATE_KEYS.get((study_type, body_region))
    if key:
        return key
    region = REGION_LABELS.get(body_region, body_region)
    return f"{STUDY_LABELS.get(study_type, study_type)}, {region}"


def ask(messages: list[dict[str, str]]) -> str:
    """Как test_of_models.ask(): те же параметры генерации."""
    token, model = settings()
    client = InferenceClient(token=token)
    resp = client.chat_completion(
        model=model,
        messages=messages,
        max_tokens=4096,  # рассуждающим MoE-моделям нужен запас
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""  # при нехватке токенов content бывает None


# Частые ответы Hugging Face — коротко и по-русски, чтобы врач понял причину
HF_STATUS = {
    401: "неверный токен Hugging Face (HF_TOKEN)",
    402: "закончились кредиты Hugging Face — нужен другой токен или оплата",
    404: "модель не найдена (MODEL)",
    429: "слишком много запросов к Hugging Face, лимит",
}


def short_error(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in HF_STATUS:
        return f"{HF_STATUS[status]} (HTTP {status})"
    return f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:200]}"


app = FastAPI(title="Triage AI service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    token, model = settings()
    return {"status": "ok", "model": model or None, "hf_token": bool(token)}


@app.post("/ai/v1/analyze")
def analyze(body: AnalyzeIn) -> dict[str, Any]:
    # def, не async: FastAPI выполнит блокирующий вызов модели в пуле потоков
    token, model = settings()
    if not token or not model:
        raise HTTPException(
            503, "AI-сервис не настроен: укажите HF_TOKEN и MODEL в ai_service/.env"
        )
    messages = build_messages(
        study_type_for_model(body.study_type, body.body_region),
        body.report_text,
        body.patient_context.model_dump(),
    )
    start = time.monotonic()
    try:
        raw = ask(messages)
    except Exception as exc:  # сеть, лимиты HF, ошибка модели — backend покажет «AI не отвечает»
        logger.exception("model call failed: request_id=%s", body.request_id)
        raise HTTPException(502, f"Модель недоступна: {short_error(exc)}") from exc
    sec = round(time.monotonic() - start, 1)

    parsed = parse_json(raw)
    if parsed is None:
        logger.warning("not JSON from model: request_id=%s raw=%r", body.request_id, raw[:500])
        raise HTTPException(502, "Модель вернула ответ не в формате JSON")
    errors = validate(parsed)
    logger.info("request_id=%s %ss errors=%s", body.request_id, sec, errors)
    return {
        **parsed,
        "request_id": body.request_id,
        "model": {"name": model, "version": "hf-inference"},
        "warnings": errors,  # их validate(): backend принимает мягко и сохраняет как warnings
    }
