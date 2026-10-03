import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.context import request_id_ctx
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import JsonFormatter
from app.main import create_app


@pytest.fixture
def app_with_errors():
    app = create_app()

    @app.get("/_boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    @app.get("/_forbidden")
    async def forbidden():
        raise ForbiddenError("Not your study", details={"study_id": "st_1"})

    @app.get("/_unauthorized")
    async def unauthorized():
        raise UnauthorizedError("Missing token")

    @app.get("/_typed/{n}")
    async def typed(n: int):
        return {"n": n}

    return app


def test_unknown_path_uses_error_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_domain_error(app_with_errors):
    with TestClient(app_with_errors) as c:
        r = c.get("/_forbidden")
    assert r.status_code == 403
    assert r.json()["error"] == {
        "code": "forbidden",
        "message": "Not your study",
        "details": {"study_id": "st_1"},
    }


def test_unauthorized_has_www_authenticate(app_with_errors):
    with TestClient(app_with_errors) as c:
        r = c.get("/_unauthorized")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_validation_error_envelope(app_with_errors):
    with TestClient(app_with_errors) as c:
        r = c.get("/_typed/abc")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]["errors"][0]["loc"] == ["path", "n"]


def test_unhandled_error_hides_details(app_with_errors):
    with TestClient(app_with_errors, raise_server_exceptions=False) as c:
        r = c.get("/_boom", headers={"X-Request-ID": "req-500"})
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret" not in r.text
    assert r.headers["x-request-id"] == "req-500"


def test_request_id_generated_and_echoed(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-request-id"]

    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


def test_request_id_rejects_unsafe_value(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad value\twith junk"})
    assert r.headers["x-request-id"] != "bad value\twith junk"


def test_json_formatter_fields():
    record = logging.makeLogRecord(
        {"name": "t", "levelname": "INFO", "msg": "hello %s", "args": ("world",)}
    )
    token = request_id_ctx.set("req-1")
    try:
        out = json.loads(JsonFormatter().format(record))
    finally:
        request_id_ctx.reset(token)
    assert out["msg"] == "hello world"
    assert out["request_id"] == "req-1"
    assert {"ts", "level", "logger"} <= out.keys()


def test_json_formatter_survives_bad_format_args():
    record = logging.makeLogRecord({"msg": "%d", "args": ("not-int",)})
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "%d"
    assert "msg_format_error" in out


def test_prod_requires_explicit_jwt_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_docs_disabled_in_prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AI_PROVIDER", "http")
    assert Settings(_env_file=None).ENABLE_DOCS is False


def test_mock_ai_only_in_tests(monkeypatch):
    import pytest
    from pydantic import ValidationError

    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_wildcard_with_credentials_rejected(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        create_app()
