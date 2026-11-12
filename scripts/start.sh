#!/usr/bin/env bash
# Start the API on the configured host and port. Refuses port 8089.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run scripts/install.sh first." >&2
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

HOST="${INFERENCE_HOST:-127.0.0.1}"
PORT="${INFERENCE_PORT:-8090}"
if [[ "$PORT" == "8089" ]]; then
  echo "Refusing to start: port 8089 is reserved for the existing service and is not switched by this version." >&2
  exit 1
fi

mkdir -p data/logs data/outputs data/inputs data/recovery
PID_FILE="data/inference.pid"
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "Inference API already running as pid $OLD_PID. This script will not replace it." >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if .venv/bin/python - "$HOST" "$PORT" <<'PY'
import socket
import sys
host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
try:
    sock.bind((host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
then
  :
else
  echo "Port ${HOST}:${PORT} is already in use. This script will not stop the existing process." >&2
  exit 1
fi

if [[ -f .env ]]; then
  MODE="$(stat -f '%Lp' .env 2>/dev/null || stat -c '%a' .env)"
  case "$MODE" in
    600|400) ;;
    *) echo "Refusing to start because .env mode is $MODE. Run chmod 600 .env." >&2; exit 1 ;;
  esac
fi

nohup .venv/bin/python -m inference.runtime >> data/logs/inference.log 2>&1 &
echo $! > "$PID_FILE"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "Inference API is listening on ${HOST}:${PORT}. Logs: data/logs/inference.log"
    exit 0
  fi
  sleep 0.3
done

echo "Process started but /healthz did not respond. See data/logs/inference.log." >&2
exit 1
