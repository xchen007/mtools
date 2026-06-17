# Jira Global Sync Policy Finish Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish and commit the Jira global sync policy implementation with one coherent sync-page product direction, passing tests, and no unrelated files committed.

**Architecture:** The canonical Jira sync UI is global-policy based: one primary policy, current policy version, child scopes, scope reports, and active membership reads. Legacy `JiraSyncProfile` / `JiraSyncRun` remains in the codebase for existing data, operation history, and non-sync-page compatibility, but the main Jira Sync command center must not expose profile save/run controls or render profile-based run history as the primary sync status model.

**Tech Stack:** Django 3.2, server-rendered templates, SQLite test DB, vanilla JS, existing `jira_workspace` app.

---

## Current State Snapshot

- The repo is `/Users/xchen17/workspace/mtools`.
- The branch is `master`; this task is being continued in-place.
- There are unrelated dirty files that must not be committed: `README.md`, `.claude/`, `.continues-handoff.md`, `.superpowers/`, `docs/superpowers/handoffs/`, older untracked plan/spec files, and `tmp/`.
- The intended commit should include only these Jira global-sync files:
  - `apps/jira_workspace/migrations/0011_global_sync_policy.py`
  - `apps/jira_workspace/services/query_service.py`
  - `apps/jira_workspace/services/sync_service.py`
  - `apps/jira_workspace/tests/test_query_service.py`
  - `apps/jira_workspace/tests/test_sync_policy_migration.py`
  - `apps/jira_workspace/tests/test_sync_service.py`
  - `apps/jira_workspace/tests/test_views.py`
  - `apps/jira_workspace/views.py`
  - `templates/jira_workspace/sync.html`
  - `static/jira_workspace/jira.css`

## Non-Negotiable Product Decisions

1. `Primary Jira Policy` is the single global policy identity.
2. Reads must use only the current policy version when it is `READY` and `full_sync_required=False`.
3. Reads must return empty while the current version is rebuilding; do not fall back to an older ready version.
4. Sync page policy/scope actions must reject secondary policies and stale-version scopes.
5. Sync page main UI must be scope/report based, not profile-run based.
6. `JiraSyncProfile` model/service compatibility can remain outside the main sync command center; do not delete legacy model or service code in this finish plan.

---

## File Map

- Modify `apps/jira_workspace/views.py`: remove sync-page profile form/run branches, compute active status from `SyncScope`, and pass `scope_sync_reports` as the page history source.
- Modify `templates/jira_workspace/sync.html`: remove `Current Profile`, `Sync Controls`, and `Profile Editor`; render latest status, summary, and history from `scope_sync_reports`.
- Modify `templates/jira_workspace/partials/sync_runs.html`: keep filename for compatibility, but change table semantics from `sync_runs` / profile rows to `scope_sync_reports` / scope-version rows.
- Modify `apps/jira_workspace/tests/test_views.py`: remove contradictory profile UI/action assertions and add scope-report assertions.
- Modify `apps/jira_workspace/tests/test_query_service.py`: keep strict current-version rebuild test.
- Review existing changes in `apps/jira_workspace/services/query_service.py` and `apps/jira_workspace/services/sync_service.py`; only patch if review finds current-version or report semantics broken.

---

## Task 1: Lock Query Semantics To Current Ready Version Only

**Files:**
- Modify: `apps/jira_workspace/services/query_service.py`
- Test: `apps/jira_workspace/tests/test_query_service.py`

- [ ] **Step 1: Verify the query helper has no fallback**

Open `apps/jira_workspace/services/query_service.py` and ensure `serving_global_sync_policy_version()` is exactly:

```python
def serving_global_sync_policy_version():
    policy = current_global_sync_policy()
    if policy is None or policy.current_version_id is None:
        return None
    if (
        policy.current_version.status == GlobalSyncPolicyVersion.Status.READY
        and not policy.current_version.full_sync_required
    ):
        return policy.current_version
    return None
```

- [ ] **Step 2: Verify the rebuild test asserts empty results**

Open `apps/jira_workspace/tests/test_query_service.py` and ensure the rebuild test asserts:

```python
def test_build_issue_queryset_returns_empty_while_current_version_rebuilds(self):
    pending_version = GlobalSyncPolicyVersion.objects.create(
        policy=self.version.policy,
        version_no=2,
        strategy_hash="hash-v2",
        status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
        full_sync_required=True,
    )
    self.version.policy.current_version = pending_version
    self.version.policy.status = GlobalSyncPolicy.Status.STALE
    self.version.policy.save(update_fields=["current_version", "status", "updated_at"])

    queryset = build_issue_queryset(username="xchen17", source="assigned")

    assert serving_global_sync_policy_version() is None
    assert list(queryset.values_list("issue_key", flat=True)) == []
```

- [ ] **Step 3: Run the focused query tests**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_query_service -v 2
```

Expected: all query service tests pass.

---

## Task 2: Make Sync View Scope/Report-Based

**Files:**
- Modify: `apps/jira_workspace/views.py`
- Test: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Remove sync-page profile form imports**

In `apps/jira_workspace/views.py`, the `jira_workspace.forms` import must not include `JiraSyncProfileForm`, and the `sync_service` import must not include `ActiveFullSyncError`.

Expected import block:

```python
from jira_workspace.forms import (
    GlobalSyncPolicyForm,
    JiraConnectionForm,
    JiraIssueFilterForm,
    JiraSavedQueryForm,
    SyncScopeForm,
    Sync2PodProfileForm,
)
```

Expected sync service import:

```python
from jira_workspace.services.sync_service import (
    PRIMARY_GLOBAL_SYNC_POLICY_NAME,
    SyncService,
)
```

- [ ] **Step 2: Remove profile POST actions from `sync()`**

In `apps/jira_workspace/views.py`, `sync()` must not handle:

```python
elif action == "save_profile":
```

or:

```python
elif action == "run_sync":
```

Keep connection actions, policy actions, scope actions, and run-due action.

- [ ] **Step 3: Compute active sync state from current policy scopes**

After loading `policy_scopes` and `scope_sync_reports`, use this logic:

```python
active_scope_statuses = {
    SyncScope.RunStatus.QUEUED_FULL,
    SyncScope.RunStatus.RUNNING_FULL,
    SyncScope.RunStatus.QUEUED_INCREMENTAL,
    SyncScope.RunStatus.RUNNING_INCREMENTAL,
}
active_full_scope_statuses = {
    SyncScope.RunStatus.QUEUED_FULL,
    SyncScope.RunStatus.RUNNING_FULL,
}
has_active_sync = any(
    scope.last_run_status in active_scope_statuses for scope in policy_scopes
)
has_active_full_sync = any(
    scope.last_run_status in active_full_scope_statuses for scope in policy_scopes
)
sync_status = sync_service.build_sync_status()
```

Use `sync_status` only for external blocker / latest legacy failure messages:

```python
"latest_failed_run": sync_status["latest_failure"],
"jira_blocker_message": sync_status["blocker_message"],
"has_external_blocker": sync_status["has_external_blocker"],
```

- [ ] **Step 4: Remove profile context from `sync()`**

The `context` dict in `sync()` must not include:

```python
"profiles": profiles,
"sync_runs": sync_status["recent_runs"],
"profile_form": profile_form,
"selected_profile": selected_profile,
"starred_profile_ids": ...,
```

The operation logs context should be global Jira sync logs:

```python
"recent_operation_logs": operation_log_service.recent_logs(
    tool=OperationLog.Tool.JIRA_SYNC,
),
```

- [ ] **Step 5: Run sync view focused tests**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceSecondaryPagesTests -v 2
```

Expected before Task 3 updates: failures only in tests that still expect legacy profile UI/action behavior.

---

## Task 3: Convert Sync Template To Scope Reports

**Files:**
- Modify: `templates/jira_workspace/sync.html`
- Modify: `templates/jira_workspace/partials/sync_runs.html`
- Test: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Remove legacy profile panels from `sync.html`**

In `templates/jira_workspace/sync.html`, remove sections containing:

```html
<h2 class="section-title">Current Profile</h2>
<h2 class="section-title">Sync Controls</h2>
<h3 class="section-title">Profile Editor</h3>
<input type="hidden" name="action" value="run_sync">
<input type="hidden" name="action" value="save_profile">
data-sync-details-toggle="profile"
data-sync-details-panel="profile"
```

- [ ] **Step 2: Render latest status from `scope_sync_reports`**

Replace the latest status `{% with latest_run=sync_runs|first %}` block with:

```django
{% with latest_report=scope_sync_reports|first %}
  {% if latest_report %}
    <article class="recent-item">
      <div class="recent-item__top">
        <span class="issue-key">{{ latest_report.scope.name }}</span>
        <span class="issue-status">{{ latest_report.status }}</span>
      </div>
      <div class="recent-item__summary">
        v{{ latest_report.policy_version.version_no }} {{ latest_report.get_run_type_display }}
        fetched {{ latest_report.fetched_count }},
        inserted {{ latest_report.inserted_count }},
        updated {{ latest_report.updated_count }},
        unchanged {{ latest_report.unchanged_checked_count }}.
      </div>
    </article>
    {% if has_active_full_sync %}
      <p class="empty-state">A Jira full sync is already queued or running. Wait for it to finish before starting another Jira sync task.</p>
    {% endif %}
  {% elif has_external_blocker %}
    <article class="recent-item">
      <div class="recent-item__top">
        <span class="issue-key">External Jira access is currently blocked</span>
        <span class="issue-status">403</span>
      </div>
      <div class="recent-item__summary">{{ latest_failed_run.error_message }}</div>
    </article>
  {% else %}
    <p class="empty-state">No scope sync reports recorded yet.</p>
  {% endif %}
{% endwith %}
```

- [ ] **Step 3: Render summary from scope reports**

Replace summary loop:

```django
{% for run in sync_runs|slice:":5" %}
```

with:

```django
{% for report in scope_sync_reports|slice:":5" %}
```

and use:

```django
<span class="issue-key">{{ report.scope.name }}</span>
<span class="issue-status">{{ report.status }}</span>
v{{ report.policy_version.version_no }} {{ report.get_run_type_display }}
with {{ report.fetched_count }} fetched in {{ report.duration_ms }}ms.
```

- [ ] **Step 4: Change the history tab title**

In `templates/jira_workspace/sync.html`, change:

```html
<h3 class="section-title">Recent Sync Runs</h3>
```

to:

```html
<h3 class="section-title">Scope Report History</h3>
```

and include:

```django
{% include "jira_workspace/partials/sync_runs.html" with scope_sync_reports=scope_sync_reports %}
```

- [ ] **Step 5: Rewrite `partials/sync_runs.html` as scope-report table**

Replace `templates/jira_workspace/partials/sync_runs.html` with:

```django
<div class="table-wrap">
  <table class="ticket-table ticket-table--compact">
    <thead>
      <tr>
        <th scope="col">Scope</th>
        <th scope="col">Policy Version</th>
        <th scope="col">Run Type</th>
        <th scope="col">Status</th>
        <th scope="col">Started</th>
        <th scope="col">Finished</th>
        <th scope="col">Fetched</th>
        <th scope="col">Inserted</th>
        <th scope="col">Updated</th>
        <th scope="col">Unchanged</th>
        <th scope="col">Deactivated</th>
        <th scope="col">Duration</th>
        <th scope="col">Log</th>
      </tr>
    </thead>
    <tbody>
      {% for report in scope_sync_reports %}
        <tr>
          <td>{{ report.scope.name|default:"-" }}</td>
          <td>v{{ report.policy_version.version_no|default:"-" }}</td>
          <td>{{ report.get_run_type_display|default:report.run_type|default:"-" }}</td>
          <td><span class="status-pill status-pill--{{ report.status|default:'neutral' }}">{{ report.status|default:"-" }}</span></td>
          <td>{{ report.started_at|date:"Y-m-d H:i"|default:"-" }}</td>
          <td>{{ report.finished_at|date:"Y-m-d H:i"|default:"-" }}</td>
          <td>{{ report.fetched_count|default:0 }}</td>
          <td>{{ report.inserted_count|default:0 }}</td>
          <td>{{ report.updated_count|default:0 }}</td>
          <td>{{ report.unchanged_checked_count|default:0 }}</td>
          <td>{{ report.deactivated_membership_count|default:0 }}</td>
          <td>{{ report.duration_ms|default:0 }}ms</td>
          <td class="sync-run-log">{{ report.error_message|default:"-" }}</td>
        </tr>
      {% empty %}
        <tr>
          <td class="empty-state empty-state--cell" colspan="13">No scope sync reports recorded yet.</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

- [ ] **Step 6: Run template/view tests**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceSecondaryPagesTests apps.jira_workspace.tests.test_views.JiraWorkspaceStylesheetTests -v 2
```

Expected: failures identify tests still expecting profile UI; fix in Task 4.

---

## Task 4: Align View Tests With Scope/Report UI

**Files:**
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Remove profile UI positive assertions**

In sync-page tests, replace assertions expecting:

```python
assert "Current Profile" in content
assert "Sync Controls" in content
assert "Profile Editor" in content
assert 'name="action" value="run_sync"' in content
assert 'name="action" value="save_profile"' in content
assert 'data-sync-details-toggle="profile"' in content
assert 'data-sync-details-panel="profile"' in content
```

with assertions expecting the absence of profile controls and the presence of scope controls:

```python
assert "Current Profile" not in content
assert "Sync Controls" not in content
assert "Profile Editor" not in content
assert 'name="action" value="run_sync"' not in content
assert 'name="action" value="save_profile"' not in content
assert 'data-sync-details-toggle="profile"' not in content
assert 'data-sync-details-panel="profile"' not in content
assert "Policy Editor" in content
assert "Scope Report History" in content
assert "Scope Sync Reports" in content
```

- [ ] **Step 2: Remove sync-page profile action tests**

Delete or rewrite these sync-page tests:

```python
test_sync_page_can_persist_a_profile
test_sync_page_queues_incremental_sync
test_sync_page_queues_full_sync
test_sync_page_shows_error_when_full_run_blocks_new_enqueue
```

Do not delete `JiraSyncProfile` model/service tests outside the sync page.

- [ ] **Step 3: Replace running progress tests with scope status tests**

Replace tests that create `JiraSyncRun(status=RUNNING)` for sync page progress with a scope status setup:

```python
self.sync_scope.last_run_status = SyncScope.RunStatus.RUNNING_FULL
self.sync_scope.save(update_fields=["last_run_status", "updated_at"])
```

Expected assertions:

```python
assert 'data-sync-refresh="active"' in content
assert "A Jira full sync is already queued or running." in content
```

Do not assert legacy progress bar fields from `JiraSyncRun`.

- [ ] **Step 4: Update failed log test to use `JiraScopeSyncReport`**

Use:

```python
JiraScopeSyncReport.objects.create(
    policy_version=self.policy_version,
    scope=self.sync_scope,
    run_type=JiraScopeSyncReport.RunType.FULL,
    status=JiraScopeSyncReport.Status.FAILED,
    started_at=datetime.now(timezone.utc),
    finished_at=datetime.now(timezone.utc),
    effective_jql=self.sync_scope.base_jql,
    error_message="No active Jira connection is configured.",
)
```

Expected assertions:

```python
assert "<th scope=\"col\">Log</th>" in content
assert "No active Jira connection is configured." in content
assert "<th scope=\"col\">Profile</th>" not in content
```

- [ ] **Step 5: Update stylesheet hook test**

The hook test should assert:

```python
assert 'data-sync-summary-runs' in html
assert 'data-sync-details-toggle="history"' in html
assert 'data-sync-details-toggle="scope-reports"' in html
assert 'data-sync-details-toggle="policy"' in html
assert 'data-sync-details-toggle="profile"' not in html
```

- [ ] **Step 6: Run focused view tests**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views -v 2
```

Expected: all view tests pass.

---

## Task 5: Full Verification

**Files:**
- No source edits unless verification fails.

- [ ] **Step 1: Run focused implementation tests**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_sync_policy_models apps.jira_workspace.tests.test_sync_policy_migration apps.jira_workspace.tests.test_sync_service apps.jira_workspace.tests.test_query_service apps.jira_workspace.tests.test_views -v 1
```

Expected: all tests pass.

- [ ] **Step 2: Run full Jira workspace test suite**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests -v 2
```

Expected: all tests pass. Current latest known failure before this finish plan was a stale sync command-center hook assertion; after Task 4 it should pass.

- [ ] **Step 3: Run Django system check**

Run:

```bash
./.venv/bin/python manage.py check
```

Expected:

```text
System check identified no issues (0 silenced).
```

- [ ] **Step 4: Run migration dry-run**

Run:

```bash
./.venv/bin/python manage.py makemigrations --check --dry-run
```

Expected:

```text
No changes detected
```

- [ ] **Step 5: Run whitespace diff check**

Run:

```bash
git diff --check -- apps/jira_workspace/migrations/0011_global_sync_policy.py apps/jira_workspace/services/query_service.py apps/jira_workspace/services/sync_service.py apps/jira_workspace/tests/test_query_service.py apps/jira_workspace/tests/test_sync_policy_migration.py apps/jira_workspace/tests/test_sync_service.py apps/jira_workspace/tests/test_views.py apps/jira_workspace/views.py templates/jira_workspace/sync.html static/jira_workspace/jira.css
```

Expected: no output and exit code 0.

---

## Task 6: Review Gates

**Files:**
- Review only unless findings require fixes.

- [ ] **Step 1: Spec compliance review checklist**

Verify:

```text
- Primary policy identity is fixed to "Primary Jira Policy".
- `save_policy` cannot rename the primary policy.
- `rebuild_policy` rejects secondary policies.
- `run_scope_full` and `run_scope_incremental` reject stale-version scopes.
- `run_due_scopes()` runs only current primary-policy scopes.
- Query reads return empty while current policy version is rebuilding.
- Sync page does not render profile save/run controls.
- Sync page report/history surfaces show scope/version attribution.
```

- [ ] **Step 2: Code quality review checklist**

Verify:

```text
- No dead imports in `views.py`.
- No unreachable template variables in `sync.html`.
- No N+1 query introduced beyond the existing page shape.
- No unrelated file changes staged.
- Tests assert behavior rather than implementation where feasible.
- The migration backfill is deterministic and does not create duplicate primary policies for empty DBs.
```

- [ ] **Step 3: Fix review findings**

If review finds issues, patch only relevant files, then repeat Task 5 and Task 6.

---

## Task 7: Commit The Atomic Change Set

**Files:**
- Stage only the 10 Jira global-sync files listed in Current State Snapshot.

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short
```

Expected: unrelated files may remain dirty/untracked, but only Jira global-sync files should be staged after Step 2.

- [ ] **Step 2: Stage only relevant files**

Run:

```bash
git add \
  apps/jira_workspace/migrations/0011_global_sync_policy.py \
  apps/jira_workspace/services/query_service.py \
  apps/jira_workspace/services/sync_service.py \
  apps/jira_workspace/tests/test_query_service.py \
  apps/jira_workspace/tests/test_sync_policy_migration.py \
  apps/jira_workspace/tests/test_sync_service.py \
  apps/jira_workspace/tests/test_views.py \
  apps/jira_workspace/views.py \
  templates/jira_workspace/sync.html \
  static/jira_workspace/jira.css
```

- [ ] **Step 3: Confirm staged file list**

Run:

```bash
git diff --cached --name-only
```

Expected exactly:

```text
apps/jira_workspace/migrations/0011_global_sync_policy.py
apps/jira_workspace/services/query_service.py
apps/jira_workspace/services/sync_service.py
apps/jira_workspace/tests/test_query_service.py
apps/jira_workspace/tests/test_sync_policy_migration.py
apps/jira_workspace/tests/test_sync_service.py
apps/jira_workspace/tests/test_views.py
apps/jira_workspace/views.py
static/jira_workspace/jira.css
templates/jira_workspace/sync.html
```

- [ ] **Step 4: Commit**

Run:

```bash
git commit -m "Implement Jira global sync policy flow"
```

Expected: commit succeeds and prints a commit hash.

- [ ] **Step 5: Record final status**

Run:

```bash
git status --short
```

Expected: unrelated dirty/untracked files may remain; no staged Jira global-sync files remain.

---

## Decision Summary

- Available options: restore legacy profile UI compatibility vs fully replace main sync UI with global policy/scope.
- Chosen option: fully replace main sync UI with global policy/scope.
- Selection: auto-selected for this finish plan based on the latest spec-review finding and the original plan goal.
- Reason: keeping both profile run UI and scope report UI creates contradictory tests and an unclear product model; legacy models can remain without being the main command-center interaction.

## Stop Conditions

Stop only when:

1. All tasks above are completed and the atomic commit exists; or
2. Remaining failures are blocked by missing user input or external system behavior that cannot be fixed locally.

If a test fails, do not stop by default. Treat it as retryable unless it reveals a genuine product-decision conflict.
