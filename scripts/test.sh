#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi

if ! .venv/bin/python -c "import fastapi, pytest" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r backend/requirements.txt
fi

PYTHONPATH=backend .venv/bin/python -m pytest backend/tests

echo "All tests passed."
