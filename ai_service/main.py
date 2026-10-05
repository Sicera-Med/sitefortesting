"""AI-сервис: HTTP-обёртка над кодом AI-команды для backend (SPEC §6).

Код AI-команды — из их репозитория (user_description @ origin/main 109ce05), без изменений,
кроме помеченной правки no_pathology в analysis.py:
- analysis.py — промт, шаблон БФТ + справочник «находка → действие», проверка, источники;
- guidelines.py, guidelines/*.json — справочник из клинических рекомендаций;
- bft_templates.py/.json — шаблоны протоколов БФТ;
- b2c.py (= их test_of_b2c.py) — объяснение заключения пациенту.

POST /ai/v1/analyze — как их test_of_models.ask(): справочник по словам протокола, а если модель
просит (need_full_guidelines) — второй запрос с полным справочником; затем validate() и
attach_sources(). Ответ — их JSON (options, reasons) + request_id, model, warnings,
guidelines_mode; к source_refs дописываем url официальной страницы документа.
POST /ai/v1/explain — B2C: summary + explanations для пациента.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from huggingface_hub import InferenceClient
from pydantic import BaseModel, Field

from analysis import attach_sources, build_messages, guidelines_partial, parse_json, validate
from guidelines import SOURCES

# b2c.py (их test_of_b2c.py) при импорте читает HF_TOKEN и MODEL — без .env нужны значения
os.environ.setdefault("HF_TOKEN", "")
os.environ.setdefault("MODEL", "")
from b2c import build_input, system_prompt_for, validate_b2c_response

logger = logging.getLogger("ai_service")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Настройки — config/ai_service.env в корне репозитория; ai_service/.env, если есть, — поверх.
# В Docker переменные задаёт docker-compose
ENV_PATHS = (
    os.path.join(BASE_DIR, "..", "config", "ai_service.env"),
    os.path.join(BASE_DIR, ".env"),
)

# Адреса официальных страниц документов справочника (doc → url) — наша доработка их данных
with open(os.path.join(BASE_DIR, "source_urls.json"), encoding="utf-8") as _f:
    SOURCE_URLS: dict[str, str] = json.load(_f)

# Заданы тестами напрямую; иначе берутся из .env при каждом запросе —
# токен можно вписать в .env без перезапуска сервиса
MODEL = ""
HF_TOKEN = ""


def settings() -> tuple[str, str]:
    """(HF_TOKEN, MODEL); MODEL в .env — одна модель или несколько через запятую, берём первую.

    HF_TOKEN — один токен или несколько через запятую: см. hf_tokens() и ask()."""
    if HF_TOKEN and MODEL:
        return HF_TOKEN, MODEL
    for path in ENV_PATHS:
        load_dotenv(path, override=True)
    models = [m.strip() for m in os.environ.get("MODEL", "").split(",") if m.strip()]
    return os.environ.get("HF_TOKEN", "").strip(), models[0] if models else ""


# Тип исследования backend (study_type + body_region) → ключ шаблона БФТ / справочника
TEMPLATE_KEYS = {
    ("xray", "chest"): "xray_chest",
    ("ct", "chest"): "ct_chest",
    ("mammography", "breast"): "mammography",
    ("ct", "head"): "КТ ГМ",  # шаблона БФТ нет, справочник — по синониму
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

# Частые ответы Hugging Face — коротко и по-русски, чтобы врач понял причину
HF_STATUS = {
    401: "неверный токен Hugging Face (HF_TOKEN)",
    402: "закончились кредиты Hugging Face — нужен другой токен или оплата",
    404: "модель не найдена (MODEL)",
    429: "слишком много запросов к Hugging Face, лимит",
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


class ExplainIn(BaseModel):
    """B2C: протокол для объяснения пациенту — описание и заключение раздельно."""

    request_id: str
    study_type: str
    body_region: str
    description: str | None = None
    conclusion: str | None = None


def study_type_for_model(study_type: str, body_region: str) -> str:
    """Ключ шаблона БФТ / справочника или «КТ, почки» — analysis.py сам найдёт шаблон."""
    key = TEMPLATE_KEYS.get((study_type, body_region))
    if key:
        return key
    region = REGION_LABELS.get(body_region, body_region)
    return f"{STUDY_LABELS.get(study_type, study_type)}, {region}"


def short_error(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in HF_STATUS:
        return f"{HF_STATUS[status]} (HTTP {status})"
    return f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:200]}"


def hf_tokens(raw: str) -> list[str]:
    """«hf_a, hf_b» → [hf_a, hf_b]: запасные токены через запятую (или пробел / перенос строки)."""
    return [t for t in re.split(r"[\s,;]+", raw) if t]


# Ответы HF, при которых пробуем следующий токен: неверный токен, кончились кредиты, лимит
ROTATE_ON = {401, 402, 403, 429}
_active_token = 0  # индекс токена, который сработал последним — с него и начинаем


def ask(messages: list[dict[str, str]]) -> str:
    """Как _call() в их test_of_models.py: те же параметры генерации.

    Токены перебираются по кругу, начиная с последнего рабочего: если HF ответил 401/402/403/429,
    берём следующий. Другие ошибки (сеть, модель) не зависят от токена — сразу наверх.
    """
    global _active_token
    raw, model = settings()
    tokens = hf_tokens(raw)
    start = _active_token % len(tokens) if tokens else 0
    last_exc: Exception | None = None
    for i in [*range(start, len(tokens)), *range(start)]:
        try:
            resp = InferenceClient(token=tokens[i]).chat_completion(
                model=model,
                messages=messages,
                max_tokens=4096,  # рассуждающим MoE-моделям нужен запас
                temperature=0.2,
            )
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in ROTATE_ON:
                raise
            logger.warning("HF token #%d of %d: %s — пробуем следующий", i + 1, len(tokens), status)
            last_exc = exc
            continue
        _active_token = i
        return resp.choices[0].message.content or ""  # при нехватке токенов content бывает None
    raise last_exc or RuntimeError("HF_TOKEN не задан")


def _model_call(messages: list[dict[str, str]], request_id: str) -> str:
    try:
        return ask(messages)
    except Exception as exc:  # сеть, лимиты HF, ошибка модели — backend покажет «AI не отвечает»
        logger.exception("model call failed: request_id=%s", request_id)
        raise HTTPException(502, f"Модель недоступна: {short_error(exc)}") from exc


def _require_settings() -> str:
    token, model = settings()
    if not token or not model:
        raise HTTPException(
            503, "AI-сервис не настроен: укажите HF_TOKEN и MODEL в config/ai_service.env"
        )
    return model


# source_refs несут имя файла документа — адрес ищем по нему
_URL_BY_FILE = {SOURCES[doc]["file"]: url for doc, url in SOURCE_URLS.items() if doc in SOURCES}


def source_url(ref: dict[str, Any]) -> str | None:
    """Адрес документа; PDF на официальном сайте — сразу на нужной странице (#page=)."""
    url = _URL_BY_FILE.get(ref.get("file"))
    if url and url.lower().endswith(".pdf"):
        page = re.search(r"\d+", str(ref.get("pages") or ""))
        if page:
            url += f"#page={page.group()}"
    return url


def add_urls(parsed: dict[str, Any]) -> None:
    """К ссылкам на документы (source_refs из attach_sources) — адрес официальной страницы."""
    for option in parsed.get("options") or []:
        if not isinstance(option, dict):
            continue
        for x in [option, *(option.get("items") or [])]:
            if not isinstance(x, dict):
                continue
            for ref in x.get("source_refs") or []:
                ref["url"] = source_url(ref)


app = FastAPI(title="Triage AI service", version="0.2.0")


@app.get("/health")
def health() -> dict[str, Any]:
    token, model = settings()
    return {
        "status": "ok",
        "model": model or None,
        "hf_token": bool(token),
        "hf_tokens": len(hf_tokens(token)),
    }


@app.post("/ai/v1/analyze")
def analyze(body: AnalyzeIn) -> dict[str, Any]:
    # def, не async: FastAPI выполнит блокирующие вызовы модели в пуле потоков
    model = _require_settings()
    study_type = study_type_for_model(body.study_type, body.body_region)
    context = body.patient_context.model_dump()
    start = time.monotonic()

    # Как ask() в их test_of_models.py: сначала справочник по словам протокола,
    # модель просит полный (need_full_guidelines) — второй запрос
    raw = _model_call(build_messages(study_type, body.report_text, context), body.request_id)
    mode = "весь справочник"
    if guidelines_partial(study_type, body.report_text):
        mode = "по словам протокола"
        if (parse_json(raw) or {}).get("need_full_guidelines") is True:
            messages = build_messages(study_type, body.report_text, context, full_guidelines=True)
            raw = _model_call(messages, body.request_id)
            mode = "весь справочник по запросу модели"
    sec = round(time.monotonic() - start, 1)

    parsed = parse_json(raw)
    if parsed is None:
        logger.warning("not JSON from model: request_id=%s raw=%r", body.request_id, raw[:500])
        raise HTTPException(502, "Модель вернула ответ не в формате JSON")
    errors = validate(parsed, study_type)
    parsed = attach_sources(parsed)  # документ и страницы по id из справочника
    add_urls(parsed)
    logger.info("analyze request_id=%s %ss mode=%s errors=%s", body.request_id, sec, mode, errors)
    return {
        **parsed,
        "request_id": body.request_id,
        "model": {"name": model, "version": "hf-inference"},
        "guidelines_mode": mode,
        "warnings": errors,  # их validate(): backend принимает мягко и сохраняет как warnings
    }


@app.post("/ai/v1/explain")
def explain(body: ExplainIn) -> dict[str, Any]:
    """B2C — как ask() в их test_of_b2c.py: объяснение заключения пациенту простым языком."""
    model = _require_settings()
    t = {
        "study_type": study_type_for_model(body.study_type, body.body_region),
        "description": body.description,
        "conclusion": body.conclusion,
    }
    messages = [
        {"role": "system", "content": system_prompt_for(t["study_type"])},
        {"role": "user", "content": build_input(t)},
    ]
    parsed = parse_json(_model_call(messages, body.request_id))
    if not validate_b2c_response(parsed):
        raise HTTPException(502, "Модель вернула объяснение не в нужном формате")
    return {
        "summary": parsed["summary"].strip(),
        "explanations": parsed["explanations"],
        "request_id": body.request_id,
        "model": {"name": model, "version": "hf-inference"},
    }
