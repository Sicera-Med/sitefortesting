from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.seed import DEMO_PASSWORD, seed_demo
from app.store import Store

logger = logging.getLogger(__name__)


def _build_cors_kwargs(settings: Settings) -> dict:
    """Собираем kwargs для CORSMiddleware с валидацией несовместимых опций."""
    origins = list(settings.CORS_ORIGINS)
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS

    if "*" in origins and allow_credentials:
        # Спецификация CORS запрещает `*` вместе с credentials.
        # Либо явный список origin'ов, либо отключаем credentials.
        raise RuntimeError(
            "CORS misconfiguration: allow_origins=['*'] нельзя использовать "
            "вместе с allow_credentials=True. Укажите явный список origin'ов "
            "или задайте CORS_ALLOW_CREDENTIALS=false."
        )

    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "Accept", REQUEST_ID_HEADER],
        "expose_headers": [REQUEST_ID_HEADER],
    }


def build_store(settings: Settings) -> Store:
    store = Store()
    if settings.SEED_ON_START:
        seed_demo(store, tz=settings.CLINIC_TZ)
        logger.info(
            "Demo data seeded: users=%d studies=%d; password for all demo accounts: %s",
            len(store.users),
            len(store.studies),
            DEMO_PASSWORD,
        )
    return store


def _docs_urls(settings: Settings) -> dict:
    """В проде выключаем docs/openapi; в dev — включаем."""
    enabled = settings.ENABLE_DOCS
    return {
        "docs_url": "/docs" if enabled else None,
        "redoc_url": "/redoc" if enabled else None,
        "openapi_url": "/openapi.json" if enabled else None,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.store = build_store(settings)
    # app.state.ai = build_ai_provider(settings)  — этап AI
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        **_docs_urls(settings),
    )

    app.add_middleware(CORSMiddleware, **_build_cors_kwargs(settings))
    # Добавлен последним => внешний: request_id есть и у CORS-preflight ответов.
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    # Корневой liveness-probe для Docker/K8s (не зависит от API_PREFIX).
    @app.get("/health", tags=["system"], include_in_schema=False)
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.API_PREFIX)

    return app


# Точка входа для ASGI (uvicorn app.main:app).
# Вынесена сюда, но именно как единственный сайд-эффект на import-уровне —
# сама конфигурация (логирование, CORS-валидация) выполняется в create_app().
app = create_app()
