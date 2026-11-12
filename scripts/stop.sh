#!/usr/bin/env bash
# Stop only the pid recorded by scripts/start.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="data/inference.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Inference API is not running (no pid file)."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if ! kill -0 "$PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "Removed stale pid file."
  exit 0
fi

kill -TERM "$PID"
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "Inference API stopped."
    exit 0
  fi
  sleep 0.5
done

echo "Process $PID did not exit after SIGTERM. It was not killed with SIGKILL." >&2
exit 1
