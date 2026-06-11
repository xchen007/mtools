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
            filters_json={"status": ["Blocked"]},
            is_starred=True,
            is_pinned=True,
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

    def test_saved_queries_page_lists_query_library(self):
        response = self.client.get(reverse("jira_workspace:queries"))

        assert response.status_code == 200
        assert "My Open Blockers" in response.content.decode()

    def test_profiles_page_lists_profiles_and_sync_runs(self):
        response = self.client.get(reverse("jira_workspace:profiles"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "My Issues" in content
        assert "success" in content.lower()


class JiraWorkspaceNavigationTests(TestCase):
    def test_all_primary_pages_return_ok(self):
        for name in ["dashboard", "queries", "profiles"]:
            response = self.client.get(reverse(f"jira_workspace:{name}"))
            assert response.status_code == 200

    def test_workspace_shell_routes_render(self):
        route_expectations = [
            ("jira_workspace:workspace_home", "Workspace"),
            ("jira_workspace:query", "Jira Query"),
            ("jira_workspace:issues", "Jira Issues"),
            ("jira_workspace:sync", "Jira Sync"),
            ("jira_workspace:sync2pod", "sync2pod"),
            ("jira_workspace:integrations", "Integrations"),
        ]

        for route_name, title_text in route_expectations:
            response = self.client.get(reverse(route_name))
            assert response.status_code == 200
            content = response.content.decode()
            assert "mtools" in content
            assert title_text in content

    def test_root_redirects_to_workspace_home(self):
        response = self.client.get("/")

        assert response.status_code == 302
        assert response.headers["Location"] == reverse("jira_workspace:workspace_home")
