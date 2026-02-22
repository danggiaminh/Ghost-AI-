#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required"
  exit 1
fi

export PATH="$HOME/.local/bin:$PATH"

bootstrap_pip_for_python() {
  local py_bin="$1"
  if "$py_bin" -m pip --version >/dev/null 2>&1; then
    return
  fi
  echo "pip not found for ${py_bin}, bootstrapping pip..."
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  if "$py_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)
PY
  then
    "$py_bin" /tmp/get-pip.py >/dev/null
  else
    "$py_bin" /tmp/get-pip.py --user >/dev/null
  fi
}

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
PY

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill required values and rerun ./start.sh"
  exit 1
fi

set -a
source .env
set +a

required_vars=(
  JWT_ACCESS_SECRET
  JWT_REFRESH_SECRET
  SMTP_HOST
  SMTP_PORT
  SMTP_USER
  SMTP_PASS
  SMTP_FROM
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required env variable: ${var_name}"
    exit 1
  fi
done

if [[ ! -x .venv/bin/python ]]; then
  rm -rf .venv
  python3 -m venv .venv >/dev/null 2>&1 || true
fi

if [[ ! -x .venv/bin/python ]]; then
  bootstrap_pip_for_python python3
  python3 -m pip install --user virtualenv >/dev/null
  python3 -m virtualenv .venv >/dev/null
fi

VENV_PY=".venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Failed to create virtual environment"
  exit 1
fi

bootstrap_pip_for_python "$VENV_PY"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r requirements.txt >/dev/null

"$VENV_PY" -m backend.init_db

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

"$VENV_PY" -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --workers 1 --log-level info &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "Ghost is running on http://${HOST}:${PORT}"
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 0.5
done

echo "Health check failed, server did not start correctly"
exit 1
