#!/usr/bin/env bash
#
# Bring the whole demo up with one command.
#
#   ./demo.sh            install if needed, seed, start both servers
#   ./demo.sh --reset    wipe the database and reseed first
#   ./demo.sh --test     run the test suite and exit
#
# Everything runs offline against the dataset derived from the real collector run. No Bright Data or
# Anthropic credentials are required.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/vouch/backend"
FRONTEND="$ROOT/vouch/frontend"
VENV="$BACKEND/.venv"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
info() { printf '  %s\n' "$1"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$1" >&2; exit 1; }

# --------------------------------------------------------------------------------------
# prerequisites
# --------------------------------------------------------------------------------------

PYTHON="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON" ] || die "python 3.11+ not found on PATH"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "python 3.11+ required; found $("$PYTHON" --version 2>&1)"
command -v node >/dev/null || die "node 20+ not found on PATH"

# --------------------------------------------------------------------------------------
# backend
# --------------------------------------------------------------------------------------

bold "1/4  backend dependencies"
if [ ! -d "$VENV" ]; then
  info "creating $VENV"
  "$PYTHON" -m venv "$VENV" 2>/dev/null || {
    # Some distributions ship venv without ensurepip. Fall back to the interpreter as-is rather
    # than failing the whole demo over a packaging quirk.
    info "venv unavailable, using the system interpreter"
    VENV=""
  }
fi
if [ -n "$VENV" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  PYTHON="python"
fi
"$PYTHON" -m pip install -q --disable-pip-version-check -r "$BACKEND/requirements.txt"
info "ok"

if [ "${1:-}" = "--test" ]; then
  bold "tests"
  cd "$BACKEND" && exec "$PYTHON" -m pytest -q
fi

# --------------------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------------------

bold "2/4  database"
cd "$BACKEND"
# Always seed. The seed is idempotent by design - it upserts rather than duplicating - and testing
# for an existing vouch.db is not a safe shortcut: starting the app creates the file before anything
# is in it, so "the file exists" and "the database has products" are different questions. Guessing
# wrong there produces an empty dashboard, which reads as a broken product rather than a missed step.
if [ "${1:-}" = "--reset" ] && [ -f "$BACKEND/vouch.db" ]; then
  "$PYTHON" -m scripts.reset_db >/dev/null
fi
"$PYTHON" -m scripts.seed | sed 's/^/  /'

# --------------------------------------------------------------------------------------
# frontend
# --------------------------------------------------------------------------------------

bold "3/4  frontend dependencies"
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install --silent
fi
info "ok"

# --------------------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------------------

bold "4/4  starting"

# Free the ports first so a re-run doesn't fail on EADDRINUSE from a previous session.
for port in "$API_PORT" "$UI_PORT"; do
  if command -v lsof >/dev/null; then
    lsof -ti:"$port" -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
  fi
done

cleanup() {
  trap - INT TERM EXIT
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${UI_PID:-}" ] && kill "$UI_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

cd "$BACKEND"
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"$ROOT/.demo-api.log" 2>&1 &
API_PID=$!

for _ in $(seq 40); do
  curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 \
  || { cat "$ROOT/.demo-api.log"; die "the API did not come up; log above"; }
info "api    http://127.0.0.1:$API_PORT   (/docs for the OpenAPI browser)"

cd "$FRONTEND"
npm run dev -- --port "$UI_PORT" >"$ROOT/.demo-ui.log" 2>&1 &
UI_PID=$!

for _ in $(seq 40); do
  curl -sf "http://127.0.0.1:$UI_PORT" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$UI_PORT" >/dev/null 2>&1 \
  || { cat "$ROOT/.demo-ui.log"; die "the dashboard did not come up; log above"; }

printf '  \033[1mdashboard  http://127.0.0.1:%s\033[0m\n\n' "$UI_PORT"
info "Ctrl-C to stop both."
wait
