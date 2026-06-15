# Restart Server Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a quick local restart script for the `mtools` Django development server.

**Architecture:** A single Bash script wraps the existing README-documented `screen` workflow. A focused shell smoke test verifies the restart mechanics without launching the Django server.

**Tech Stack:** Bash, `screen`, `lsof`, Django `manage.py runserver`.

---

## File Structure

- Create: `scripts/restart-server.sh` - executable restart command for the local dev server.
- Create: `tests/test_restart_server_script.sh` - shell smoke test for script syntax and expected behavior.

### Task 1: Restart Script Smoke Test

**Files:**
- Create: `tests/test_restart_server_script.sh`

- [ ] **Step 1: Write the failing test**

```bash
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
grep -q 'SESSION_NAME="${SESSION_NAME:-mtools-server}"' "$SCRIPT_PATH"
grep -q 'HOST="${HOST:-127.0.0.1}"' "$SCRIPT_PATH"
grep -q 'PORT="${PORT:-8001}"' "$SCRIPT_PATH"
grep -q 'PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"' "$SCRIPT_PATH"
grep -q 'screen -S "$SESSION_NAME" -X quit' "$SCRIPT_PATH"
grep -q 'screen -dmS "$SESSION_NAME"' "$SCRIPT_PATH"
grep -q 'manage.py runserver "$HOST:$PORT" --noreload' "$SCRIPT_PATH"
grep -q 'lsof -nP -iTCP:"$PORT" -sTCP:LISTEN' "$SCRIPT_PATH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/test_restart_server_script.sh`

Expected: non-zero exit with `missing restart script`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-15-restart-server-script-design.md docs/superpowers/plans/2026-06-15-restart-server-script-implementation.md tests/test_restart_server_script.sh
git commit -m "test: specify restart server script"
```

### Task 2: Restart Script Implementation

**Files:**
- Create: `scripts/restart-server.sh`
- Test: `tests/test_restart_server_script.sh`

- [ ] **Step 1: Write minimal implementation**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${SESSION_NAME:-mtools-server}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
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

screen -S "$SESSION_NAME" -X quit >/dev/null 2>&1 || true
sleep 1

screen -dmS "$SESSION_NAME" zsh -lc "cd '$ROOT_DIR' && exec '$PYTHON_BIN' -u manage.py runserver '$HOST:$PORT' --noreload"

sleep 2

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "mtools server restarted at http://$HOST:$PORT/ in screen session '$SESSION_NAME'"
else
  echo "server did not start listening on $HOST:$PORT" >&2
  echo "inspect with: screen -r $SESSION_NAME" >&2
  exit 1
fi
```

- [ ] **Step 2: Run test to verify it passes**

Run: `bash tests/test_restart_server_script.sh`

Expected: exit code `0`.

- [ ] **Step 3: Run Django system check**

Run: `./.venv/bin/python manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 4: Commit**

```bash
git add scripts/restart-server.sh tests/test_restart_server_script.sh
git commit -m "feat: add restart server script"
```
