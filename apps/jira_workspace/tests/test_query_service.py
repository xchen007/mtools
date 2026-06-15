from datetime import datetime, timedelta, timezone

from django.test import TestCase

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
    SyncScope,
)
from jira_workspace.services.query_service import (
    build_issue_filter_options,
    build_issue_queryset,
    serving_global_sync_policy_version,
)
from jira_workspace.services.stats_service import build_dashboard_project_groups


def create_current_policy_scope():
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
    policy.current_version = version
    policy.save(update_fields=["current_version", "updated_at"])
    scope = SyncScope.objects.create(
        policy_version=version,
        scope_type=SyncScope.ScopeType.SELF_REQUIRED,
        name="My Assigned or Reported Issues",
        is_required=True,
        is_enabled=True,
        is_system_scope=True,
        schedule_minutes=30,
        config_json={"mode": "self"},
        base_jql="assignee = currentUser() OR reporter = currentUser()",
        next_run_at=datetime.now(timezone.utc),
    )
    return policy, version, scope


def add_policy_membership(*, issue, scope, version, is_active=True):
    JiraIssueScopeMembership.objects.create(
        issue=issue,
        scope=scope,
        policy_version=version,
        first_seen_at=datetime.now(timezone.utc),
        last_checked_at=datetime.now(timezone.utc),
        last_synced_success_at=datetime.now(timezone.utc),
        last_seen_issue_updated_at=issue.updated_at,
        is_active=is_active,
    )


def build_policy_scoped_issues():
    _, version, scope = create_current_policy_scope()
    active_issue = JiraIssue.objects.create(
        issue_key="OPS-100",
        project_key="OPS",
        summary="Active issue",
        status="In Progress",
        assignee="xchen17",
        reporter="amy",
        priority="High",
        updated_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        raw_json="{}",
        last_seen_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        is_active_in_current_policy=True,
    )
    inactive_issue = JiraIssue.objects.create(
        issue_key="AAA-100",
        project_key="AAA",
        summary="Inactive issue",
        status="To Do",
        assignee="xchen17",
        reporter="amy",
        priority="Low",
        updated_at=datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        raw_json="{}",
        last_seen_at=datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc),
        is_active_in_current_policy=True,
    )
    add_policy_membership(
        issue=active_issue,
        scope=scope,
        version=version,
        is_active=True,
    )
    add_policy_membership(
        issue=inactive_issue,
        scope=scope,
        version=version,
        is_active=False,
    )
    return active_issue, inactive_issue, version


class JiraWorkspaceQueryServiceTests(TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        _, self.version, self.scope = create_current_policy_scope()
        self.assigned_issue = JiraIssue.objects.create(
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
        self.reported_issue = JiraIssue.objects.create(
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
        self.older_assigned_issue = JiraIssue.objects.create(
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
        self.created_alpha_issue = JiraIssue.objects.create(
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
        self.other_team_issue = JiraIssue.objects.create(
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
        for issue in [
            self.assigned_issue,
            self.reported_issue,
            self.older_assigned_issue,
            self.created_alpha_issue,
            self.other_team_issue,
        ]:
            add_policy_membership(
                issue=issue,
                scope=self.scope,
                version=self.version,
                is_active=True,
            )

    def test_build_issue_queryset_excludes_inactive_membership_rows_by_default(self):
        GlobalSyncPolicy.objects.all().delete()
        JiraIssue.objects.all().delete()
        active_issue, _, _ = build_policy_scoped_issues()

        queryset = build_issue_queryset(username="xchen17")

        assert list(queryset.values_list("issue_key", flat=True)) == [active_issue.issue_key]

    def test_build_issue_queryset_uses_only_current_policy_version_memberships(self):
        active_issue = self.assigned_issue
        stale_only_issue = JiraIssue.objects.create(
            issue_key="OLD-100",
            project_key="OLD",
            summary="Old policy only",
            status="In Progress",
            assignee="xchen17",
            reporter="amy",
            priority="Low",
            updated_at=self.now,
            created_at=self.now,
            raw_json="{}",
            last_seen_at=self.now,
            is_active_in_current_policy=True,
        )
        stale_policy = GlobalSyncPolicy.objects.create(
            name="Stale Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-stale",
            status=GlobalSyncPolicy.Status.STALE,
        )
        stale_version = GlobalSyncPolicyVersion.objects.create(
            policy=stale_policy,
            version_no=1,
            strategy_hash="hash-stale",
            status=GlobalSyncPolicyVersion.Status.STALE,
            full_sync_required=True,
        )
        stale_policy.current_version = stale_version
        stale_policy.save(update_fields=["current_version", "updated_at"])
        stale_scope = SyncScope.objects.create(
            policy_version=stale_version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="Stale TESS",
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "TESS"},
            base_jql='project = "TESS"',
            next_run_at=self.now,
        )
        add_policy_membership(
            issue=active_issue,
            scope=stale_scope,
            version=stale_version,
            is_active=True,
        )
        add_policy_membership(
            issue=stale_only_issue,
            scope=stale_scope,
            version=stale_version,
            is_active=True,
        )
        queryset = build_issue_queryset(username="xchen17", source="assigned")

        issue_keys = list(queryset.values_list("issue_key", flat=True))
        assert issue_keys.count("TESS-321") == 1
        assert "OLD-100" not in issue_keys

    def test_build_issue_queryset_returns_empty_when_no_current_policy_version_exists(self):
        GlobalSyncPolicy.objects.all().delete()
        self.assigned_issue.is_active_in_current_policy = True
        self.assigned_issue.save(update_fields=["is_active_in_current_policy"])

        queryset = build_issue_queryset(username="xchen17", source="assigned")

        assert list(queryset.values_list("issue_key", flat=True)) == []

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

    def test_build_issue_filter_options_counts_only_current_policy_active_issues(self):
        GlobalSyncPolicy.objects.all().delete()
        JiraIssue.objects.all().delete()
        build_policy_scoped_issues()

        options = build_issue_filter_options(username="xchen17")

        assert options["project_options"] == ["OPS"]

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

    def test_build_dashboard_project_groups_does_not_double_count_multi_scope_issues(self):
        extra_scope = SyncScope.objects.create(
            policy_version=self.version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="TESS",
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "TESS"},
            base_jql='project = "TESS"',
            next_run_at=self.now,
        )
        add_policy_membership(
            issue=self.assigned_issue,
            scope=extra_scope,
            version=self.version,
            is_active=True,
        )

        groups = build_dashboard_project_groups(username="xchen17")

        assert groups["assigned"][0]["project_key"] == "TESS"
        assert groups["assigned"][0]["issue_count"] == 2
