#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$ROOT_DIR/scripts/restart-server.sh"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "missing restart script: $SCRIPT_PATH" >&2
  exit 1
fi

bash -n "$SCRIPT_PATH"

grep -q 'set -euo pipefail' "$SCRIPT_PATH"
grep -q 'HOST="${HOST:-127.0.0.1}"' "$SCRIPT_PATH"
grep -q 'PORT="${PORT:-8001}"' "$SCRIPT_PATH"
grep -q 'SESSION_NAME="${SESSION_NAME:-mtools-server-${PORT}}"' "$SCRIPT_PATH"
grep -q 'PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"' "$SCRIPT_PATH"
grep -q 'screen -S "$SESSION_NAME" -X quit' "$SCRIPT_PATH"
grep -q 'cwd_output="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null || true)"' "$SCRIPT_PATH"
grep -q 'awk '\''/^n/ { sub(/^n/, ""); print; exit }'\''' "$SCRIPT_PATH"
grep -q 'kill "$pid"' "$SCRIPT_PATH"
grep -q 'screen -dmS "$SESSION_NAME"' "$SCRIPT_PATH"
grep -q 'screen_list="$(screen -ls || true)"' "$SCRIPT_PATH"
grep -q 'grep -F ".${SESSION_NAME}" <<<"$screen_list"' "$SCRIPT_PATH"
grep -Eq 'manage\.py runserver .*HOST.*PORT.*--noreload' "$SCRIPT_PATH"
grep -q 'lsof -nP -iTCP:"$PORT" -sTCP:LISTEN' "$SCRIPT_PATH"
