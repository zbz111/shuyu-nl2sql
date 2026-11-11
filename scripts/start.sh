#!/usr/bin/env bash
# 一键启动（Linux / macOS）
set -e
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
  pip install -r requirements.txt
fi

[ -f .env ] || cp .env.example .env

exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
