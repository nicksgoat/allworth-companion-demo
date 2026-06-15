#!/usr/bin/env bash
# Run the backend test suite via uv (Python 3.12), matching how the app runs.
# Tests run in mock mode against the in-process FastAPI app — no server, no key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

uv run --with pytest --with httpx python -m pytest tests "$@"
echo "All tests passed."
