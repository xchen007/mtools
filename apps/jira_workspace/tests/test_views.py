from datetime import datetime, timedelta, timezone

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

    def test_dashboard_ticket_table_partial_filters_assigned_project(self):
        response = self.client.get(
            reverse("jira_workspace:dashboard_ticket_table"),
            {"source": "assigned", "project": "TESS"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "TESS-321" in content
        assert "OPS-778" not in content


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
        content = response.content.decode()
        assert "Query Library" in content
        assert "My Open Blockers" in content
        assert "Blocked work owned by me." in content
        assert 'status = "Blocked"' in content
        assert "Pinned" in content
        assert "Starred" in content
        assert "Project Filter" in content
        assert "Status Filter" in content

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
