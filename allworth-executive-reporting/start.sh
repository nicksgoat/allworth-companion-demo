#!/bin/bash
set -euo pipefail

# Local startup for the Allworth Executive Reporting app.
#
# Usage:
#   ./start.sh local  [all|backend|frontend|demo]   # run directly on this machine
#   ./start.sh docker [all|down|logs|ps]            # run via docker compose
#
# local all      Flask backend on :5000 + Vite frontend on :5173
# local backend  Flask backend only (uses backend/.venv when present)
# local frontend Vite dev server only
# local demo     Vite in offline demo mode (no auth, no backend needed)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

MODE="${1:-local}"
SERVICE="${2:-all}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

python_bin() {
    if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
        echo "$BACKEND_DIR/.venv/bin/python"
    else
        warn "backend/.venv not found — using system python3" >&2
        command -v python3
    fi
}

start_backend() {
    info "Starting Flask backend on http://0.0.0.0:5000 (reachable at http://localhost:5000)"
    (cd "$BACKEND_DIR" && exec "$(python_bin)" run_local.py)
}

start_frontend() {
    info "Starting Vite dev server on http://localhost:5173"
    (cd "$FRONTEND_DIR" && exec npm run dev)
}

start_demo() {
    info "Starting Vite DEMO preview (no auth/backend) on http://localhost:5173"
    (cd "$FRONTEND_DIR" && exec npm run dev:demo)
}

case "$MODE" in
    local)
        case "$SERVICE" in
            backend)  start_backend ;;
            frontend) start_frontend ;;
            demo)     start_demo ;;
            all)
                info "Starting backend + frontend (Ctrl-C stops both)"
                trap 'kill 0' EXIT
                start_backend &
                # Give Flask a moment so its startup log doesn't interleave Vite's.
                sleep 2
                start_frontend &
                wait
                ;;
            *) echo "Unknown local service: $SERVICE (use all|backend|frontend|demo)"; exit 1 ;;
        esac
        ;;
    docker)
        case "$SERVICE" in
            all)  docker compose -f "$SCRIPT_DIR/docker-compose.yml" up --build ;;
            down) docker compose -f "$SCRIPT_DIR/docker-compose.yml" down ;;
            logs) docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs -f ;;
            ps)   docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps ;;
            *) echo "Unknown docker service: $SERVICE (use all|down|logs|ps)"; exit 1 ;;
        esac
        ;;
    *)
        echo "Usage: ./start.sh [local|docker] [service]"
        exit 1
        ;;
esac
