# mtools Workspace UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Migrate all `ui-preview/*.html` pages into the Django app, wire them to real backend behavior, and deliver a testable workspace UI for Jira, sync2pod, and integrations.

**Architecture:** Keep the current Django server-rendered approach. Build one shared workspace shell in templates/static, extend the existing `jira_workspace` app for all pages and routes, add real persistence/services for `sync2pod` and `integrations`, then aggregate everything into a real `/workspace/` home page.

**Tech Stack:** Django 3.2, SQLite, Django templates, vanilla JavaScript, existing `apps/jira_workspace` app, Django test runner.

---

## File Structure

### Core routes, templates, and static

- Modify: `mtools/urls.py`
- Modify: `apps/jira_workspace/urls.py`
- Modify: `apps/jira_workspace/views.py`
- Modify: `templates/jira_workspace/base.html`
- Create: `templates/jira_workspace/workspace_home.html`
- Create: `templates/jira_workspace/issues.html`
- Create: `templates/jira_workspace/sync.html`
- Create: `templates/jira_workspace/sync2pod.html`
- Create: `templates/jira_workspace/integrations.html`
- Create: `templates/jira_workspace/partials/app_nav.html`
- Create: `templates/jira_workspace/partials/app_rail.html`
- Create: `templates/jira_workspace/partials/topbar.html`
- Modify: `templates/jira_workspace/dashboard.html`
- Modify: `templates/jira_workspace/queries.html`
- Modify: `templates/jira_workspace/profiles.html`
- Modify: `templates/jira_workspace/partials/ticket_table.html`
- Modify: `static/jira_workspace/jira.css`
- Modify: `static/jira_workspace/jira.js`

### Backend models, forms, and services

- Modify: `apps/jira_workspace/models.py`
- Modify: `apps/jira_workspace/forms.py`
- Create: `apps/jira_workspace/services/workspace_service.py`
- Create: `apps/jira_workspace/services/sync2pod_service.py`
- Create: `apps/jira_workspace/services/integrations_service.py`
- Modify: `apps/jira_workspace/services/query_service.py`
- Modify: `apps/jira_workspace/services/stats_service.py`
- Modify: `apps/jira_workspace/services/sync_service.py`
- Create: `apps/jira_workspace/migrations/0003_workspace_models.py`

### Tests

- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `apps/jira_workspace/tests/test_models.py`
- Modify: `apps/jira_workspace/tests/test_sync_service.py`
- Create: `apps/jira_workspace/tests/test_workspace_service.py`
- Create: `apps/jira_workspace/tests/test_sync2pod_service.py`
- Create: `apps/jira_workspace/tests/test_integrations_service.py`

---

### Task 1: Build the shared workspace shell and route map

**Files:**
- Modify: `mtools/urls.py`
- Modify: `apps/jira_workspace/urls.py`
- Modify: `templates/jira_workspace/base.html`
- Create: `templates/jira_workspace/partials/app_nav.html`
- Create: `templates/jira_workspace/partials/app_rail.html`
- Create: `templates/jira_workspace/partials/topbar.html`
- Modify: `static/jira_workspace/jira.css`
- Modify: `static/jira_workspace/jira.js`
- Test: `apps/jira_workspace/tests/test_views.py`

- [x] Add failing route/render tests for `/`, `/workspace/`, `/jira/issues/`, `/jira/sync/`, `/sync2pod/`, and `/integrations/`.
- [x] Run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_views -v 2 ` and verify the new assertions fail for missing routes or missing template content.
- [x] Refactor the base template into the shared shell from the preview spec, including left nav, topbar, breadcrumb slot, and right rail.
- [x] Wire the root redirect and all new routes in `mtools/urls.py` and `apps/jira_workspace/urls.py`.
- [x] Move shared layout and component styles from preview pages into `static/jira_workspace/jira.css`, keeping one common token system instead of per-page inline CSS.
- [x] Add the minimum JS hooks needed for nav state, rail refresh placeholders, and shared partial loading behavior without hardcoding page-specific mock data.
- [x] Re-run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_views -v 2 ` and verify route/render coverage passes.
- [x] Commit with `git commit -m "feat: build workspace shell and route map"`.

### Task 2: Migrate Jira pages to the new UI and complete the Jira workflow

**Files:**
- Modify: `apps/jira_workspace/views.py`
- Modify: `apps/jira_workspace/forms.py`
- Modify: `apps/jira_workspace/services/query_service.py`
- Modify: `apps/jira_workspace/services/stats_service.py`
- Modify: `apps/jira_workspace/services/sync_service.py`
- Modify: `templates/jira_workspace/dashboard.html`
- Modify: `templates/jira_workspace/queries.html`
- Modify: `templates/jira_workspace/profiles.html`
- Create: `templates/jira_workspace/issues.html`
- Create: `templates/jira_workspace/sync.html`
- Modify: `templates/jira_workspace/partials/ticket_table.html`
- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `apps/jira_workspace/tests/test_sync_service.py`

- [x] Add failing tests for the Jira page set: dashboard summary rendering, query page library/filter rendering, issues page list/filter rendering, and sync page profile/run rendering.
- [x] Run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_views apps.jira_workspace.tests.test_sync_service -v 2 ` and verify the new expectations fail.
- [x] Keep existing Jira local-cache architecture, but split the old `queries` and `profiles` behavior into the new `jira/query`, `jira/issues`, and `jira/sync` pages.
- [x] Extend service/view context so the new pages render real saved-query data, issue filters, sync profiles, sync history, and Jira external-blocker error states.
- [x] Replace the minimal templates with preview-aligned layouts while preserving real Django data bindings and existing partial-based result rendering.
- [x] Re-run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_views apps.jira_workspace.tests.test_sync_service -v 2 ` and verify the Jira workflow tests pass.
- [x] Commit with `git commit -m "feat: migrate jira workflow pages"`.

### Task 3: Add real sync2pod persistence, service logic, and UI

**Files:**
- Modify: `apps/jira_workspace/models.py`
- Modify: `apps/jira_workspace/forms.py`
- Create: `apps/jira_workspace/services/sync2pod_service.py`
- Create: `templates/jira_workspace/sync2pod.html`
- Create: `apps/jira_workspace/tests/test_sync2pod_service.py`
- Modify: `apps/jira_workspace/tests/test_models.py`
- Modify: `apps/jira_workspace/tests/test_views.py`
- Create: `apps/jira_workspace/migrations/0003_workspace_models.py`

- [x] Add failing model, service, and view tests for sync2pod profiles, run logging, capability checks, page rendering, and failure-state rendering.
- [x] Run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_models apps.jira_workspace.tests.test_sync2pod_service apps.jira_workspace.tests.test_views -v 2 ` and verify sync2pod expectations fail because models/services/routes are missing.
- [x] Add persistent models for sync2pod profiles, runs, and watch events in `models.py`, plus the migration.
- [x] Add forms/service methods for config CRUD, capability checks, run creation, and log/status summaries using real command execution wrappers where available.
- [x] Implement the sync2pod page and view context so the preview sections show real stored configs, recent runs, queue state, and actionable error messages.
- [x] Re-run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_models apps.jira_workspace.tests.test_sync2pod_service apps.jira_workspace.tests.test_views -v 2 ` and verify sync2pod coverage passes.
- [x] Commit with `git commit -m "feat: add sync2pod backend and page"`.

### Task 4: Add integrations registry persistence, service logic, and UI

**Files:**
- Modify: `apps/jira_workspace/models.py`
- Create: `apps/jira_workspace/services/integrations_service.py`
- Create: `templates/jira_workspace/integrations.html`
- Create: `apps/jira_workspace/tests/test_integrations_service.py`
- Modify: `apps/jira_workspace/tests/test_models.py`
- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `apps/jira_workspace/migrations/0003_workspace_models.py`

- [x] Add failing model, service, and view tests for integration tool records, contract matrix output, grouped catalog rendering, search behavior, and readiness display.
- [x] Run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_models apps.jira_workspace.tests.test_integrations_service apps.jira_workspace.tests.test_views -v 2 ` and verify integrations expectations fail.
- [x] Add persistent integration tool, contract, and scan-run models, reusing the same migration task if Task 3 has already introduced `0003_workspace_models.py`.
- [x] Implement a lightweight integrations service that builds the catalog from persisted records and code-available metadata instead of template literals.
- [x] Implement the integrations page so grouped tools, matrix rows, and recent scan events come from real service output.
- [x] Re-run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_models apps.jira_workspace.tests.test_integrations_service apps.jira_workspace.tests.test_views -v 2 ` and verify integrations coverage passes.
- [x] Commit with `git commit -m "feat: add integrations catalog backend and page"`.

### Task 5: Build the workspace home aggregator, integrate cross-tool rail data, and verify the full stack

**Files:**
- Modify: `apps/jira_workspace/views.py`
- Create: `apps/jira_workspace/services/workspace_service.py`
- Create: `templates/jira_workspace/workspace_home.html`
- Modify: `templates/jira_workspace/partials/app_rail.html`
- Modify: `apps/jira_workspace/tests/test_views.py`
- Create: `apps/jira_workspace/tests/test_workspace_service.py`
- Modify: `README.md`

- [x] Add failing tests for the workspace home page summary cards, cross-tool recent runs, health data, and root redirect behavior.
- [x] Run ` .venv/bin/python manage.py test apps.jira_workspace.tests.test_views apps.jira_workspace.tests.test_workspace_service -v 2 ` and verify the new workspace assertions fail.
- [x] Implement a workspace aggregation service that combines Jira sync runs, sync2pod runs, and integrations scan activity into one view model.
- [x] Build the workspace home template to match the preview information hierarchy with real aggregate data instead of mock arrays.
- [x] Update the shared right rail so it can render cross-tool activity and health in a consistent way across pages.
- [x] Update `README.md` with the real UI route map and startup/verification steps for the migrated workspace.
- [x] Run the full app test suite with ` .venv/bin/python manage.py test apps.jira_workspace.tests -v 2 `.
- [x] Start a local dev server on an open port, verify all target routes open, and capture any external blockers such as Jira 403 responses.
- [x] Commit with `git commit -m "feat: complete workspace ui migration"` if verification is green aside from documented external blockers.

---

## Execution Notes

- Task 1 is the first critical-path task and must land before the new page work is integrated.
- Task 2 can proceed after Task 1.
- Task 3 and Task 4 both touch `models.py` and the same migration, so one worker must own the model/migration edit at a time. Their page/service work can still be split after the persistence layer lands.
- Task 5 depends on Tasks 2, 3, and 4 being integrated.
- After each task:
  - run spec-compliance review
  - run code-quality review
  - fix any open issues before moving forward

## Verification Checklist

- `/` redirects to `/workspace/`
- `/workspace/` renders real aggregate content
- `/jira/dashboard/` renders migrated dashboard UI
- `/jira/query/` renders migrated query UI
- `/jira/issues/` renders migrated issues UI
- `/jira/sync/` renders migrated sync UI
- `/sync2pod/` renders real config/run data
- `/integrations/` renders real catalog/matrix data
- ` .venv/bin/python manage.py test apps.jira_workspace.tests -v 2 ` passes
- Local server serves static assets and target routes
- Any Jira external 403 is surfaced as an external blocker, not hidden
