# Triage Backend

Backend для платформы тестирования AI-триажа медицинских заключений.

## Запуск

```bash
cd backend
cp .env.example .env
uv sync                       # ставит и dev-зависимости (группа dev)
uv run uvicorn app.main:app --reload
```

Или в Docker:

```bash
cd backend
docker compose up --build
```

- Swagger: http://localhost:8000/docs
- Health:  http://localhost:8000/api/v1/health

## Тесты и линтер

```bash
cd backend
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Слои

```
api/v1   → HTTP, валидация
services → бизнес-логика (появится)
repos    → доступ к данным (появится, memory → sql)
domain   → чистые сущности (появится)
ai       → AIProvider (mock → http, отдельный репо)
```
