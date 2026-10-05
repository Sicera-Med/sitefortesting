# AI-сервис: HTTP-обёртка над моделью AI-команды (порт 8001)
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Сначала только зависимости — для кэша слоёв
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Код AI-команды (промпт, шаблоны БФТ, справочник КР, B2C) и обёртка
COPY *.py *.json ./
COPY guidelines ./guidelines

RUN useradd --create-home appuser
USER appuser

EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
