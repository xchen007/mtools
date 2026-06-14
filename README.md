# mtools

`mtools` is a Django workspace for Jira operations, sync2pod execution, and integrations cataloging.

## Current Workspace

The active app is `apps/jira_workspace`. It now provides:

- `/workspace/` for cross-tool summary cards, health, and recent activity
- `/jira/query/` as the visible Jira Query Card dashboard/workbench
- `/sync2pod/` for stored sync2pod profiles, run logs, and queued watch events
- `/integrations/` for grouped tool catalog, contract matrix, and recent scan activity

Jira's visible workflow is card-centric. The top Jira tool button points to `/jira/query/`, the left sidebar lists Query Cards, and individual cards render their metrics, table, and detail drawer in one shared workbench.

Legacy Jira routes are intentionally still available for compatibility and diagnostics, but they are no longer primary navigation entries:

- `/jira/dashboard/`
- `/jira/issues/`
- `/jira/sync/`

`/jira/sync/` manages Jira cache refresh profiles and run history. Query Cards read from the local Jira cache, so data freshness depends on the most recent successful live sync, not on opening the Query Card page.

The root route `/` redirects to `/workspace/`.

## Local Setup

Use the project virtualenv:

```bash
source .venv/bin/activate
```

Run a Django configuration check:

```bash
python manage.py check
```

Apply migrations:

```bash
python manage.py migrate
```

Start the dev server on the current local port:

```bash
python manage.py runserver 127.0.0.1:8001
```

For a long-lived local server in this Codex/tool environment, use a detached `screen` session so the process is not cleaned up when a shell command exits:

```bash
screen -dmS mtools-server zsh -lc 'cd /Users/xchen17/workspace/mtools && exec ./.venv/bin/python -u manage.py runserver 127.0.0.1:8001 --noreload'
screen -ls
lsof -nP -iTCP:8001 -sTCP:LISTEN
```

Stop it with:

```bash
screen -S mtools-server -X quit
```

## Verification Routes

Open these pages after the server starts:

- `http://127.0.0.1:8001/workspace/`
- `http://127.0.0.1:8001/jira/query/`
- `http://127.0.0.1:8001/sync2pod/`
- `http://127.0.0.1:8001/integrations/`

Optional legacy/diagnostic Jira pages:

- `http://127.0.0.1:8001/jira/dashboard/`
- `http://127.0.0.1:8001/jira/issues/`
- `http://127.0.0.1:8001/jira/sync/`

Verified on the current repo snapshot:

- `python manage.py check` returns `System check identified no issues (0 silenced).`
- `python manage.py runserver 127.0.0.1:8001` starts successfully
- `GET /` returns `302` to `/workspace/`
- `GET /workspace/` returns `200`
- `GET /jira/query/` returns `200`

## Jira Data Freshness

The Query Card workbench displays locally cached `JiraIssue` rows. To determine whether those rows are fresh, check:

- the latest successful `JiraSyncRun` for the relevant `JiraSyncProfile`
- the profile's `last_cursor`
- whether the latest run used live Jira access or simulation data
- whether the latest run failed with an external blocker such as Jira `403`

Current local databases can contain seeded or simulated rows. A successful simulated sync proves UI and sync logic, but it does not prove that live Jira ticket status is current.

## Environment

Jira sync uses these environment variables when live access is attempted:

```bash
JIRA_API_BASE_URL
JIRA_API_TOKEN
JIRA_AUTH_TYPE
JIRA_USER_EMAIL
```

For full local simulation without Jira network access, enable the fake adapter and seed the local cache:

```bash
export JIRA_SIMULATION_MODE=true
export JIRA_SIMULATION_SCENARIO=default
python manage.py seed_fake_jira
python manage.py runserver 127.0.0.1:8001
```

Additional simulation settings:

```bash
JIRA_SIMULATION_FIXTURE_PATH
```

This loads fixture-backed Jira identity and issue data from `apps/jira_workspace/fixtures/jira_simulation.json`. The sync UI can then run incremental and full syncs without talking to a real Jira server.

Known external limitation:

- Jira live access can still return `403` with `The request is blocked.`
- the UI surfaces this as an external blocker instead of hiding the failure

## Tests

Run the focused boot regression checks:

```bash
python manage.py test apps.jira_workspace.tests.test_app_boot -v 2
```

Run the full workspace test suite:

```bash
python manage.py test apps.jira_workspace.tests -v 2
```

Verified on the current repo snapshot:

- `python manage.py test apps.jira_workspace.tests.test_app_boot -v 2` passes with `3` tests
- `python manage.py test apps.jira_workspace.tests -v 2` passes with `130` tests

## Project Structure

```text
mtools/
├── apps/
│   └── jira_workspace/
├── mtools/
├── static/
│   └── jira_workspace/
├── templates/
│   └── jira_workspace/
├── ui-preview/
├── manage.py
└── README.md
```
