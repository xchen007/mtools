from datetime import datetime, timedelta, timezone

from django.test import TestCase
from django.urls import reverse

from jira_workspace.models import JiraIssue, JiraSavedQuery, JiraSyncProfile, JiraSyncRun


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
