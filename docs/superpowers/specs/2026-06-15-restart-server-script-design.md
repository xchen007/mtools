# Restart Server Script Design

## Goal

Add a small shell script for quickly restarting the local `mtools` Django development server.

## Context

`README.md` documents the current long-lived local server pattern:

- detached `screen` session: `mtools-server`
- project directory: `/Users/xchen17/workspace/mtools`
- command: `./.venv/bin/python -u manage.py runserver 127.0.0.1:8001 --noreload`
- stop command: `screen -S mtools-server -X quit`

The script should wrap that flow without changing the project's runtime model.

## Design

Create `scripts/restart-server.sh`. The script stops any existing configured `screen` session, starts a new detached session from the repository root, waits briefly, and reports whether the configured TCP port is listening.

Defaults:

- `SESSION_NAME=mtools-server`
- `HOST=127.0.0.1`
- `PORT=8001`
- `PYTHON_BIN=./.venv/bin/python`

Each default can be overridden through environment variables:

```bash
PORT=8010 SESSION_NAME=mtools-test scripts/restart-server.sh
```

The script should fail fast when required local tools or files are missing:

- `screen`
- `lsof`
- `manage.py`
- configured Python executable

## Error Handling

Missing prerequisites return a non-zero exit code with a concise error message.

If the old `screen` session does not exist, the script continues because that is a normal first-run state.

If the new server process starts but the port is not listening after a short wait, the script returns a non-zero exit code and tells the user how to inspect the screen session.

## Testing

Add a shell smoke test at `tests/test_restart_server_script.sh` that validates the script is syntactically valid and contains the expected restart behavior:

- uses Bash strict mode
- defines the documented defaults
- stops the configured `screen` session
- starts a detached `screen` session
- runs Django through `manage.py runserver`
- includes the `--noreload` flag
- checks the configured port with `lsof`
