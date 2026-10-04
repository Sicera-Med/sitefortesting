from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Переменные окружения имеют приоритет над .env — тесты не зависят от локального .env
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    # Детерминированные ответы AI (фикстуры) — только в тестах; воркер запускаем вручную
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_AUTO_ANALYZE", "false")
    # Ограничение частоты ручной отправки проверяется отдельным тестом
    monkeypatch.setenv("AI_SEND_COOLDOWN_S", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:  # with — чтобы отработал lifespan
        yield c


def analyze_all(client: TestClient) -> int:
    """Прогон автоанализа (в приложении его делает фоновый воркер)."""
    return client.portal.call(client.app.state.analyzer.run_once)


def login(client: TestClient, email: str, password: str = "demo") -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def petrov(client: TestClient) -> dict[str, str]:
    return login(client, "petrov@clinic.demo")


@pytest.fixture
def sidorova(client: TestClient) -> dict[str, str]:
    return login(client, "sidorova@clinic.demo")


@pytest.fixture
def chief(client: TestClient) -> dict[str, str]:
    return login(client, "chief@clinic.demo")


@pytest.fixture
def manager(client: TestClient) -> dict[str, str]:
    return login(client, "manager@clinic.demo")


@pytest.fixture
def kuznetsova(client: TestClient) -> dict[str, str]:
    return login(client, "kuznetsova@patient.demo")
