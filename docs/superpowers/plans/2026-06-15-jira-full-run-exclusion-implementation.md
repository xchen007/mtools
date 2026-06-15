# Jira Full Run Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent any new Jira sync task from starting while a Jira full sync is already queued or running, and surface that blocked state clearly in the Jira sync UI.

**Architecture:** Add the exclusion rule at the `SyncService.enqueue_sync()` boundary so every caller gets the same protection, then thread the rejection reason through the `/jira/sync/` view and template. Keep the rule Jira-sync-local, use existing `JiraSyncRun` status fields, and cover the behavior with focused service and view tests before changing production code.

**Tech Stack:** Django 3.2, Django test runner, SQLite, existing `jira_workspace` service/view/template stack, Django messages framework already installed via middleware/context processors.

---

## File Map

- Modify `apps/jira_workspace/services/sync_service.py`: add the active-full-run guard and explicit rejection exception.
- Modify `apps/jira_workspace/tests/test_sync_service.py`: add red/green tests for allowed and blocked enqueue cases.
- Modify `apps/jira_workspace/views.py`: catch the explicit rejection, surface a user message, and expose an `has_active_full_sync` UI signal.
- Modify `apps/jira_workspace/tests/test_views.py`: cover blocked POST behavior and disabled controls when a full run is active.
- Modify `templates/jira_workspace/base.html`: render shared Django flash messages.
- Modify `templates/jira_workspace/sync.html`: show the blocked-state hint and disable both run buttons when a full run is active.

## Task 1: Guard Jira Sync Enqueue at the Service Boundary

**Files:**
- Modify: `apps/jira_workspace/tests/test_sync_service.py`
- Modify: `apps/jira_workspace/services/sync_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
# apps/jira_workspace/tests/test_sync_service.py
    def test_enqueue_sync_allows_incremental_when_no_active_full_run_exists(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={},
            jql="",
        )

        run = self.service.enqueue_sync(
            profile,
            JiraSyncRun.RunType.INCREMENTAL,
            start_background=False,
        )

        assert run.run_type == JiraSyncRun.RunType.INCREMENTAL
        assert run.status == JiraSyncRun.Status.QUEUED

    def test_enqueue_sync_rejects_incremental_when_full_run_is_queued(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.QUEUED,
            started_at=datetime.now(timezone.utc),
            progress_message="Queued",
        )

        before_count = JiraSyncRun.objects.count()

        with self.assertRaises(ActiveFullSyncError):
            self.service.enqueue_sync(
                self.profile,
                JiraSyncRun.RunType.INCREMENTAL,
                start_background=False,
            )

        assert JiraSyncRun.objects.count() == before_count

    def test_enqueue_sync_rejects_full_when_another_full_run_is_running(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            progress_message="Fetched 10 issues.",
        )

        before_count = JiraSyncRun.objects.count()

        with self.assertRaises(ActiveFullSyncError):
            self.service.enqueue_sync(
                self.profile,
                JiraSyncRun.RunType.FULL,
                start_background=False,
            )

        assert JiraSyncRun.objects.count() == before_count
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test \
  apps.jira_workspace.tests.test_sync_service.JiraWorkspaceSyncServiceTests.test_enqueue_sync_allows_incremental_when_no_active_full_run_exists \
  apps.jira_workspace.tests.test_sync_service.JiraWorkspaceSyncServiceTests.test_enqueue_sync_rejects_incremental_when_full_run_is_queued \
  apps.jira_workspace.tests.test_sync_service.JiraWorkspaceSyncServiceTests.test_enqueue_sync_rejects_full_when_another_full_run_is_running \
  -v 2
```

Expected: fail with `AttributeError` or `ImportError` because `ActiveFullSyncError` and the guard behavior do not exist yet.

- [ ] **Step 3: Implement the minimal service guard**

```python
# apps/jira_workspace/services/sync_service.py
class ActiveFullSyncError(Exception):
    """Raised when a Jira full sync already owns the Jira sync queue."""


class SyncService:
    # ...

    def enqueue_sync(self, profile, run_type, *, start_background=True):
        if self._has_active_full_sync():
            raise ActiveFullSyncError(
                "A Jira full sync is already queued or running. "
                "Wait for it to finish before starting another Jira sync task."
            )

        run = JiraSyncRun.objects.create(
            profile=profile,
            run_type=run_type,
            status=JiraSyncRun.Status.QUEUED,
            started_at=timezone.now(),
            progress_message="Queued",
        )
        if start_background:
            thread = threading.Thread(
                target=self._run_queued_sync,
                args=(run.id,),
                daemon=True,
            )
            thread.start()
        return run

    @staticmethod
    def _has_active_full_sync():
        return JiraSyncRun.objects.filter(
            run_type=JiraSyncRun.RunType.FULL,
            status__in=[JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING],
        ).exists()
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass, and the blocked cases confirm no extra `JiraSyncRun` row is created.

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/services/sync_service.py apps/jira_workspace/tests/test_sync_service.py
git commit -m "fix: block jira sync while full run is active"
```

## Task 2: Surface the Blocked State in the Jira Sync View and Templates

**Files:**
- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `apps/jira_workspace/views.py`
- Modify: `templates/jira_workspace/base.html`
- Modify: `templates/jira_workspace/sync.html`

- [ ] **Step 1: Write the failing view and template tests**

```python
# apps/jira_workspace/tests/test_views.py
    @patch("jira_workspace.views.SyncService.enqueue_sync")
    def test_sync_page_shows_error_when_full_run_blocks_new_enqueue(self, enqueue_sync):
        enqueue_sync.side_effect = ActiveFullSyncError(
            "A Jira full sync is already queued or running. "
            "Wait for it to finish before starting another Jira sync task."
        )

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.INCREMENTAL,
            },
            follow=True,
        )

        assert response.status_code == 200
        assert "A Jira full sync is already queued or running." in response.content.decode()

    def test_sync_page_disables_all_run_buttons_when_full_run_is_active(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            progress_message="Fetched 10 of 20 issues.",
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="run_type" value="incremental" disabled' in content
        assert 'name="run_type" value="full" disabled' in content
        assert "A Jira full sync is already queued or running." in content
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test \
  apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_sync_page_shows_error_when_full_run_blocks_new_enqueue \
  apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_sync_page_disables_all_run_buttons_when_full_run_is_active \
  -v 2
```

Expected: fail because the view still swallows exceptions, no flash messages are rendered, and the sync buttons are not disabled for active full runs.

- [ ] **Step 3: Implement the minimal blocked-state UI**

```python
# apps/jira_workspace/views.py
from django.contrib import messages

from jira_workspace.services.sync_service import ActiveFullSyncError, SyncService

# inside sync()
        elif action == "run_sync":
            profile = get_object_or_404(JiraSyncProfile, pk=request.POST.get("profile_id"))
            run_type = request.POST.get("run_type")
            try:
                if run_type not in {JiraSyncRun.RunType.FULL, JiraSyncRun.RunType.INCREMENTAL}:
                    run_type = JiraSyncRun.RunType.INCREMENTAL
                sync_service.enqueue_sync(profile, run_type)
            except ActiveFullSyncError as exc:
                messages.error(request, str(exc))
            except Exception:
                messages.error(request, "Unable to start the Jira sync task right now.")
            return redirect(f"{reverse('jira_workspace:sync')}?profile={profile.id}")

    sync_status = sync_service.build_sync_status()
    has_active_sync = any(
        run.status in {JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING}
        for run in sync_status["recent_runs"]
    )
    has_active_full_sync = any(
        run.run_type == JiraSyncRun.RunType.FULL
        and run.status in {JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING}
        for run in sync_status["recent_runs"]
    )
    context = {
        # ...
        "has_active_sync": has_active_sync,
        "has_active_full_sync": has_active_full_sync,
    }
```

```html
<!-- templates/jira_workspace/base.html -->
<main class="app-main">
  {% if messages %}
    <section class="flash-stack">
      {% for message in messages %}
        <div class="status-pill status-pill--{% if message.tags == 'error' %}failed{% else %}neutral{% endif %}">
          {{ message }}
        </div>
      {% endfor %}
    </section>
  {% endif %}
  {% block content %}{% endblock %}
</main>
```

```html
<!-- templates/jira_workspace/sync.html -->
<div class="toolbar toolbar--actions">
  <button type="submit" name="run_type" value="incremental" {% if not profiles or has_active_full_sync %}disabled{% endif %}>Run Incremental</button>
  <button type="submit" name="run_type" value="full" {% if not profiles or has_active_full_sync %}disabled{% endif %}>Run Full</button>
</div>
{% if has_active_full_sync %}
  <p class="empty-state">A Jira full sync is already queued or running. Wait for it to finish before starting another Jira sync task.</p>
{% elif has_active_sync %}
  <p class="empty-state">A sync task is running in the background. Progress refreshes automatically.</p>
{% endif %}
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run the same `manage.py test` command from Step 2.

Expected: pass, with the blocked POST surfacing the error string and the GET response disabling both sync buttons during an active full run.

- [ ] **Step 5: Commit**

```bash
git add apps/jira_workspace/views.py apps/jira_workspace/tests/test_views.py templates/jira_workspace/base.html templates/jira_workspace/sync.html
git commit -m "fix: surface jira full sync exclusion in sync ui"
```

## Task 3: Run Focused Regression Verification and Finish the Change Set

**Files:**
- Modify: none
- Verify: `apps/jira_workspace/tests/test_sync_service.py`
- Verify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
./.venv/bin/python manage.py test \
  apps.jira_workspace.tests.test_sync_service \
  apps.jira_workspace.tests.test_views \
  -v 2
```

Expected: pass, including the new full-run exclusion tests and the existing sync page behavior.

- [ ] **Step 2: Verify the final diff is scoped correctly**

Run:

```bash
git diff --stat HEAD~2..HEAD
git status --short
```

Expected: only the service, view, template, and test files from Tasks 1-2 are part of the new commits; unrelated working tree changes remain untouched.

- [ ] **Step 3: Commit any final doc or polish only if needed**

```bash
# If no further edits were needed after regression verification, do not create an extra commit.
# If a small fix was required inside the existing scope, commit only these files:
git add apps/jira_workspace/services/sync_service.py apps/jira_workspace/tests/test_sync_service.py apps/jira_workspace/views.py apps/jira_workspace/tests/test_views.py templates/jira_workspace/base.html templates/jira_workspace/sync.html
git commit -m "test: finalize jira full sync exclusion coverage"
```
