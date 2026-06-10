#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r services/api/requirements.txt

if command -v npm >/dev/null 2>&1; then
  npm install --workspaces=false
  (cd apps/mobile && npm install)
fi

echo "Setup complete."

