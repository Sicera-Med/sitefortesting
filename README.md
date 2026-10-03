# Triage Backend

Backend для платформы тестирования AI-триажа медицинских заключений.

## Запуск

```bash
cp .env.example .env
uv sync --extra dev           # или: pip install -e ".[dev]"
uv run uvicorn app.main:app --reload
```

- Swagger: http://localhost:8000/docs
- Health:  http://localhost:8000/api/v1/health

## Тесты

```bash
uv run pytest
```

## Слои

```
api/v1   → HTTP, валидация
services → бизнес-логика (появится)
repos    → доступ к данным (появится, memory → sql)
domain   → чистые сущности (появится)
ai       → AIProvider (mock → http, отдельный репо)
```