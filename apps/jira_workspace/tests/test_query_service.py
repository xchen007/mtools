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

    def test_build_issue_queryset_filters_reported_issues_for_created_source(self):
        qs = build_issue_queryset(username="xchen17", source="created")

        assert list(qs.values_list("issue_key", flat=True)) == ["OPS-778"]

    def test_build_issue_queryset_returns_assigned_and_reported_issues_for_all_source(self):
        qs = build_issue_queryset(username="xchen17", source="all")

        assert list(qs.values_list("issue_key", flat=True)) == ["TESS-321", "OPS-778"]

    def test_build_dashboard_project_groups_separates_assigned_and_created_projects(self):
        groups = build_dashboard_project_groups(username="xchen17")

        assert groups["assigned"][0]["project_key"] == "TESS"
        assert groups["created"][0]["project_key"] == "OPS"
