# mtools

`mtools` is a Django workspace for Jira operations, sync2pod execution, and integrations cataloging.

## Current Workspace

The active app is `apps/jira_workspace`. It now provides:

- `/workspace/` for cross-tool summary cards, health, and recent activity
- `/jira/dashboard/` for issue metrics and recent tickets
- `/jira/query/` for saved Jira query presets
- `/jira/issues/` for filterable issue results
- `/jira/sync/` for Jira sync profiles, runs, and blocker states
- `/sync2pod/` for stored sync2pod profiles, run logs, and queued watch events
- `/integrations/` for grouped tool catalog, contract matrix, and recent scan activity

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

Start the dev server on the default local port:

```bash
python manage.py runserver 127.0.0.1:8011
```

If port `8011` is already in use, check the listener and switch to another port:

```bash
lsof -nP -iTCP:8011 -sTCP:LISTEN
python manage.py runserver 127.0.0.1:8020
```

## Verification Routes

Open these pages after the server starts:

- `http://127.0.0.1:8011/workspace/`
- `http://127.0.0.1:8011/jira/dashboard/`
- `http://127.0.0.1:8011/jira/query/`
- `http://127.0.0.1:8011/jira/issues/`
- `http://127.0.0.1:8011/jira/sync/`
- `http://127.0.0.1:8011/sync2pod/`
- `http://127.0.0.1:8011/integrations/`

Verified on the current repo snapshot:

- `python manage.py check` returns `System check identified no issues (0 silenced).`
- `python manage.py runserver 127.0.0.1:8020` starts successfully
- `GET /` returns `302` to `/workspace/`
- `GET /workspace/` returns `200`

## Environment

Jira sync uses these environment variables when live access is attempted:

```bash
JIRA_API_BASE_URL
JIRA_API_TOKEN
JIRA_AUTH_TYPE
JIRA_USER_EMAIL
```

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
- `python manage.py test apps.jira_workspace.tests -v 2` passes with `66` tests

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
