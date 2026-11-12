#!/usr/bin/env bash
# Install a local virtualenv and create .env only when it does not already exist.
# This script does not stop ComfyUI, Studio, or any service on port 8089.
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
if [[ "$PORT" == "8089" ]]; then
  echo "Refusing install: INFERENCE_PORT=8089 would bind the existing native API." >&2
  exit 1
fi

PYTHON="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  umask 077
  cp .env.example .env
  .venv/bin/python - <<'PY'
import secrets
from pathlib import Path

key = secrets.token_urlsafe(32)
path = Path(".env")
lines = []
replaced = False
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith("INFERENCE_API_KEY=") and not replaced:
        lines.append("INFERENCE_API_KEY=" + key)
        replaced = True
    else:
        lines.append(line)
if not replaced:
    raise SystemExit("INFERENCE_API_KEY line was not found in .env.example")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
  echo "Created .env. The new API key was written to that file and is not printed."
else
  echo "Existing .env was left unchanged."
fi

chmod 600 .env
mkdir -p data/outputs data/inputs data/logs data/recovery
chmod 700 data || true

if [[ "${INSTALL_SYSTEMD:-0}" == "1" ]]; then
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "systemd user units are installed only on Linux. The template remains in deploy/." >&2
    exit 1
  fi
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p "$UNIT_DIR"
  sed "s#@ROOT@#${ROOT}#g" deploy/inference-api.user.service > "$UNIT_DIR/multimodal-inference-api.service"
  echo "User unit installed at $UNIT_DIR/multimodal-inference-api.service. It was not enabled or started."
fi

.venv/bin/python -m compileall -q inference app.py
echo "Install complete. Start with scripts/start.sh"
