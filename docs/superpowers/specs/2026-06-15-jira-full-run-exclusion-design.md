# Jira Full Run Exclusion Design

## Goal

Prevent new Jira sync tasks from starting while a Jira `Full Run` is already queued or running.

The behavior must be enforced at the back-end service layer so all callers respect the same rule, not only the `/jira/sync/` page.

## Scope

This design covers:

- Jira sync task enqueue behavior in `apps/jira_workspace/services/sync_service.py`
- Jira sync page request handling in `apps/jira_workspace/views.py`
- Jira sync page feedback in `templates/jira_workspace/sync.html`
- focused tests for service and view behavior

This design does not cover:

- sync2pod task concurrency
- integrations scan concurrency
- global workspace-wide job scheduling
- cancellation, preemption, or recovery of already-running Jira sync tasks

## Current State

- `/jira/sync/` exposes both `Run Incremental` and `Run Full`.
- The POST `run_sync` flow calls `SyncService.enqueue_sync(profile, run_type)`.
- `enqueue_sync()` always creates a `JiraSyncRun` row with `status=queued` and may immediately start a background thread.
- The page already computes `has_active_sync`, but this is only informative UI state.
- There is currently no mutual exclusion rule for active Jira full syncs.
- The `run_sync` view branch currently swallows exceptions with `except Exception: pass`, so rejected or failed enqueue attempts are silent.

## Decision

- If any `JiraSyncRun` exists with:
  - `run_type = full`
  - `status in {queued, running}`
- then reject any new Jira sync enqueue request:
  - reject new `full` runs
  - reject new `incremental` runs
- The rule applies only within Jira sync.
- The rule is enforced in `SyncService`, not only in the view.
- The Jira sync page should surface a clear reason when a new task is rejected.

## Service Behavior

### New Guard

Add a dedicated service-level exception, for example `ActiveFullSyncError`.

`SyncService.enqueue_sync()` must:

1. query for any active full run using:
   - `run_type = JiraSyncRun.RunType.FULL`
   - `status in {JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING}`
2. if one exists, raise `ActiveFullSyncError`
3. otherwise create and optionally launch the new run as it does today

The rejection must happen before creating a new `JiraSyncRun` row, so the database does not accumulate rejected queue entries.

### Query Scope

The guard should apply across all Jira sync profiles, not only the selected profile.

Reason:

- the user request is about an already-running `Full Run` command, not only a profile-local conflict
- current full sync behavior operates on the shared Jira issue cache and membership state
- cross-profile exclusion is safer than assuming profile isolation that the current implementation does not guarantee

## View Behavior

The `run_sync` branch in `apps/jira_workspace/views.py` should stop swallowing all exceptions silently.

Expected flow:

1. normalize `run_type` as it does today
2. call `sync_service.enqueue_sync(profile, run_type)`
3. if `ActiveFullSyncError` is raised:
   - add a user-visible error message
   - redirect back to the same `/jira/sync/?profile=<id>` page
4. for unrelated unexpected exceptions:
   - preserve the existing non-fatal redirect behavior
   - add a generic error message instead of silently ignoring the failure

The page should remain usable for viewing status and history even when starting a new task is blocked.

## UX Behavior

When an active full run exists:

- show a clear message on the Jira sync page that a full sync is already queued or running
- disable both `Run Incremental` and `Run Full`

Reason:

- disabling only `Run Full` would contradict the requested rule because incrementals would still be startable
- UI disablement is not the primary protection, but it reduces confusing failed submissions

The source of truth remains the service-layer guard.

## Template Behavior

`templates/jira_workspace/sync.html` should receive enough context to distinguish:

- any active sync
- an active full sync specifically

Use the full-run-specific signal to:

- render a warning or blocked-state hint near the sync controls
- disable both submit buttons when a full run is active

The page does not need a new route or a new data model field for this behavior.

## Error Message

Use one stable human-readable message for the rejection path. Example:

`A Jira full sync is already queued or running. Wait for it to finish before starting another Jira sync task.`

The exact text can vary, but it should:

- mention Jira full sync explicitly
- explain that the current task was not started
- tell the user what condition must clear before retrying

## Testing

### Service Tests

Add focused tests for `SyncService.enqueue_sync()`:

- when no active full run exists, `incremental` enqueue still succeeds
- when no active full run exists, `full` enqueue still succeeds
- when a `queued` full run exists, enqueueing a new `incremental` raises `ActiveFullSyncError`
- when a `queued` full run exists, enqueueing a new `full` raises `ActiveFullSyncError`
- when a `running` full run exists, enqueueing a new `incremental` raises `ActiveFullSyncError`
- rejected enqueue attempts do not create an extra `JiraSyncRun` row

### View Tests

Add or update `/jira/sync/` POST tests to verify:

- a blocked enqueue redirects back to the selected profile page
- the response includes the rejection message
- no extra run row is created on rejection
- when a full run is active, the rendered page disables both sync buttons

### Regression Focus

Preserve current behavior for:

- successful enqueue flow
- background thread startup for accepted runs
- sync history rendering
- non-Jira tools

## Non-Goals

- no cross-tool scheduler
- no queue prioritization
- no auto-retry after the full run finishes
- no partial allowance for "safe" incremental runs during full sync
- no database-level locking redesign in this iteration
