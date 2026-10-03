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
    AI_PROVIDER: Literal["mock", "http"] = "mock"
    AI_BASE_URL: str = "http://localhost:8001"
    AI_TIMEOUT_S: int = Field(default=30, gt=0)
    AI_MOCK_LATENCY_MS: int = Field(default=0, ge=0)  # имитация «думающей» модели на демо
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
