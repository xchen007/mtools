from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from jira_workspace.models import (
    IntegrationContract,
    IntegrationScanRun,
    IntegrationTool,
    JiraIssue,
    JiraSavedQuery,
    JiraSyncProfile,
    JiraSyncRun,
    Sync2PodProfile,
    Sync2PodRun,
    Sync2PodWatchEvent,
)


class JiraWorkspaceDashboardViewTests(TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="Review",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=self.now - timedelta(days=1),
            created_at=self.now - timedelta(days=2),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Created issue",
            status="Blocked",
            assignee="ravi",
            reporter="xchen17",
            priority="Medium",
            updated_at=self.now - timedelta(days=2),
            created_at=self.now - timedelta(days=3),
            raw_json="{}",
            last_seen_at=self.now,
        )

    def test_dashboard_renders_time_range_and_recently_updated_sections(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "15d" in content
        assert "Recently Updated" in content
        assert "Assigned To Me" in content
        assert "Created By Me" in content
        assert "Assigned Issues" in content
        assert "Created Issues" in content
        assert "Tracked Projects" in content
        assert "Blocked Issues" in content
        assert "?range=30d" in content

    def test_dashboard_ticket_table_partial_filters_assigned_project(self):
        response = self.client.get(
            reverse("jira_workspace:dashboard_ticket_table"),
            {"source": "assigned", "project": "TESS"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "TESS-321" in content
        assert "OPS-778" not in content

    def test_dashboard_surfaces_external_blocker_when_local_cache_is_empty(self):
        JiraIssue.objects.all().delete()
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
            is_default=True,
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=self.now - timedelta(minutes=10),
            finished_at=self.now - timedelta(minutes=9),
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
            error_message="Jira returned 403: The request is blocked.",
        )

        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "External Jira access is currently blocked" in content
        assert "No cached Jira issues are available yet." in content


class JiraWorkspaceSecondaryPagesTests(TestCase):
    def setUp(self):
        self.profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
            is_default=True,
        )
        JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=self.profile,
            description="Blocked work owned by me.",
            filters_json={"status": ["Blocked"]},
            jql_text='status = "Blocked"',
            is_starred=True,
            is_pinned=True,
        )
        JiraSavedQuery.objects.create(
            name="Team Review Queue",
            profile=self.profile,
            filters_json={"status": ["Review"], "project": ["TESS"]},
            jql_text='project = "TESS" AND status = "Review"',
            sort_by="priority",
            sort_order="asc",
        )
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="Review",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            sprint="Sprint 42",
            updated_at=datetime.now(timezone.utc) - timedelta(hours=4),
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            raw_json="{}",
            last_seen_at=datetime.now(timezone.utc),
        )
        JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Escalate blocker handling",
            status="Blocked",
            assignee="xchen17",
            reporter="xchen17",
            priority="Highest",
            sprint="Sprint 42",
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            raw_json="{}",
            last_seen_at=datetime.now(timezone.utc),
        )
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.SUCCESS,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            finished_at=datetime.now(timezone.utc),
            fetched_count=3,
            inserted_count=1,
            updated_count=1,
            skipped_count=1,
        )
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=19),
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
            error_message="Jira returned 403: The request is blocked.",
        )

    def test_query_page_renders_query_library_and_filter_details(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        assert "Query Library" in content
        assert "My Open Blockers" in content
        assert "Blocked work owned by me." in content
        assert 'status = "Blocked"' in content
        assert "Pinned" in content
        assert "Starred" in content
        assert "Project Filter" in content
        assert "Status Filter" in content
        assert "Query Results" in content
        assert "OPS-778" in content
        assert "TESS-321" not in content

    def test_query_page_can_persist_a_saved_query_from_editor_form(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "save_query",
                "name": "OPS Blockers",
                "profile": str(self.profile.id),
                "description": "Track OPS blockers",
                "project_values": "OPS",
                "status_values": "Blocked",
                "jql_text": 'project = "OPS" AND status = "Blocked"',
                "sort_by": "priority",
                "sort_order": "asc",
                "is_starred": "on",
            },
        )

        assert response.status_code == 302
        saved_query = JiraSavedQuery.objects.get(name="OPS Blockers")
        assert saved_query.profile == self.profile
        assert saved_query.filters_json == {"project": ["OPS"], "status": ["Blocked"]}
        assert saved_query.sort_by == "priority"
        assert saved_query.sort_order == "asc"
        assert saved_query.is_starred is True

    def test_query_page_allows_selecting_a_saved_query(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"saved_query": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        assert "Team Review Queue" in content
        assert "TESS-321" in content
        assert "OPS-778" not in content

    def test_issues_page_renders_saved_views_filters_and_issue_rows(self):
        response = self.client.get(
            reverse("jira_workspace:issues"),
            {"query": "OPS", "project": "OPS", "status": "Blocked"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Saved Views" in content
        assert "Issue Results" in content
        assert "Bulk Actions" in content
        assert "TESS-321" not in content
        assert "OPS-778" in content
        assert "Project" in content
        assert "Status" in content
        assert "Search" in content

    def test_issues_page_can_render_selected_issue_detail(self):
        response = self.client.get(
            reverse("jira_workspace:issues"),
            {"issue": "OPS-778"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Issue Detail" in content
        assert "Escalate blocker handling" in content
        assert "Sprint 42" in content

    def test_sync_page_renders_profiles_runs_and_blocker_state(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Run Configuration Presets" in content
        assert "Sync Run Timeline" in content
        assert "My Issues" in content
        assert "success" in content.lower()
        assert "The request is blocked." in content
        assert "External Jira access is currently blocked" in content
        assert "Profile Editor" in content
        assert "Sync Controls" in content

    def test_sync_page_can_persist_a_profile(self):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "save_profile",
                "name": "OPS Project",
                "profile_type": JiraSyncProfile.ProfileType.PROJECT,
                "project_key": "OPS",
                "is_default": "on",
            },
        )

        assert response.status_code == 302
        profile = JiraSyncProfile.objects.get(name="OPS Project")
        assert profile.profile_type == JiraSyncProfile.ProfileType.PROJECT
        assert profile.params_json == {"project_key": "OPS"}
        assert profile.is_default is True

    @patch("jira_workspace.views.SyncService.incremental_sync")
    def test_sync_page_can_trigger_incremental_sync(self, incremental_sync):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.INCREMENTAL,
            },
        )

        assert response.status_code == 302
        incremental_sync.assert_called_once()

    @patch("jira_workspace.views.SyncService.full_sync")
    def test_sync_page_can_trigger_full_sync(self, full_sync):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.FULL,
            },
        )

        assert response.status_code == 302
        full_sync.assert_called_once()


class JiraWorkspaceNavigationTests(TestCase):
    def test_all_primary_pages_return_ok(self):
        for name in ["dashboard", "query", "issues", "sync"]:
            response = self.client.get(reverse(f"jira_workspace:{name}"))
            assert response.status_code == 200

    def test_workspace_shell_routes_render(self):
        route_expectations = [
            ("/workspace/", "Workspace"),
            (reverse("jira_workspace:query"), "Jira Query"),
            (reverse("jira_workspace:issues"), "Jira Issues"),
            (reverse("jira_workspace:sync"), "Jira Sync"),
            ("/sync2pod/", "sync2pod"),
            ("/integrations/", "Integrations"),
        ]

        for route_path, title_text in route_expectations:
            response = self.client.get(route_path)
            assert response.status_code == 200
            content = response.content.decode()
            assert "mtools" in content
            assert title_text in content

    def test_legacy_queries_and_profiles_routes_redirect_to_new_pages(self):
        route_expectations = [
            (reverse("jira_workspace:queries"), reverse("jira_workspace:query")),
            (reverse("jira_workspace:profiles"), reverse("jira_workspace:sync")),
        ]

        for old_route, new_route in route_expectations:
            response = self.client.get(old_route)
            assert response.status_code == 302
            assert response.headers["Location"] == new_route

    def test_root_redirects_to_workspace_home(self):
        response = self.client.get("/")

        assert response.status_code == 302
        assert response.headers["Location"] == "/workspace/"

    def test_workspace_home_renders_cross_tool_summary_cards_and_activity(self):
        jira_profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
        )
        JiraSyncRun.objects.create(
            profile=jira_profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.SUCCESS,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=19),
            fetched_count=4,
            inserted_count=1,
            updated_count=2,
            skipped_count=1,
        )
        sync2pod_profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        Sync2PodRun.objects.create(
            profile=sync2pod_profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=127,
            error_message="sync2pod command is not available on this host.",
        )
        Sync2PodWatchEvent.objects.create(
            profile=sync2pod_profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued after edit",
        )
        tool = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into pods.",
        )
        IntegrationScanRun.objects.create(
            tool=tool,
            status=IntegrationScanRun.Status.SUCCESS,
            summary="catalog refresh completed",
        )

        response = self.client.get("/workspace/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Workspace Overview" in content
        assert "Jira Sync Runs" in content
        assert "sync2pod Queue" in content
        assert "Integration Scans" in content
        assert "Cross-Tool Activity" in content
        assert "catalog refresh completed" in content
        assert "sync2pod command is not available on this host." in content


class Sync2PodViewTests(TestCase):
    def test_sync2pod_page_renders_persisted_profiles_runs_and_queue_state(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            config_path="/tmp/sync2pod.yaml",
            command="sync2pod",
            extra_args="--delete",
        )
        Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.SUCCESS,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push --delete",
            exit_code=0,
            stdout_log="synced 4 files",
        )
        Sync2PodWatchEvent.objects.create(
            profile=profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued after edit",
        )

        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Sync2pod Profiles" in content
        assert "Recent Runs" in content
        assert "Queued Watch Events" in content
        assert "Primary Pod" in content
        assert "pod-a" in content
        assert "synced 4 files" in content
        assert "src/module.py" in content
        assert "Project Configuration Manager" in content
        assert "Sync Strategy Panel" in content
        assert "Execution Console" in content
        assert "Watch Mode" in content
        assert "Archive / Chunk Upload Insights" in content
        assert "Safety / Validation Strip" in content

    def test_sync2pod_page_renders_actionable_failure_state(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=127,
            error_message="sync2pod command is not available on this host.",
        )

        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Action Required" in content
        assert "sync2pod command is not available on this host." in content

    def test_sync2pod_post_can_persist_a_profile(self):
        response = self.client.post(
            reverse("jira_workspace:sync2pod"),
            {
                "action": "save_profile",
                "name": "Primary Pod",
                "pod_name": "pod-a",
                "namespace": "sync",
                "watch_path": "/tmp/watch",
                "config_path": "/tmp/sync2pod.yaml",
                "command": "true",
                "extra_args": "--delete",
                "is_enabled": "on",
            },
        )

        assert response.status_code == 302
        profile = Sync2PodProfile.objects.get(name="Primary Pod")
        assert profile.command == "true"
        assert profile.extra_args == "--delete"

    def test_sync2pod_post_can_start_a_sync_run(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            config_path="/tmp/sync2pod.yaml",
            command="true",
            extra_args="--delete",
        )

        response = self.client.post(
            reverse("jira_workspace:sync2pod"),
            {
                "action": "start_sync",
                "profile_id": str(profile.id),
            },
        )

        assert response.status_code == 302
        run = Sync2PodRun.objects.latest("started_at")
        assert run.profile == profile
        assert run.status == Sync2PodRun.Status.SUCCESS


class IntegrationsViewTests(TestCase):
    def setUp(self):
        jira_sync = IntegrationTool.objects.create(
            key="jira-sync",
            name="Jira Sync",
            group="Issue Ops",
            readiness=IntegrationTool.Readiness.READY,
            description="Refreshes cached Jira issues.",
        )
        IntegrationContract.objects.create(
            tool=jira_sync,
            input_contract="profile + JQL",
            output_contract="issue cache rows",
            event_contract="sync runs",
            notes="Stable contract surface.",
        )
        sync2pod = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into pods.",
        )
        IntegrationContract.objects.create(
            tool=sync2pod,
            input_contract="watch path + pod target",
            output_contract="transfer summary",
            event_contract="",
            notes="Event stream not wired yet.",
        )
        IntegrationScanRun.objects.create(
            tool=sync2pod,
            status=IntegrationScanRun.Status.FAILED,
            summary="catalog refresh stalled on sync2pod metadata",
            error_message="event stream contract missing",
        )

    def test_integrations_page_renders_catalog_matrix_and_recent_activity(self):
        response = self.client.get(reverse("jira_workspace:integrations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Tool Catalog by Type" in content
        assert "Contract Surface Matrix" in content
        assert "Recent Scan Activity" in content
        assert "Issue Ops" in content
        assert "Jira Sync" in content
        assert "sync2pod" in content
        assert "event stream contract missing" in content
        assert "events" in content

    def test_integrations_page_filters_catalog_by_query(self):
        response = self.client.get(reverse("jira_workspace:integrations"), {"query": "pod"})

        assert response.status_code == 200
        content = response.content.decode()
        assert "sync2pod" in content
        assert "Push local files into pods." in content
        assert "Refreshes cached Jira issues." not in content


class JiraWorkspaceStylesheetTests(TestCase):
    def test_shared_stylesheet_includes_toolbar_and_form_layout_hooks(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        for selector in [
            ".toolbar",
            ".toolbar--actions",
            ".toolbar__search",
            ".form-grid",
            ".checkbox-row",
            ".data-table",
            ".meta-inline",
            ".group-stack",
        ]:
            assert selector in css
