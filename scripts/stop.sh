#!/usr/bin/env bash
# Stop only the inference API process recorded for this checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="data/inference.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Inference API is not running (no pid file)."
  exit 0
fi

PID="$(tr -d '[:space:]' < "$PID_FILE")"
if [[ ! "$PID" =~ ^[0-9]+$ ]]; then
  echo "Refusing to signal an invalid pid file." >&2
  exit 1
fi

process_is_gone() {
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    return 0
  fi
  # An unreaped zombie has already exited. Signaling it cannot stop a service.
  local state
  state="$(ps -p "$PID" -o stat= 2>/dev/null | tr -d '[:space:]' || true)"
  case "$state" in
    Z*) return 0 ;;
  esac
  return 1
}

if process_is_gone; then
  rm -f "$PID_FILE"
  echo "Removed stale pid file."
  exit 0
fi

args="$(ps -p "$PID" -o args= 2>/dev/null || true)"
cwd="$(lsof -a -p "$PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
owned=0
case "$args" in
  *"-m inference.runtime"*)
    case "$args" in
      *"$ROOT/"*) owned=1 ;;
    esac
    if [[ "$owned" -eq 0 && "$cwd" == "$ROOT" ]]; then
      owned=1
    fi
    ;;
esac

if [[ "$owned" -ne 1 ]]; then
  echo "Refusing to signal pid $PID because it is not this checkout's inference API." >&2
  exit 1
fi

kill -TERM "$PID"
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if process_is_gone; then
    rm -f "$PID_FILE"
    echo "Inference API stopped."
    exit 0
  fi
  sleep 0.5
done

echo "Process $PID did not exit after SIGTERM. It was not killed with SIGKILL." >&2
exit 1
