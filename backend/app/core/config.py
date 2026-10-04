from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "dev-secret-change-me-in-prod-0123456789"  # ≥ 32 байт для HS256


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",  # явная кодировка
        extra="ignore",
        case_sensitive=False,  # APP_ENV и app_env равнозначны
    )

    # --- App ---
    APP_NAME: str = "triage-backend"
    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # None — вычисляется из APP_ENV: docs включены везде, кроме prod
    ENABLE_DOCS: bool | None = None

    # --- HTTP ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    # --- CORS ---
    # ВАЖНО: при allow_credentials=True origins должны быть явными
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    CORS_ALLOW_CREDENTIALS: bool = True

    # --- Security ---
    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_TTL_MIN: int = Field(default=60, gt=0)

    # --- AI ---
    # Ответы AI — только от сервиса коллег. mock (фикстуры) разрешён лишь в тестах
    AI_PROVIDER: Literal["mock", "http"] = "http"
    AI_BASE_URL: str = "http://localhost:8001"
    # Модель коллег (LLM через Hugging Face) отвечает ~30–60 с
    AI_TIMEOUT_S: int = Field(default=120, gt=0)
    AI_MOCK_LATENCY_MS: int = Field(default=0, ge=0)  # только для тестов
    # Автоанализ: новые исследования уходят в AI сами; при сбое — повтор через AI_RETRY_S
    # Пока выключено (решение пользователя): в AI отправляет врач кнопкой
    AI_AUTO_ANALYZE: bool = False
    AI_POLL_S: float = Field(default=3, gt=0)
    AI_RETRY_S: float = Field(default=8 * 3600, gt=0)  # повтор после сбоя — через 8 часов
    AI_MAX_AUTO_ATTEMPTS: int = Field(default=3, ge=1)  # потом — только ручная отправка
    # Ручная отправка одного исследования — не чаще раза в AI_SEND_COOLDOWN_S (бережём кредиты)
    AI_SEND_COOLDOWN_S: float = Field(default=10, ge=0)
    # Напоминания пациенту (раз в неделю, до 3 раз) — фоновый воркер; в тестах выключен
    NOTIFY_REMINDERS: bool = True
    # Адрес сайта для ссылок в SMS / email / соцсетях (на сцене — доступный с телефона)
    SITE_URL: str = "http://localhost:3000"
    # Настоящие рассылки (services/channels.py). false — всё имитируется, как раньше
    NOTIFY_REAL: bool = False
    NOTIFY_SMS: bool = True  # при NOTIFY_REAL: SMS через SMSPilot
    NOTIFY_EMAIL: bool = True  # при NOTIFY_REAL: email через SMTP
    NOTIFY_OUTBOX: bool = True  # фоновая очередь отправки; в тестах выключена
    NOTIFY_OUTBOX_POLL_S: float = Field(default=2, gt=0)  # очередь отправки
    NOTIFY_REMIND_COOLDOWN_S: float = Field(default=10, ge=0)  # «Напомнить сейчас»
    SMSPILOT_API_KEY: str = ""
    SMSPILOT_FROM: str = ""  # имя отправителя; пусто — по умолчанию SMSPilot
    SMTP_HOST: str = "smtp.yandex.ru"
    SMTP_PORT: int = 465  # SSL
    SMTP_USER: str = ""  # ящик Яндекса, он же отправитель
    SMTP_PASSWORD: str = ""  # пароль приложения Яндекса
    # Демо: контакты всех пациентов seed (уведомления придут одному человеку)
    DEMO_CONTACT_PHONE: str = ""
    DEMO_CONTACT_EMAIL: str = ""
    AI_HIGH_CONFIDENCE: float = Field(default=0.7, ge=0, le=1)

    # --- Клиника ---
    CLINIC_TZ: str = "Europe/Moscow"  # слоты записи считаются в этом поясе

    # --- Storage ---
    STORAGE: Literal["memory", "sql"] = "memory"

    # --- Seed ---
    SEED_ON_START: bool = True

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.ENABLE_DOCS is None:
            self.ENABLE_DOCS = self.APP_ENV != "prod"
        if self.APP_ENV == "prod" and self.JWT_SECRET == _DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set explicitly in prod")
        if self.AI_PROVIDER == "mock" and self.APP_ENV != "test":
            raise ValueError(
                "AI_PROVIDER=mock — только для тестов: ответы AI не подделываем. "
                "Укажите AI_PROVIDER=http и AI_BASE_URL сервиса"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
