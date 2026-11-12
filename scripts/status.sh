#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${INFERENCE_PORT:-8090}"
PID_FILE="data/inference.pid"
if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "pid: $PID"
  else
    echo "pid file is stale: $PID"
  fi
else
  echo "pid: not running"
fi

echo "healthz:"
curl -sS -m 3 "http://127.0.0.1:${PORT}/healthz" || echo "healthz unreachable"
echo
echo "Logs: data/logs/inference.log"
