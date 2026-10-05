#!/usr/bin/env bash
# Запуск без Docker (для разработки): ai_service :8001, backend :8000, сайт :3000.
# Нужны uv (https://docs.astral.sh/uv/) и Node.js 20+. Остановка — Ctrl+C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

(cd "$ROOT/ai_service" && uv sync -q && uv run uvicorn main:app --port 8001) &
(cd "$ROOT/backend" && uv sync -q && uv run uvicorn app.main:app --port 8000 --reload) &
(cd "$ROOT/frontend" && npm install --silent && npm run dev) &

trap 'kill 0' INT TERM EXIT
echo "Сайт: http://localhost:3000   API: http://localhost:8000/docs"
wait
