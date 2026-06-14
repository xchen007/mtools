from datetime import datetime, timedelta, timezone

from django.test import TestCase

from jira_workspace.models import JiraIssue
from jira_workspace.services.query_service import (
    build_issue_filter_options,
    build_issue_queryset,
)
from jira_workspace.services.stats_service import build_dashboard_project_groups


class JiraWorkspaceQueryServiceTests(TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Assigned issue",
            status="In Progress",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            sprint="Sprint 42",
            issue_type="Bug",
            labels_json=["backend", "urgent"],
            updated_at=self.now - timedelta(days=1),
            created_at=self.now - timedelta(days=2),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Reported issue",
            status="Blocked",
            assignee="ravi",
            reporter="xchen17",
            priority="Highest",
            sprint="Sprint 41",
            issue_type="Incident",
            labels_json=["urgent", "customer-impact"],
            updated_at=self.now - timedelta(days=2),
            created_at=self.now - timedelta(days=3),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="TESS-400",
            project_key="TESS",
            summary="Older assigned alpha",
            status="To Do",
            assignee="xchen17",
            reporter="nina",
            priority="Low",
            sprint="Sprint 42",
            issue_type="Task",
            labels_json=["backend"],
            updated_at=self.now - timedelta(days=3),
            created_at=self.now - timedelta(days=4),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="AAA-100",
            project_key="AAA",
            summary="Created alpha",
            status="Done",
            assignee="li",
            reporter="xchen17",
            priority="Medium",
            sprint="Sprint 40",
            issue_type="Story",
            labels_json=["frontend"],
            updated_at=self.now - timedelta(days=4),
            created_at=self.now - timedelta(days=5),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="OPS-900",
            project_key="OPS",
            summary="Other team issue",
            status="Review",
            assignee="maria",
            reporter="noah",
            priority="High",
            sprint="Sprint 42",
            issue_type="Bug",
            labels_json=["backend", "triage"],
            updated_at=self.now - timedelta(hours=6),
            created_at=self.now - timedelta(days=1),
            raw_json="{}",
            last_seen_at=self.now,
        )

    def test_build_issue_queryset_filters_by_source_semantics(self):
        qs = build_issue_queryset(
            username="xchen17",
            source="assigned",
            project_key="TESS",
        )

        assert list(qs.values_list("issue_key", flat=True)) == ["TESS-321", "TESS-400"]

    def test_build_issue_queryset_filters_reported_issues_for_created_source(self):
        qs = build_issue_queryset(username="xchen17", source="created")

        assert list(qs.values_list("issue_key", flat=True)) == ["OPS-778", "AAA-100"]

    def test_build_issue_queryset_returns_assigned_and_reported_issues_for_all_source(self):
        qs = build_issue_queryset(username="xchen17", source="all")

        assert list(qs.values_list("issue_key", flat=True)) == [
            "TESS-321",
            "OPS-778",
            "TESS-400",
            "AAA-100",
        ]

    def test_build_issue_queryset_filters_by_updated_at_range(self):
        qs = build_issue_queryset(
            username="xchen17",
            start=self.now - timedelta(days=2, hours=12),
            end=self.now - timedelta(days=1, hours=12),
        )

        assert list(qs.values_list("issue_key", flat=True)) == ["OPS-778"]

    def test_build_issue_queryset_filters_by_search_term(self):
        qs = build_issue_queryset(username="xchen17", search="alpha")

        assert list(qs.values_list("issue_key", flat=True)) == ["TESS-400", "AAA-100"]

    def test_build_issue_queryset_filters_by_explicit_people_with_inclusive_or(self):
        qs = build_issue_queryset(
            username="xchen17",
            assignee="maria",
            reporter="xchen17",
        )

        assert list(qs.values_list("issue_key", flat=True)) == ["OPS-900", "OPS-778", "AAA-100"]

    def test_build_issue_queryset_without_people_filters_includes_all_people(self):
        qs = build_issue_queryset(username="xchen17", assignee="", reporter="")

        assert list(qs.values_list("issue_key", flat=True)) == [
            "OPS-900",
            "TESS-321",
            "OPS-778",
            "TESS-400",
            "AAA-100",
        ]

    def test_build_issue_queryset_filters_by_labels_sprint_type_and_priority(self):
        qs = build_issue_queryset(
            username="xchen17",
            assignee="",
            reporter="",
            labels=["backend", "urgent"],
            sprint="Sprint 42",
            issue_type="Bug",
            priority="High",
        )

        assert list(qs.values_list("issue_key", flat=True)) == ["TESS-321"]

    def test_build_issue_filter_options_prioritizes_my_projects_by_all_time_counts(self):
        options = build_issue_filter_options(username="xchen17")

        assert options["project_options"][0] == "TESS"
        assert set(options["project_options"][1:3]) == {"OPS", "AAA"}
        assert "backend" in options["label_options"]
        assert "Bug" in options["issue_type_options"]
        assert "Sprint 42" in options["sprint_options"]

    def test_build_issue_queryset_sorts_by_summary_in_ascending_order(self):
        qs = build_issue_queryset(
            username="xchen17",
            sort_by="summary",
            sort_order="asc",
        )

        assert list(qs.values_list("issue_key", flat=True)) == [
            "TESS-321",
            "AAA-100",
            "TESS-400",
            "OPS-778",
        ]

    def test_build_issue_queryset_rejects_unknown_source(self):
        with self.assertRaisesMessage(
            ValueError,
            "Invalid source 'watched'. Expected one of: all, assigned, created.",
        ):
            build_issue_queryset(username="xchen17", source="watched")

    def test_build_issue_queryset_rejects_unknown_sort_by(self):
        with self.assertRaisesMessage(
            ValueError,
            "Invalid sort_by 'raw_json'. Expected one of: assignee, created_at, issue_key, issue_type, priority, project_key, reporter, status, summary, updated_at.",
        ):
            build_issue_queryset(username="xchen17", sort_by="raw_json")

    def test_build_issue_queryset_rejects_unknown_sort_order(self):
        with self.assertRaisesMessage(
            ValueError,
            "Invalid sort_order 'sideways'. Expected one of: asc, desc.",
        ):
            build_issue_queryset(username="xchen17", sort_order="sideways")

    def test_build_dashboard_project_groups_returns_counts_in_expected_order(self):
        groups = build_dashboard_project_groups(username="xchen17")

        assert groups["assigned"][0]["project_key"] == "TESS"
        assert groups["assigned"][0]["issue_count"] == 2
        assert groups["created"] == [
            {"project_key": "AAA", "issue_count": 1},
            {"project_key": "OPS", "issue_count": 1},
        ]
