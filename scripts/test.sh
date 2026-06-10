#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi

if ! .venv/bin/python -c "import fastapi, pytest" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r services/api/requirements.txt
fi

PYTHONPATH=services/api .venv/bin/python -m pytest services/api/tests
node --test apps/mobile/tests/*.test.mjs

echo "All tests passed."
