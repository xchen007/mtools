# Jira Workspace Implementation Plan

Current-state note, 2026-06-14: this early implementation plan is complete and superseded by later workspace migration, rich table, UI polish, and Query Card workbench plans. Use `docs/superpowers/plans/STATUS.md` and `README.md` for current routes, navigation, and verification status.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Django-backed Jira workspace inside `mtools` with local issue caching, profile-driven sync, a personal dashboard, a saved-query workspace, and profile/sync management.

**Architecture:** Create a new Django app package named `jira_workspace` under `apps/` to avoid colliding with the third-party `jira` package name. Persist all Jira cache and configuration data in the main Django SQLite database, sync Jira issues into local models through a small REST adapter, and render the UI with Django templates plus a thin layer of vanilla JavaScript for asynchronous ticket-table refreshes.

**Tech Stack:** Django 3.2, SQLite, Django test runner, `requests`, Django templates, vanilla JavaScript, existing `static/` and `templates/` support in `mtools`.

---

## File Structure

### New files

- `apps/jira_workspace/__init__.py`
- `apps/jira_workspace/apps.py`
- `apps/jira_workspace/admin.py`
- `apps/jira_workspace/forms.py`
- `apps/jira_workspace/models.py`
- `apps/jira_workspace/urls.py`
- `apps/jira_workspace/views.py`
- `apps/jira_workspace/services/__init__.py`
- `apps/jira_workspace/services/jira_adapter.py`
- `apps/jira_workspace/services/query_service.py`
- `apps/jira_workspace/services/stats_service.py`
- `apps/jira_workspace/services/sync_service.py`
- `apps/jira_workspace/migrations/__init__.py`
- `apps/jira_workspace/migrations/0001_initial.py`
- `apps/jira_workspace/tests/__init__.py`
- `apps/jira_workspace/tests/test_app_boot.py`
- `apps/jira_workspace/tests/test_models.py`
- `apps/jira_workspace/tests/test_query_service.py`
- `apps/jira_workspace/tests/test_sync_service.py`
- `apps/jira_workspace/tests/test_views.py`
- `templates/jira_workspace/base.html`
- `templates/jira_workspace/dashboard.html`
- `templates/jira_workspace/queries.html`
- `templates/jira_workspace/profiles.html`
- `templates/jira_workspace/partials/ticket_table.html`
- `templates/jira_workspace/partials/project_groups.html`
- `templates/jira_workspace/partials/query_library.html`
- `templates/jira_workspace/partials/sync_runs.html`
- `static/jira_workspace/jira.css`
- `static/jira_workspace/jira.js`

### Modified files

- `mtools/settings.py`
- `mtools/urls.py`

### Responsibilities

- `models.py`: local Jira cache, sync profile/run records, saved query definitions.
- `jira_adapter.py`: low-level Jira REST search and user-identity resolution.
- `sync_service.py`: full and incremental sync into local cache plus run logging.
- `query_service.py`: reusable filtered issue query building for dashboard and saved queries.
- `stats_service.py`: dashboard-specific aggregations and project-group building.
- `forms.py`: profile and saved-query validation without duplicating parsing logic in views.
- `views.py`: HTML pages plus partial endpoints for async table refresh and sync actions.
- `jira.js`: click handlers for project groups, range chips, and partial refreshes.

---

### Task 1: Scaffold the `jira_workspace` app and wire a dashboard route

**Files:**
- Create: `apps/jira_workspace/__init__.py`
- Create: `apps/jira_workspace/apps.py`
- Create: `apps/jira_workspace/urls.py`
- Create: `apps/jira_workspace/views.py`
- Create: `apps/jira_workspace/tests/__init__.py`
- Create: `apps/jira_workspace/tests/test_app_boot.py`
- Modify: `mtools/settings.py`
- Modify: `mtools/urls.py`

- [ ] **Step 1: Write the failing smoke test**

```python
# apps/jira_workspace/tests/test_app_boot.py
from django.test import SimpleTestCase
from django.urls import reverse


class JiraWorkspaceBootTests(SimpleTestCase):
    def test_dashboard_route_resolves_and_returns_ok(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        assert b"Jira Dashboard" in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.jira_workspace.tests.test_app_boot.JiraWorkspaceBootTests.test_dashboard_route_resolves_and_returns_ok -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'jira_workspace'` or `NoReverseMatch`.

- [ ] **Step 3: Write the minimal app wiring**

```python
# apps/jira_workspace/apps.py
from django.apps import AppConfig


class JiraWorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jira_workspace"
```

```python
# apps/jira_workspace/views.py
from django.http import HttpResponse


def dashboard(request):
    return HttpResponse("Jira Dashboard")
```

```python
# apps/jira_workspace/urls.py
from django.urls import path

from . import views

app_name = "jira_workspace"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
]
```

```python
# mtools/settings.py
INSTALLED_APPS = [
    # ...
    "jira_workspace",
    "rest_auth",
    "rest_framework.authtoken",
]
```

```python
# mtools/urls.py
urlpatterns = [
    path("admin/", admin.site.urls),
    path("jira/", include("jira_workspace.urls", namespace="jira_workspace")),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.jira_workspace.tests.test_app_boot.JiraWorkspaceBootTests.test_dashboard_route_resolves_and_returns_ok -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mtools/settings.py mtools/urls.py apps/jira_workspace
git commit -m "feat: scaffold jira workspace app"
```

### Task 2: Add local Jira data models and the initial migration

**Files:**
- Create: `apps/jira_workspace/models.py`
- Create: `apps/jira_workspace/migrations/__init__.py`
- Create: `apps/jira_workspace/migrations/0001_initial.py`
- Create: `apps/jira_workspace/tests/test_models.py`
- Modify: `apps/jira_workspace/admin.py`

- [ ] **Step 1: Write the failing model tests**

```python
# apps/jira_workspace/tests/test_models.py
from django.test import TestCase

from jira_workspace.models import JiraIssue, JiraSavedQuery, JiraSyncProfile


class JiraWorkspaceModelTests(TestCase):
    def test_issue_string_representation_uses_issue_key(self):
        issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="In Progress",
            assignee="xchen17",
            reporter="xchen17",
            updated_at="2026-06-11T10:00:00+00:00",
            created_at="2026-06-10T10:00:00+00:00",
            raw_json="{}",
            last_seen_at="2026-06-11T10:00:00+00:00",
        )

        assert str(issue) == "TESS-321"

    def test_default_profile_flag_can_be_saved(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
            is_default=True,
        )

        assert profile.is_default is True

    def test_saved_query_defaults_to_not_starred_and_not_pinned(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
        )
        query = JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=profile,
            filters_json={"status": ["Blocked"]},
        )

        assert query.is_starred is False
        assert query.is_pinned is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests.test_models.JiraWorkspaceModelTests -v 2`
Expected: FAIL with `ImportError` or `OperationalError` because the models and tables do not exist.

- [ ] **Step 3: Write the models, register them in admin, and create the initial migration**

```python
# apps/jira_workspace/models.py
from django.db import models


class JiraIssue(models.Model):
    issue_key = models.CharField(max_length=32, primary_key=True)
    project_key = models.CharField(max_length=32, db_index=True)
    summary = models.TextField()
    status = models.CharField(max_length=64, db_index=True)
    assignee = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    reporter = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    priority = models.CharField(max_length=64, blank=True, null=True)
    sprint = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(blank=True, null=True)
    raw_json = models.TextField()
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.issue_key


class JiraIssueMetric(models.Model):
    issue = models.OneToOneField(JiraIssue, on_delete=models.CASCADE, related_name="metrics")
    cycle_time_minutes = models.IntegerField(blank=True, null=True)
    worklog_minutes = models.IntegerField(blank=True, null=True)
    status_changed_at = models.DateTimeField(blank=True, null=True)


class JiraSyncProfile(models.Model):
    class ProfileType(models.TextChoices):
        MY_ISSUES = "my_issues", "My Issues"
        PROJECT = "project", "Project"
        CUSTOM_JQL = "custom_jql", "Custom JQL"

    name = models.CharField(max_length=120, unique=True)
    profile_type = models.CharField(max_length=32, choices=ProfileType.choices)
    params_json = models.JSONField(default=dict, blank=True)
    jql = models.TextField()
    is_default = models.BooleanField(default=False)
    last_cursor = models.CharField(max_length=128, blank=True, null=True)
    last_full_sync_at = models.DateTimeField(blank=True, null=True)
    last_incremental_sync_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class JiraSyncRun(models.Model):
    class RunType(models.TextChoices):
        FULL = "full", "Full"
        INCREMENTAL = "incremental", "Incremental"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    profile = models.ForeignKey(JiraSyncProfile, on_delete=models.CASCADE, related_name="sync_runs")
    run_type = models.CharField(max_length=32, choices=RunType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    fetched_count = models.IntegerField(default=0)
    inserted_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)


class JiraSavedQuery(models.Model):
    name = models.CharField(max_length=120, unique=True)
    profile = models.ForeignKey(JiraSyncProfile, on_delete=models.CASCADE, related_name="saved_queries")
    description = models.TextField(blank=True)
    filters_json = models.JSONField(default=dict, blank=True)
    jql_text = models.TextField(blank=True)
    is_starred = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    sort_by = models.CharField(max_length=32, default="updated_at")
    sort_order = models.CharField(max_length=8, default="desc")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
```

```python
# apps/jira_workspace/admin.py
from django.contrib import admin

from .models import JiraIssue, JiraIssueMetric, JiraSavedQuery, JiraSyncProfile, JiraSyncRun

admin.site.register(JiraIssue)
admin.site.register(JiraIssueMetric)
admin.site.register(JiraSyncProfile)
admin.site.register(JiraSyncRun)
admin.site.register(JiraSavedQuery)
```

Run: `python manage.py makemigrations jira_workspace`
Expected generated migration operations: create `JiraIssue`, `JiraIssueMetric`, `JiraSyncProfile`, `JiraSyncRun`, and `JiraSavedQuery`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.jira_workspace.tests.test_models.JiraWorkspaceModelTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/models.py apps/jira_workspace/admin.py apps/jira_workspace/migrations apps/jira_workspace/tests/test_models.py
git commit -m "feat: add jira workspace data models"
```

### Task 3: Implement local query and dashboard aggregation services

**Files:**
- Create: `apps/jira_workspace/services/query_service.py`
- Create: `apps/jira_workspace/services/stats_service.py`
- Create: `apps/jira_workspace/tests/test_query_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
# apps/jira_workspace/tests/test_query_service.py
from datetime import datetime, timedelta, timezone

from django.test import TestCase

from jira_workspace.models import JiraIssue
from jira_workspace.services.query_service import build_issue_queryset
from jira_workspace.services.stats_service import build_dashboard_project_groups


class JiraWorkspaceQueryServiceTests(TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Assigned issue",
            status="In Progress",
            assignee="xchen17",
            reporter="amy",
            updated_at=now - timedelta(days=1),
            created_at=now - timedelta(days=2),
            raw_json="{}",
            last_seen_at=now,
        )
        JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Reported issue",
            status="Blocked",
            assignee="ravi",
            reporter="xchen17",
            updated_at=now - timedelta(days=2),
            created_at=now - timedelta(days=3),
            raw_json="{}",
            last_seen_at=now,
        )

    def test_build_issue_queryset_filters_by_source_semantics(self):
        qs = build_issue_queryset(
            username="xchen17",
            source="assigned",
            project_key="TESS",
        )

        assert list(qs.values_list("issue_key", flat=True)) == ["TESS-321"]

    def test_build_dashboard_project_groups_separates_assigned_and_created_projects(self):
        groups = build_dashboard_project_groups(username="xchen17")

        assert groups["assigned"][0]["project_key"] == "TESS"
        assert groups["created"][0]["project_key"] == "OPS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests.test_query_service.JiraWorkspaceQueryServiceTests -v 2`
Expected: FAIL with `ImportError` because the services do not exist.

- [ ] **Step 3: Write the minimal query and stats services**

```python
# apps/jira_workspace/services/query_service.py
from django.db.models import Q

from jira_workspace.models import JiraIssue


def build_issue_queryset(
    *,
    username,
    source="all",
    project_key=None,
    start=None,
    end=None,
    search=None,
    sort_by="updated_at",
    sort_order="desc",
):
    queryset = JiraIssue.objects.all()

    if source == "assigned":
        queryset = queryset.filter(assignee=username)
    elif source == "created":
        queryset = queryset.filter(reporter=username)
    else:
        queryset = queryset.filter(Q(assignee=username) | Q(reporter=username))

    if project_key:
        queryset = queryset.filter(project_key=project_key)
    if start:
        queryset = queryset.filter(updated_at__gte=start)
    if end:
        queryset = queryset.filter(updated_at__lte=end)
    if search:
        queryset = queryset.filter(Q(issue_key__icontains=search) | Q(summary__icontains=search))

    ordering = sort_by if sort_order == "asc" else f"-{sort_by}"
    return queryset.order_by(ordering)
```

```python
# apps/jira_workspace/services/stats_service.py
from django.db.models import Count

from jira_workspace.services.query_service import build_issue_queryset


def build_dashboard_project_groups(*, username, start=None, end=None):
    assigned = (
        build_issue_queryset(username=username, source="assigned", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key"))
        .order_by("-issue_count", "project_key")
    )
    created = (
        build_issue_queryset(username=username, source="created", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key"))
        .order_by("-issue_count", "project_key")
    )
    return {"assigned": list(assigned), "created": list(created)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.jira_workspace.tests.test_query_service.JiraWorkspaceQueryServiceTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/services/query_service.py apps/jira_workspace/services/stats_service.py apps/jira_workspace/tests/test_query_service.py
git commit -m "feat: add jira workspace query services"
```

### Task 4: Implement the Jira REST adapter and profile-driven sync service

**Files:**
- Create: `apps/jira_workspace/services/jira_adapter.py`
- Create: `apps/jira_workspace/services/sync_service.py`
- Create: `apps/jira_workspace/tests/test_sync_service.py`
- Modify: `mtools/settings.py`

- [ ] **Step 1: Write the failing sync test**

```python
# apps/jira_workspace/tests/test_sync_service.py
from datetime import datetime, timezone
from unittest.mock import Mock

from django.test import TestCase

from jira_workspace.models import JiraIssue, JiraSyncProfile
from jira_workspace.services.sync_service import JiraSyncService


class JiraWorkspaceSyncServiceTests(TestCase):
    def test_incremental_sync_inserts_and_updates_issues_for_a_profile(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
        )
        adapter = Mock()
        adapter.fetch_issues.return_value = [
            {
                "key": "TESS-321",
                "project_key": "TESS",
                "summary": "Refine query presets",
                "status": "In Progress",
                "assignee": "xchen17",
                "reporter": "amy",
                "priority": "High",
                "updated_at": datetime(2026, 6, 11, tzinfo=timezone.utc),
                "created_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
                "raw_json": "{}",
            }
        ]

        result = JiraSyncService(adapter=adapter).incremental_sync(profile)

        assert result.inserted_count == 1
        assert JiraIssue.objects.get(issue_key="TESS-321").assignee == "xchen17"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests.test_sync_service.JiraWorkspaceSyncServiceTests -v 2`
Expected: FAIL with `ImportError` because the sync service does not exist.

- [ ] **Step 3: Write the adapter database connection and sync service**

```python
# apps/jira_workspace/models.py
class JiraConnection(models.Model):
    base_url = models.URLField()
    api_token = models.CharField(max_length=500)
    auth_type = models.CharField(max_length=20, default="bearer")
    user_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
```

```python
# apps/jira_workspace/services/jira_adapter.py
import requests

from jira_workspace.models import JiraConnection


class JiraAdapter:
    search_url = "/rest/api/2/search"

    def __init__(self):
        self.connection = JiraConnection.objects.active().order_by("-updated_at").first()
        if self.connection is None:
            raise ValueError("No active Jira connection is configured.")

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.connection.auth_type == "basic":
            return headers
        headers["Authorization"] = f"Bearer {self.connection.api_token}"
        return headers

    def fetch_issues(self, *, jql, start_at=0, max_results=50):
        response = requests.get(
            f"{self.connection.base_url}{self.search_url}",
            headers=self._headers(),
            params={"jql": jql, "startAt": start_at, "maxResults": max_results},
            auth=(self.connection.user_email, self.connection.api_token) if self.connection.auth_type == "basic" else None,
            timeout=30,
        )
        response.raise_for_status()
        return [
            {
                "key": issue["key"],
                "project_key": issue["fields"]["project"]["key"],
                "summary": issue["fields"].get("summary", ""),
                "status": issue["fields"]["status"]["name"],
                "assignee": (issue["fields"].get("assignee") or {}).get("name"),
                "reporter": (issue["fields"].get("reporter") or {}).get("name"),
                "priority": (issue["fields"].get("priority") or {}).get("name"),
                "updated_at": issue["fields"]["updated"],
                "created_at": issue["fields"].get("created"),
                "raw_json": issue,
            }
            for issue in response.json().get("issues", [])
        ]
```

```python
# apps/jira_workspace/services/sync_service.py
from dataclasses import dataclass
from datetime import datetime, timezone

from jira_workspace.models import JiraIssue, JiraSyncRun


@dataclass
class SyncResult:
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0


class JiraSyncService:
    def __init__(self, adapter):
        self.adapter = adapter

    def incremental_sync(self, profile):
        run = JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        items = self.adapter.fetch_issues(jql=profile.jql)
        result = SyncResult(fetched_count=len(items))
        now = datetime.now(timezone.utc)

        for item in items:
            issue, created = JiraIssue.objects.update_or_create(
                issue_key=item["key"],
                defaults={
                    "project_key": item["project_key"],
                    "summary": item["summary"],
                    "status": item["status"],
                    "assignee": item.get("assignee"),
                    "reporter": item.get("reporter"),
                    "priority": item.get("priority"),
                    "updated_at": item["updated_at"],
                    "created_at": item.get("created_at"),
                    "raw_json": item.get("raw_json", {}),
                    "last_seen_at": now,
                },
            )
            if created:
                result.inserted_count += 1
            else:
                result.updated_count += 1

        profile.last_incremental_sync_at = now
        profile.save(update_fields=["last_incremental_sync_at", "updated_at"])
        run.status = JiraSyncRun.Status.SUCCESS
        run.finished_at = now
        run.fetched_count = result.fetched_count
        run.inserted_count = result.inserted_count
        run.updated_count = result.updated_count
        run.skipped_count = result.skipped_count
        run.save()
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.jira_workspace.tests.test_sync_service.JiraWorkspaceSyncServiceTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mtools/settings.py apps/jira_workspace/services/jira_adapter.py apps/jira_workspace/services/sync_service.py apps/jira_workspace/tests/test_sync_service.py
git commit -m "feat: add jira profile sync service"
```

### Task 5: Build the Dashboard page, time-range controls, and async ticket-table refresh

**Files:**
- Create: `templates/jira_workspace/base.html`
- Create: `templates/jira_workspace/dashboard.html`
- Create: `templates/jira_workspace/partials/project_groups.html`
- Create: `templates/jira_workspace/partials/ticket_table.html`
- Create: `static/jira_workspace/jira.css`
- Create: `static/jira_workspace/jira.js`
- Modify: `apps/jira_workspace/views.py`
- Modify: `apps/jira_workspace/urls.py`
- Create: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing dashboard view tests**

```python
# apps/jira_workspace/tests/test_views.py
from datetime import datetime, timedelta, timezone

from django.test import TestCase
from django.urls import reverse

from jira_workspace.models import JiraIssue


class JiraWorkspaceDashboardViewTests(TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="Review",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=now - timedelta(days=1),
            created_at=now - timedelta(days=2),
            raw_json="{}",
            last_seen_at=now,
        )

    def test_dashboard_renders_time_range_and_recently_updated_sections(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        assert "7d" in response.content.decode()
        assert "Recently Updated" in response.content.decode()

    def test_dashboard_ticket_table_partial_filters_assigned_project(self):
        response = self.client.get(
            reverse("jira_workspace:dashboard_ticket_table"),
            {"source": "assigned", "project": "TESS"},
        )

        assert response.status_code == 200
        assert "TESS-321" in response.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceDashboardViewTests -v 2`
Expected: FAIL because the view, partial route, and templates do not exist.

- [ ] **Step 3: Write the dashboard view, routes, templates, and JS**

```python
# apps/jira_workspace/views.py
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from jira_workspace.services.query_service import build_issue_queryset
from jira_workspace.services.stats_service import build_dashboard_project_groups


DEFAULT_USERNAME = "xchen17"


def dashboard(request):
    end = timezone.now()
    start = end - timedelta(days=15)
    ticket_queryset = build_issue_queryset(username=DEFAULT_USERNAME, start=start, end=end)
    context = {
        "range_key": request.GET.get("range", "15d"),
        "start": start.date(),
        "end": end.date(),
        "project_groups": build_dashboard_project_groups(username=DEFAULT_USERNAME, start=start, end=end),
        "recent_issues": ticket_queryset[:5],
        "ticket_rows": ticket_queryset[:20],
        "active_source": "all",
        "active_project": "",
    }
    return render(request, "jira_workspace/dashboard.html", context)


def dashboard_ticket_table(request):
    queryset = build_issue_queryset(
        username=DEFAULT_USERNAME,
        source=request.GET.get("source", "all"),
        project_key=request.GET.get("project") or None,
    )
    return render(
        request,
        "jira_workspace/partials/ticket_table.html",
        {"ticket_rows": queryset[:30]},
    )
```

```python
# apps/jira_workspace/urls.py
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/tickets/", views.dashboard_ticket_table, name="dashboard_ticket_table"),
]
```

```html
<!-- templates/jira_workspace/dashboard.html -->
{% extends "jira_workspace/base.html" %}
{% block content %}
<section>
  <h1>Jira Dashboard</h1>
  <div class="range-bar">
    <button>7d</button><button>30d</button><button>90d</button><button>1y</button><button>All</button>
    <input type="date" value="{{ start|date:'Y-m-d' }}">
    <input type="date" value="{{ end|date:'Y-m-d' }}">
  </div>
  <div class="dashboard-layout">
    <aside>
      <h2>Assigned To Me</h2>
      {% include "jira_workspace/partials/project_groups.html" with group_items=project_groups.assigned group_source="assigned" %}
      <h2>Created By Me</h2>
      {% include "jira_workspace/partials/project_groups.html" with group_items=project_groups.created group_source="created" %}
      <h2>Recently Updated</h2>
      {% for issue in recent_issues %}<div>{{ issue.issue_key }} {{ issue.summary }}</div>{% endfor %}
    </aside>
    <main id="ticket-table-root">
      {% include "jira_workspace/partials/ticket_table.html" with ticket_rows=ticket_rows %}
    </main>
  </div>
</section>
{% endblock %}
```

```javascript
// static/jira_workspace/jira.js
document.addEventListener("click", async (event) => {
  const trigger = event.target.closest("[data-project-trigger]");
  if (!trigger) return;
  event.preventDefault();
  const url = new URL(trigger.dataset.url, window.location.origin);
  const response = await fetch(url.toString(), { headers: { "X-Requested-With": "XMLHttpRequest" } });
  document.querySelector("#ticket-table-root").innerHTML = await response.text();
});
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceDashboardViewTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/views.py apps/jira_workspace/urls.py templates/jira_workspace static/jira_workspace apps/jira_workspace/tests/test_views.py
git commit -m "feat: add jira dashboard page"
```

### Task 6: Build Saved Queries and Profiles & Sync pages on top of the shared services

**Files:**
- Create: `apps/jira_workspace/forms.py`
- Modify: `apps/jira_workspace/views.py`
- Modify: `apps/jira_workspace/urls.py`
- Create: `templates/jira_workspace/queries.html`
- Create: `templates/jira_workspace/profiles.html`
- Create: `templates/jira_workspace/partials/query_library.html`
- Create: `templates/jira_workspace/partials/sync_runs.html`
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing saved-query and profile tests**

```python
# append to apps/jira_workspace/tests/test_views.py
from jira_workspace.models import JiraSavedQuery, JiraSyncProfile


class JiraWorkspaceSecondaryPagesTests(TestCase):
    def setUp(self):
        self.profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
            is_default=True,
        )
        JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=self.profile,
            filters_json={"status": ["Blocked"]},
            is_starred=True,
            is_pinned=True,
        )

    def test_saved_queries_page_lists_query_library(self):
        response = self.client.get(reverse("jira_workspace:queries"))

        assert response.status_code == 200
        assert "My Open Blockers" in response.content.decode()

    def test_profiles_page_lists_profiles_and_sync_runs(self):
        response = self.client.get(reverse("jira_workspace:profiles"))

        assert response.status_code == 200
        assert "My Issues" in response.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceSecondaryPagesTests -v 2`
Expected: FAIL because the routes, forms, and templates do not exist.

- [ ] **Step 3: Write forms, views, routes, and templates**

```python
# apps/jira_workspace/forms.py
from django import forms

from jira_workspace.models import JiraSavedQuery, JiraSyncProfile


class JiraSyncProfileForm(forms.ModelForm):
    class Meta:
        model = JiraSyncProfile
        fields = ["name", "profile_type", "params_json", "jql", "is_default"]


class JiraSavedQueryForm(forms.ModelForm):
    class Meta:
        model = JiraSavedQuery
        fields = ["name", "profile", "description", "filters_json", "jql_text", "is_starred", "is_pinned", "sort_by", "sort_order"]
```

```python
# apps/jira_workspace/views.py
from jira_workspace.models import JiraSavedQuery, JiraSyncProfile


def queries(request):
    context = {
        "saved_queries": JiraSavedQuery.objects.select_related("profile").order_by("-is_pinned", "-is_starred", "name"),
    }
    return render(request, "jira_workspace/queries.html", context)


def profiles(request):
    context = {
        "profiles": JiraSyncProfile.objects.order_by("-is_default", "name"),
        "sync_runs": JiraSyncRun.objects.select_related("profile").order_by("-started_at")[:20],
    }
    return render(request, "jira_workspace/profiles.html", context)
```

```python
# apps/jira_workspace/urls.py
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/tickets/", views.dashboard_ticket_table, name="dashboard_ticket_table"),
    path("queries/", views.queries, name="queries"),
    path("profiles/", views.profiles, name="profiles"),
]
```

```html
<!-- templates/jira_workspace/queries.html -->
{% extends "jira_workspace/base.html" %}
{% block content %}
<h1>Saved Queries</h1>
{% include "jira_workspace/partials/query_library.html" with saved_queries=saved_queries %}
{% endblock %}
```

```html
<!-- templates/jira_workspace/profiles.html -->
{% extends "jira_workspace/base.html" %}
{% block content %}
<h1>Profiles & Sync</h1>
{% for profile in profiles %}<div>{{ profile.name }}</div>{% endfor %}
{% include "jira_workspace/partials/sync_runs.html" with sync_runs=sync_runs %}
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceSecondaryPagesTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/forms.py apps/jira_workspace/views.py apps/jira_workspace/urls.py templates/jira_workspace apps/jira_workspace/tests/test_views.py
git commit -m "feat: add jira saved queries and profiles pages"
```

### Task 7: Verify the integrated Jira workspace end-to-end

**Files:**
- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `apps/jira_workspace/tests/test_sync_service.py`

- [ ] **Step 1: Write the failing integration-level tests**

```python
# append to apps/jira_workspace/tests/test_views.py
class JiraWorkspaceNavigationTests(TestCase):
    def test_all_primary_pages_return_ok(self):
        for name in ["dashboard", "queries", "profiles"]:
            response = self.client.get(reverse(f"jira_workspace:{name}"))
            assert response.status_code == 200
```

```python
# append to apps/jira_workspace/tests/test_sync_service.py
class JiraWorkspaceSyncRunTests(TestCase):
    def test_incremental_sync_records_a_successful_run(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
        )
        adapter = Mock()
        adapter.fetch_issues.return_value = []

        JiraSyncService(adapter=adapter).incremental_sync(profile)

        assert profile.sync_runs.count() == 1
        assert profile.sync_runs.first().status == JiraSyncRun.Status.SUCCESS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.jira_workspace.tests -v 2`
Expected: FAIL because the new assertions or imports are not yet complete.

- [ ] **Step 3: Finish the small gaps exposed by the full test run**

```python
# apps/jira_workspace/tests/test_sync_service.py
from jira_workspace.models import JiraIssue, JiraSyncProfile, JiraSyncRun
```

```html
<!-- templates/jira_workspace/base.html -->
<nav>
  <a href="{% url 'jira_workspace:dashboard' %}">Dashboard</a>
  <a href="{% url 'jira_workspace:queries' %}">Saved Queries</a>
  <a href="{% url 'jira_workspace:profiles' %}">Profiles & Sync</a>
</nav>
{% block content %}{% endblock %}
```

```html
<!-- templates/jira_workspace/partials/sync_runs.html -->
{% if sync_runs %}
  {% for run in sync_runs %}
    <div>{{ run.profile.name }} {{ run.status }} {{ run.started_at }}</div>
  {% endfor %}
{% else %}
  <div>No sync runs yet.</div>
{% endif %}
```

- [ ] **Step 4: Run the full test suite to verify it passes**

Run: `python manage.py test apps.jira_workspace.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/tests templates/jira_workspace/base.html
git commit -m "test: verify jira workspace flow"
```

## Self-Review

### Spec coverage

- Local-cache architecture: covered by Tasks 2, 3, and 4.
- Dashboard self-only behavior, 15-day default range, grouped projects, recent updates, and async ticket-table refresh: covered by Task 5.
- Saved Queries workspace with query library and reusable result area: covered by Task 6.
- Profiles & Sync management page and profile-driven sync model: covered by Tasks 2, 4, and 6.
- Reporter versus assignee source semantics: covered by Task 3 and exercised by Task 5 partial-refresh tests.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain in executable steps.
- The integration task now names the exact import and template snippets required to close the expected gaps.

### Type consistency

- App namespace is consistently `jira_workspace`.
- The model names `JiraIssue`, `JiraSyncProfile`, `JiraSyncRun`, and `JiraSavedQuery` are used consistently across tasks.
- Dashboard partial route name is consistently `dashboard_ticket_table`.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-11-jira-workspace-implementation.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
