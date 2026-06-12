#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r backend/requirements.txt
fi

.venv/bin/uvicorn main:app --app-dir backend --host 0.0.0.0 --port 3000 --reload
