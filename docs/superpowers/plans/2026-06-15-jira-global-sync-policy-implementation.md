# Jira Global Sync Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current profile-centric Jira sync flow with one global policy, versioned rebuild semantics, scope-level incremental sync, active membership tracking, and productized sync status/reporting.

**Architecture:** Keep `JiraIssue` as the shared local cache, but add a global policy root, version rows, and independently scheduled child scopes. Move sync execution from "run one profile" to "build one policy version and then increment individual scopes," while query and dashboard views read only the current policy version's active memberships by default.

**Tech Stack:** Django 3.2, existing `jira_workspace` app, SQLite test database, server-rendered templates, current `jira_adapter` / `sync_service` / `query_service` stack, vanilla JavaScript, existing workspace CSS shell.

---

## File Map

- Modify `apps/jira_workspace/models.py`: add the global policy, policy version, scope, membership, and sync report models/fields.
- Create `apps/jira_workspace/migrations/0011_global_sync_policy.py`: persist the new sync architecture.
- Modify `apps/jira_workspace/forms.py`: replace profile editing with global policy + scope editing forms.
- Modify `apps/jira_workspace/services/sync_service.py`: implement policy version rebuilds, scope full sync, scope incremental sync, cursor overlap, and report writing.
- Modify `apps/jira_workspace/services/query_service.py`: make cache queries membership-aware and current-policy-aware.
- Modify `apps/jira_workspace/services/stats_service.py`: make dashboard aggregates read only active tickets in the current policy.
- Modify `apps/jira_workspace/services/workspace_service.py`: surface new global sync health summary if needed.
- Modify `apps/jira_workspace/views.py`: replace profile-based sync page actions with policy, scope, rebuild, run-due, and report flows.
- Modify `apps/jira_workspace/urls.py`: add any new sync report or scope action routes if separate endpoints are required.
- Modify `templates/jira_workspace/sync.html`: add global status bar, scope cards, policy editor, and run/report surfaces.
- Modify `templates/jira_workspace/partials/sync_runs.html`: display new report fields and scope/version attribution.
- Modify `templates/jira_workspace/dashboard.html`: surface global cache trust and latest alignment state.
- Modify `templates/jira_workspace/queries.html`: surface current cache status and active-policy-only semantics.
- Modify `static/jira_workspace/jira.css`: style the new sync status bar, scope cards, and report metadata.
- Add `apps/jira_workspace/tests/test_sync_policy_models.py`: focused tests for new policy/version/scope model rules.
- Modify `apps/jira_workspace/tests/test_sync_service.py`: cover rebuilds, incremental overlap, inactive memberships, and report counts.
- Modify `apps/jira_workspace/tests/test_query_service.py`: cover current-policy active-membership filtering.
- Modify `apps/jira_workspace/tests/test_workspace_service.py`: cover global sync health summary if added there.
- Modify `apps/jira_workspace/tests/test_views.py`: cover policy editor, scope actions, status surfaces, and report rendering.

## Task 1: Add the Global Policy, Version, Scope, and Membership Models

**Files:**
- Modify: `apps/jira_workspace/models.py`
- Create: `apps/jira_workspace/migrations/0011_global_sync_policy.py`
- Test: `apps/jira_workspace/tests/test_sync_policy_models.py`

- [ ] **Step 1: Write the failing model tests**

```python
from django.test import TestCase
from django.utils import timezone

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
    SyncScope,
)


class JiraGlobalSyncPolicyModelTests(TestCase):
    def test_policy_creates_single_current_version_pointer(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-v1",
            status=GlobalSyncPolicy.Status.STALE,
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=1,
            strategy_hash="hash-v1",
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )
        policy.current_version = version
        policy.save(update_fields=["current_version", "updated_at"])

        policy.refresh_from_db()
        assert policy.current_version_id == version.id

    def test_self_scope_is_marked_required_and_system_managed(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-v1",
            status=GlobalSyncPolicy.Status.STALE,
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=1,
            strategy_hash="hash-v1",
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )

        scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.SELF_REQUIRED,
            name="My Assigned or Reported Issues",
            is_required=True,
            is_enabled=True,
            is_system_scope=True,
            schedule_minutes=30,
            config_json={"mode": "self"},
            base_jql="assignee = currentUser() OR reporter = currentUser() ORDER BY updated DESC",
            next_run_at=timezone.now(),
        )

        assert scope.is_required is True
        assert scope.is_system_scope is True

    def test_issue_membership_can_be_marked_inactive_without_deleting_issue(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-v1",
            status=GlobalSyncPolicy.Status.READY,
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=1,
            strategy_hash="hash-v1",
            status=GlobalSyncPolicyVersion.Status.READY,
            full_sync_required=False,
        )
        scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="OPS",
            is_required=False,
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "OPS"},
            base_jql='project = "OPS" ORDER BY updated DESC',
            next_run_at=timezone.now(),
        )
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Escalate blocker handling",
            status="Blocked",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=timezone.now(),
            raw_json="{}",
            last_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )

        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        issue.refresh_from_db()

        assert JiraIssue.objects.filter(issue_key="OPS-778").exists()
        assert JiraIssueScopeMembership.objects.get(pk=membership.pk).is_active is False
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_sync_policy_models -v 2
```

Expected: fail because the new policy/version/scope models and issue freshness fields do not exist.

- [ ] **Step 3: Add the minimal models, enums, and migration**

```python
class GlobalSyncPolicy(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        REBUILDING = "rebuilding", "Rebuilding"
        PARTIAL = "partial", "Partial"
        STALE = "stale", "Stale"

    name = models.CharField(max_length=120, unique=True)
    strategy_json = models.JSONField(default=dict, blank=True)
    strategy_hash = models.CharField(max_length=64, db_index=True)
    current_version = models.ForeignKey(
        "GlobalSyncPolicyVersion",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.STALE)
    last_strategy_changed_at = models.DateTimeField(blank=True, null=True)
    last_version_built_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GlobalSyncPolicyVersion(models.Model):
    class Status(models.TextChoices):
        PENDING_FULL_SYNC = "pending_full_sync", "Pending Full Sync"
        BUILDING = "building", "Building"
        READY = "ready", "Ready"
        PARTIAL_FAILED = "partial_failed", "Partial Failed"
        STALE = "stale", "Stale"

    policy = models.ForeignKey(GlobalSyncPolicy, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    strategy_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_FULL_SYNC)
    full_sync_required = models.BooleanField(default=True)
    full_sync_started_at = models.DateTimeField(blank=True, null=True)
    full_sync_completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "version_no"], name="jira_workspace_policy_version_unique"),
        ]


class SyncScope(models.Model):
    class ScopeType(models.TextChoices):
        SELF_REQUIRED = "self_required", "Self Required"
        ASSIGNEE_USER = "assignee_user", "Assignee User"
        REPORTER_USER = "reporter_user", "Reporter User"
        PROJECT = "project", "Project"
        LABEL = "label", "Label"
        SPRINT = "sprint", "Sprint"
        CUSTOM_JQL = "custom_jql", "Custom JQL"

    class RunStatus(models.TextChoices):
        IDLE = "idle", "Idle"
        QUEUED_FULL = "queued_full", "Queued Full"
        RUNNING_FULL = "running_full", "Running Full"
        QUEUED_INCREMENTAL = "queued_incremental", "Queued Incremental"
        RUNNING_INCREMENTAL = "running_incremental", "Running Incremental"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"

    policy_version = models.ForeignKey(GlobalSyncPolicyVersion, on_delete=models.CASCADE, related_name="scopes")
    scope_type = models.CharField(max_length=32, choices=ScopeType.choices)
    name = models.CharField(max_length=120)
    is_required = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    is_system_scope = models.BooleanField(default=False)
    schedule_minutes = models.PositiveIntegerField(default=30)
    config_json = models.JSONField(default=dict, blank=True)
    base_jql = models.TextField()
    effective_jql_last_run = models.TextField(blank=True, default="")
    last_full_sync_at = models.DateTimeField(blank=True, null=True)
    last_incremental_sync_at = models.DateTimeField(blank=True, null=True)
    last_successful_check_at = models.DateTimeField(blank=True, null=True)
    last_issue_updated_cursor = models.CharField(max_length=128, blank=True, null=True)
    last_run_status = models.CharField(max_length=32, choices=RunStatus.choices, default=RunStatus.IDLE)
    last_error_message = models.TextField(blank=True, default="")
    next_run_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Also extend `JiraIssue` and `JiraIssueScopeMembership` in `models.py`, and write a migration that creates the new tables and backfills sensible defaults for existing rows.

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit the model layer**

```bash
git add apps/jira_workspace/models.py apps/jira_workspace/migrations/0011_global_sync_policy.py apps/jira_workspace/tests/test_sync_policy_models.py
git commit -m "feat: add jira global sync policy models"
```

## Task 2: Replace Profile-Centric Sync Execution With Policy Versions and Scope Runs

**Files:**
- Modify: `apps/jira_workspace/services/sync_service.py`
- Modify: `apps/jira_workspace/tests/test_sync_service.py`
- Test: `apps/jira_workspace/tests/test_sync_policy_models.py`

- [ ] **Step 1: Write the failing sync-service tests**

```python
def test_policy_change_creates_new_version_and_queues_full_scopes(self):
    policy = GlobalSyncPolicy.objects.create(
        name="Primary Jira Policy",
        strategy_json={"required_self": True, "scopes": []},
        strategy_hash="hash-v1",
        status=GlobalSyncPolicy.Status.READY,
    )
    service = SyncService(jira_adapter=self.adapter)

    version = service.apply_policy_strategy(
        policy=policy,
        strategy_json={
            "required_self": True,
            "scopes": [{"scope_type": "project", "name": "OPS", "project_key": "OPS"}],
        },
    )

    policy.refresh_from_db()
    assert version.version_no == 1
    assert version.status == GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC
    assert policy.status == GlobalSyncPolicy.Status.STALE
    assert version.scopes.filter(last_run_status=SyncScope.RunStatus.QUEUED_FULL).count() == 2


def test_incremental_scope_sync_uses_cursor_overlap_and_updates_success_time_for_unchanged_issue(self):
    policy, version, scope = build_ready_self_scope()
    issue = JiraIssue.objects.create(
        issue_key="OPS-778",
        project_key="OPS",
        summary="Escalate blocker handling",
        status="Blocked",
        assignee="xchen17",
        reporter="amy",
        priority="High",
        updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        raw_json='{"key":"OPS-778"}',
        last_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        is_active_in_current_policy=True,
        first_seen_policy_version_id=version.id,
        last_seen_policy_version_id=version.id,
    )
    JiraIssueScopeMembership.objects.create(
        issue=issue,
        scope=scope,
        policy_version=version,
        first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
        last_seen_issue_updated_at=issue.updated_at,
        is_active=True,
    )
    scope.last_issue_updated_cursor = "2026-06-15T01:05:00+00:00"
    scope.save(update_fields=["last_issue_updated_cursor", "updated_at"])
    self.adapter.fetch_issues.return_value = [build_issue_payload(key="OPS-778", updated_at="2026-06-15T01:00:00+00:00")]

    result = SyncService(jira_adapter=self.adapter).run_scope_incremental(scope)

    issue.refresh_from_db()
    assert 'updated >=' in scope.effective_jql_last_run or 'updated >=' in SyncScope.objects.get(pk=scope.pk).effective_jql_last_run
    assert result.unchanged_checked_count == 1
    assert issue.last_synced_success_at > datetime.fromisoformat("2026-06-15T01:00:00+00:00")
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_sync_service -v 2
```

Expected: fail because the service still expects `JiraSyncProfile` as the execution root.

- [ ] **Step 3: Implement the minimal policy/scope execution flow**

```python
class SyncService:
    CURSOR_OVERLAP_MINUTES = 5

    def apply_policy_strategy(self, *, policy, strategy_json):
        normalized = self._normalize_strategy(strategy_json)
        strategy_hash = self._hash_strategy(normalized)
        if strategy_hash == policy.strategy_hash:
            return policy.current_version

        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=self._next_version_number(policy),
            strategy_hash=strategy_hash,
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )
        self._create_scopes_for_version(version, normalized)
        policy.strategy_json = normalized
        policy.strategy_hash = strategy_hash
        policy.current_version = version
        policy.status = GlobalSyncPolicy.Status.STALE
        policy.last_strategy_changed_at = timezone.now()
        policy.save(
            update_fields=[
                "strategy_json",
                "strategy_hash",
                "current_version",
                "status",
                "last_strategy_changed_at",
                "updated_at",
            ]
        )
        return version

    def run_scope_incremental(self, scope):
        if not scope.last_full_sync_at:
            raise ValueError("Incremental sync requires a prior full sync for this scope.")
        effective_jql = self._build_incremental_jql(scope.base_jql, scope.last_issue_updated_cursor)
        items = self._jira_client().fetch_issues(effective_jql)
        return self._store_scope_items(scope=scope, items=items, run_type="incremental", effective_jql=effective_jql)
```

Update `_store_scope_items()` to:

- upsert `JiraIssue`
- update `last_checked_at` and `last_synced_success_at` even for unchanged hits
- update `JiraIssueScopeMembership`
- mark scope-missing rows inactive on full sync
- compute report counters for inserted, updated, unchanged, and deactivated memberships

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit the sync execution layer**

```bash
git add apps/jira_workspace/services/sync_service.py apps/jira_workspace/tests/test_sync_service.py apps/jira_workspace/tests/test_sync_policy_models.py
git commit -m "feat: add policy version and scope sync execution"
```

## Task 3: Make Query and Dashboard Reads Current-Policy and Active-Membership Aware

**Files:**
- Modify: `apps/jira_workspace/services/query_service.py`
- Modify: `apps/jira_workspace/services/stats_service.py`
- Modify: `apps/jira_workspace/tests/test_query_service.py`
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing query-layer tests**

```python
def test_build_issue_queryset_excludes_inactive_membership_rows_by_default(self):
    active_issue, inactive_issue, version = build_policy_scoped_issues()

    queryset = build_issue_queryset(username="xchen17")

    assert list(queryset.values_list("issue_key", flat=True)) == [active_issue.issue_key]


def test_build_issue_filter_options_counts_only_current_policy_active_issues(self):
    build_policy_scoped_issues()

    options = build_issue_filter_options(username="xchen17")

    assert options["project_options"] == ["OPS"]
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_query_service -v 2
```

Expected: fail because query helpers currently read raw `JiraIssue.objects.all()`.

- [ ] **Step 3: Implement membership-aware query helpers**

```python
def _active_policy_issue_queryset():
    policy = GlobalSyncPolicy.objects.select_related("current_version").first()
    if not policy or not policy.current_version_id:
        return JiraIssue.objects.none()
    return JiraIssue.objects.filter(
        is_active_in_current_policy=True,
        sync_memberships__policy_version_id=policy.current_version_id,
        sync_memberships__is_active=True,
    ).distinct()


def build_issue_queryset(...):
    queryset = _active_policy_issue_queryset()
    ...
    return queryset.order_by(ordering)
```

Update the dashboard summary and project-group builders to use the same active-policy base queryset.

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit the query-layer changes**

```bash
git add apps/jira_workspace/services/query_service.py apps/jira_workspace/services/stats_service.py apps/jira_workspace/tests/test_query_service.py apps/jira_workspace/tests/test_views.py
git commit -m "feat: scope jira cache queries to active policy memberships"
```

## Task 4: Replace the Sync UI With Global Policy, Scope Cards, and Run Reports

**Files:**
- Modify: `apps/jira_workspace/forms.py`
- Modify: `apps/jira_workspace/views.py`
- Modify: `apps/jira_workspace/urls.py`
- Modify: `templates/jira_workspace/sync.html`
- Modify: `templates/jira_workspace/partials/sync_runs.html`
- Modify: `static/jira_workspace/jira.css`
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing view tests**

```python
def test_sync_page_renders_global_policy_status_and_scope_cards(self):
    response = self.client.get(reverse("jira_workspace:sync"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Global Sync Policy" in content
    assert "Current Policy Version" in content
    assert "Required Scopes" in content
    assert "Run Due Scopes" in content


def test_sync_post_can_rebuild_current_version(self):
    policy = build_primary_policy_with_scope()

    response = self.client.post(
        reverse("jira_workspace:sync"),
        {"action": "rebuild_policy", "policy_id": str(policy.id)},
    )

    assert response.status_code == 302
    policy.refresh_from_db()
    assert policy.status in {GlobalSyncPolicy.Status.STALE, GlobalSyncPolicy.Status.REBUILDING}


def test_sync_post_can_run_scope_incremental(self):
    scope = build_ready_scope()

    response = self.client.post(
        reverse("jira_workspace:sync"),
        {"action": "run_scope_incremental", "scope_id": str(scope.id)},
    )

    assert response.status_code == 302
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceSecondaryPagesTests -v 2
```

Expected: fail because the page still renders profile controls and profile-based run actions.

- [ ] **Step 3: Implement the minimal UI and action flow**

```python
class GlobalSyncPolicyForm(forms.ModelForm):
    class Meta:
        model = GlobalSyncPolicy
        fields = ["name"]


class SyncScopeForm(forms.Form):
    scope_type = forms.ChoiceField(choices=SyncScope.ScopeType.choices)
    name = forms.CharField(max_length=120)
    schedule_minutes = forms.IntegerField(min_value=5, initial=30)
    project_key = forms.CharField(required=False, max_length=32)
    label_name = forms.CharField(required=False, max_length=64)
    sprint_name = forms.CharField(required=False, max_length=120)
    custom_jql = forms.CharField(required=False)
```

Update `views.sync()` to:

- load or initialize the single `GlobalSyncPolicy`
- render current policy version status
- list scopes grouped by required and optional
- handle actions:
  - `save_policy`
  - `add_scope`
  - `rebuild_policy`
  - `run_due_scopes`
  - `run_scope_full`
  - `run_scope_incremental`

Update `sync.html` to replace profile cards with:

- one global status bar
- one policy editor
- one scope list with status cards
- one report table using updated run fields

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit the sync UI**

```bash
git add apps/jira_workspace/forms.py apps/jira_workspace/views.py apps/jira_workspace/urls.py templates/jira_workspace/sync.html templates/jira_workspace/partials/sync_runs.html static/jira_workspace/jira.css apps/jira_workspace/tests/test_views.py
git commit -m "feat: replace jira sync profiles with global policy ui"
```

## Task 5: Surface Cache Trust and Freshness on Dashboard and Query Pages

**Files:**
- Modify: `apps/jira_workspace/views.py`
- Modify: `templates/jira_workspace/dashboard.html`
- Modify: `templates/jira_workspace/queries.html`
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing page tests**

```python
def test_dashboard_surfaces_current_cache_alignment_status(self):
    build_stale_policy_with_failed_required_scope()

    response = self.client.get(reverse("jira_workspace:dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Cache Alignment" in content
    assert "Stale" in content
    assert "Required scope failure" in content


def test_query_page_surfaces_active_policy_ticket_freshness(self):
    build_ready_policy_with_active_issue()

    response = self.client.get(reverse("jira_workspace:query"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Current Policy Version" in content
    assert "Last Successful Check" in content
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views -v 2
```

Expected: fail because the pages do not yet expose policy freshness metadata.

- [ ] **Step 3: Implement the minimal freshness surfaces**

```python
def _build_policy_status_context():
    policy = GlobalSyncPolicy.objects.select_related("current_version").first()
    if not policy or not policy.current_version_id:
        return {"sync_policy": None, "sync_policy_version": None, "sync_required_failures": []}
    version = policy.current_version
    failed_required_scopes = list(
        version.scopes.filter(is_required=True, last_run_status__in=[SyncScope.RunStatus.FAILED, SyncScope.RunStatus.BLOCKED])
    )
    return {
        "sync_policy": policy,
        "sync_policy_version": version,
        "sync_required_failures": failed_required_scopes,
    }
```

Include this context in dashboard and query responses, and render:

- policy status pill
- version number
- latest global alignment timestamp
- required failure summary
- ticket freshness fields in the query detail surface

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit the cache-freshness surfaces**

```bash
git add apps/jira_workspace/views.py templates/jira_workspace/dashboard.html templates/jira_workspace/queries.html apps/jira_workspace/tests/test_views.py
git commit -m "feat: add jira cache trust and freshness surfaces"
```

## Task 6: Verify the End-to-End Policy Sync Flow

**Files:**
- No code changes
- Test: `apps/jira_workspace/tests`

- [ ] **Step 1: Run focused policy-sync tests**

Run:

```bash
./.venv/bin/python manage.py test \
  apps.jira_workspace.tests.test_sync_policy_models \
  apps.jira_workspace.tests.test_sync_service \
  apps.jira_workspace.tests.test_query_service \
  apps.jira_workspace.tests.test_views -v 2
```

Expected: pass.

- [ ] **Step 2: Run the full Jira workspace suite**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests -v 2
```

Expected: pass.

- [ ] **Step 3: Run Django checks and migration verification**

Run:

```bash
./.venv/bin/python manage.py check
./.venv/bin/python manage.py makemigrations --check --dry-run
```

Expected: no system-check issues and no missing migrations.

- [ ] **Step 4: Commit the verified implementation**

```bash
git add apps/jira_workspace templates/jira_workspace static/jira_workspace docs/superpowers/plans/2026-06-15-jira-global-sync-policy-implementation.md
git commit -m "feat: implement jira global sync policy workflow"
```

## Self-Review Notes

Spec coverage:

- global policy and policy version model: Task 1
- version-triggered full rebuild semantics: Task 2
- scope-level incremental sync with overlap and unchanged-success timestamps: Task 2
- active membership query semantics: Task 3
- global status bar, scope cards, and execution reports: Task 4
- dashboard/query freshness and cache trust display: Task 5
- verification and migration checks: Task 6

Placeholder scan:

- no `TBD`, `TODO`, `implement later`, or implied "write tests" placeholders remain
- each task includes file targets, concrete tests, commands, and implementation direction

Type consistency:

- `GlobalSyncPolicy`, `GlobalSyncPolicyVersion`, `SyncScope`, and `JiraIssueScopeMembership` are used consistently across tasks
- `last_synced_success_at`, `last_checked_at`, `current_version`, and `effective_jql_last_run` are referenced with one name throughout
