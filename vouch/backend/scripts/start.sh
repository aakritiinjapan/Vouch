#!/usr/bin/env bash
# Production startup for Render.
# Seeds the DB, starts uvicorn, waits for it to be healthy, then runs one demo cycle so the
# held-proposals queue is populated on every cold start (the DB is ephemeral on Render free tier).
set -euo pipefail

PORT="${PORT:-8000}"

echo "==> seeding database"
python -m scripts.seed

echo "==> starting uvicorn on port $PORT"
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
SERVER_PID=$!

echo "==> waiting for health check"
for _ in $(seq 60); do
  curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1 \
  || { echo "server did not come up"; kill "$SERVER_PID" 2>/dev/null; exit 1; }

echo "==> seeding demo held proposals"
curl -sf -X POST "http://localhost:${PORT}/cycles/run" \
  -H "Content-Type: application/json" \
  -d '{"simulate_run": "run_degraded", "simulate_heal": "healed_swapped"}' \
  >/dev/null 2>&1 && echo "==> demo cycle done" || echo "==> demo cycle failed (non-fatal)"

echo "==> ready"
wait "$SERVER_PID"
