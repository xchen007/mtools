#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
SESSION_NAME="${SESSION_NAME:-mtools-server-${PORT}}"
PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_command screen
require_command lsof

cd "$ROOT_DIR"

if [[ ! -f manage.py ]]; then
  echo "manage.py not found in $ROOT_DIR" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python executable not found or not executable: $PYTHON_BIN" >&2
  exit 1
fi

port_listener_pids() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

stop_stale_runserver() {
  local pid
  local command
  local cwd
  local cwd_output

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue

    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd_output="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null || true)"
    cwd="$(awk '/^n/ { sub(/^n/, ""); print; exit }' <<<"$cwd_output")"

    if [[ "$cwd" == "$ROOT_DIR" && "$command" == *"manage.py runserver $HOST:$PORT"* ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done < <(port_listener_pids)
}

wait_for_port_free() {
  local attempt

  for attempt in {1..20}; do
    if [[ -z "$(port_listener_pids)" ]]; then
      return 0
    fi
    sleep 0.25
  done

  echo "port $PORT is still in use after stopping $SESSION_NAME" >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2 || true
  exit 1
}

screen -S "$SESSION_NAME" -X quit >/dev/null 2>&1 || true
sleep 1
stop_stale_runserver
wait_for_port_free

SERVER_COMMAND="cd \"$ROOT_DIR\" && exec \"$PYTHON_BIN\" -u manage.py runserver \"$HOST:$PORT\" --noreload"
screen -dmS "$SESSION_NAME" zsh -lc "$SERVER_COMMAND"

sleep 2

screen_list="$(screen -ls || true)"
if ! grep -F ".${SESSION_NAME}" <<<"$screen_list" >/dev/null 2>&1; then
  echo "server screen session exited before becoming healthy: $SESSION_NAME" >&2
  echo "try running manually: $PYTHON_BIN -u manage.py runserver $HOST:$PORT --noreload" >&2
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "mtools server restarted at http://$HOST:$PORT/ in screen session '$SESSION_NAME'"
else
  echo "server did not start listening on $HOST:$PORT" >&2
  echo "inspect with: screen -r $SESSION_NAME" >&2
  exit 1
fi
