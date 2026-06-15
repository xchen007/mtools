from datetime import datetime, timezone
from unittest.mock import Mock

from django.test import TestCase, override_settings

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueSyncMembership,
    JiraIssueScopeMembership,
    JiraScopeSyncReport,
    OperationLog,
    JiraSyncProfile,
    JiraSyncRun,
    SyncScope,
)
from jira_workspace.services.sync_service import ActiveFullSyncError, SyncService


def build_issue_payload(*, key, updated_at, summary="Summary", status="To Do"):
    return {
        "issue_key": key,
        "project_key": key.split("-", 1)[0],
        "summary": summary,
        "status": status,
        "assignee": "xchen17",
        "reporter": "reporter1",
        "priority": "High",
        "updated_at": datetime.fromisoformat(updated_at),
        "created_at": datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        "sprint": "Sprint 42",
        "raw_json": '{"key": "%s"}' % key,
    }


def build_ready_self_scope():
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
        full_sync_completed_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
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
        last_full_sync_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        last_successful_check_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        last_issue_updated_cursor="2026-06-15T01:00:00+00:00",
        last_run_status=SyncScope.RunStatus.SUCCESS,
        next_run_at=datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc),
    )
    return policy, version, scope


class JiraWorkspaceSyncServiceTests(TestCase):
    def setUp(self):
        self.adapter = Mock()
        self.service = SyncService(jira_adapter=self.adapter)

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

    def test_policy_strategy_always_creates_required_self_scope_when_omitted(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={},
            strategy_hash="old-hash",
            status=GlobalSyncPolicy.Status.READY,
        )

        version = self.service.apply_policy_strategy(
            policy=policy,
            strategy_json={"scopes": []},
        )

        assert version.scopes.filter(
            scope_type=SyncScope.ScopeType.SELF_REQUIRED,
            is_required=True,
            is_system_scope=True,
        ).exists()

    def test_policy_strategy_always_creates_required_self_scope_when_false(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={},
            strategy_hash="old-hash",
            status=GlobalSyncPolicy.Status.READY,
        )

        version = self.service.apply_policy_strategy(
            policy=policy,
            strategy_json={"required_self": False, "scopes": []},
        )

        assert version.scopes.filter(
            scope_type=SyncScope.ScopeType.SELF_REQUIRED,
            is_required=True,
            is_system_scope=True,
        ).exists()

    def test_configured_policy_scopes_create_expected_base_jql_without_root_defaults(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={},
            strategy_hash="old-hash",
            status=GlobalSyncPolicy.Status.READY,
        )

        version = self.service.apply_policy_strategy(
            policy=policy,
            strategy_json={
                "required_self": True,
                "scopes": [
                    {
                        "scope_type": SyncScope.ScopeType.PROJECT,
                        "name": "OPS",
                        "project_key": "OPS",
                    },
                    {
                        "scope_type": SyncScope.ScopeType.CUSTOM_JQL,
                        "name": "Blocked OPS",
                        "jql": '  project = "OPS" AND status = "Blocked"  ',
                    },
                    {
                        "scope_type": SyncScope.ScopeType.ASSIGNEE_USER,
                        "name": "Assigned xchen17",
                        "username": "xchen17",
                    },
                    {
                        "scope_type": SyncScope.ScopeType.LABEL,
                        "name": "Ops Escalation",
                        "label": "ops-escalation",
                    },
                ],
            },
        )

        scopes_by_name = {
            scope.name: scope
            for scope in version.scopes.filter(is_system_scope=False)
        }

        assert scopes_by_name["OPS"].base_jql == 'project = "OPS"'
        assert scopes_by_name["Blocked OPS"].base_jql == (
            'project = "OPS" AND status = "Blocked"'
        )
        assert scopes_by_name["Assigned xchen17"].base_jql == 'assignee = "xchen17"'
        assert scopes_by_name["Ops Escalation"].base_jql == 'labels = "ops-escalation"'
        for scope in scopes_by_name.values():
            assert "required_self" not in scope.config_json
            assert "scopes" not in scope.config_json

    def test_unchanged_policy_strategy_returns_current_version_without_creating_new_version(self):
        policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash=SyncService._strategy_hash({"required_self": True, "scopes": []}),
            status=GlobalSyncPolicy.Status.READY,
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=1,
            strategy_hash=policy.strategy_hash,
            status=GlobalSyncPolicyVersion.Status.READY,
            full_sync_required=False,
        )
        policy.current_version = version
        policy.save(update_fields=["current_version", "updated_at"])

        returned_version = self.service.apply_policy_strategy(
            policy=policy,
            strategy_json={"required_self": True, "scopes": []},
        )

        assert returned_version == version
        assert GlobalSyncPolicyVersion.objects.filter(policy=policy).count() == 1

    def test_incremental_scope_sync_uses_cursor_overlap_and_updates_success_time_for_unchanged_issue(self):
        policy, version, scope = build_ready_self_scope()
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
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
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(key="OPS-778", updated_at="2026-06-15T01:00:00+00:00")
        ]

        result = SyncService(jira_adapter=self.adapter).run_scope_incremental(scope)

        issue.refresh_from_db()
        scope.refresh_from_db()
        assert (
            scope.effective_jql_last_run
            == '(assignee = currentUser() OR reporter = currentUser()) AND updated >= "2026-06-15T01:00:00+00:00" ORDER BY updated ASC, key ASC'
        )
        assert result.unchanged_checked_count == 1
        assert issue.last_synced_success_at > datetime.fromisoformat("2026-06-15T01:00:00+00:00")

    def test_incremental_scope_sync_rejects_scope_without_prior_full_sync(self):
        _, _, scope = build_ready_self_scope()
        scope.last_full_sync_at = None
        scope.save(update_fields=["last_full_sync_at", "updated_at"])

        with self.assertRaisesMessage(
            ValueError,
            "Incremental scope sync requires a prior full sync.",
        ):
            self.service.run_scope_incremental(scope)

    def test_failed_scope_sync_persists_failed_status_and_error_message(self):
        _, _, scope = build_ready_self_scope()
        self.adapter.fetch_issues.side_effect = RuntimeError("jira outage")

        with self.assertRaisesMessage(RuntimeError, "jira outage"):
            self.service.run_scope_incremental(scope)

        scope.refresh_from_db()
        assert scope.last_run_status == SyncScope.RunStatus.FAILED
        assert scope.last_error_message == "jira outage"

    def test_full_scope_sync_recomputes_cursor_from_returned_issues(self):
        _, _, scope = build_ready_self_scope()
        scope.last_issue_updated_cursor = "2026-06-16T01:00:00+00:00"
        scope.save(update_fields=["last_issue_updated_cursor", "updated_at"])
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(key="OPS-778", updated_at="2026-06-15T01:00:00+00:00")
        ]

        self.service.run_scope_full(scope)

        scope.refresh_from_db()
        assert scope.last_issue_updated_cursor == "2026-06-15T01:00:00+00:00"

    def test_full_scope_sync_clears_cursor_when_no_issues_return(self):
        _, _, scope = build_ready_self_scope()
        scope.last_issue_updated_cursor = "2026-06-16T01:00:00+00:00"
        scope.save(update_fields=["last_issue_updated_cursor", "updated_at"])
        self.adapter.fetch_issues.return_value = []

        self.service.run_scope_full(scope)

        scope.refresh_from_db()
        assert scope.last_issue_updated_cursor is None

    def test_full_scope_sync_deactivates_missing_memberships(self):
        _, version, scope = build_ready_self_scope()
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
            raw_json='{"key":"OPS-778"}',
            last_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )
        self.adapter.fetch_issues.return_value = []

        result = self.service.run_scope_full(scope)

        membership.refresh_from_db()
        assert result.deactivated_membership_count == 1
        assert membership.is_active is False

    def test_full_scope_sync_keeps_returned_memberships_active(self):
        _, version, scope = build_ready_self_scope()
        returned_issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
            raw_json='{"key":"OPS-778"}',
            last_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        missing_issue = JiraIssue.objects.create(
            issue_key="OPS-999",
            project_key="OPS",
            summary="Missing",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
            raw_json='{"key":"OPS-999"}',
            last_seen_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        returned_membership = JiraIssueScopeMembership.objects.create(
            issue=returned_issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_seen_issue_updated_at=returned_issue.updated_at,
            is_active=True,
        )
        missing_membership = JiraIssueScopeMembership.objects.create(
            issue=missing_issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-14T01:00:00+00:00"),
            last_seen_issue_updated_at=missing_issue.updated_at,
            is_active=True,
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(key="OPS-778", updated_at="2026-06-15T01:00:00+00:00")
        ]

        result = self.service.run_scope_full(scope)

        returned_membership.refresh_from_db()
        missing_membership.refresh_from_db()
        assert result.deactivated_membership_count == 1
        assert returned_membership.is_active is True
        assert missing_membership.is_active is False

    def test_scope_sync_persists_run_report_counts(self):
        _, version, scope = build_ready_self_scope()
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
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
        self.adapter.fetch_issues.return_value = []

        self.service.run_scope_full(scope)

        report = JiraScopeSyncReport.objects.get(scope=scope)
        assert report.policy_version == version
        assert report.run_type == JiraScopeSyncReport.RunType.FULL
        assert report.status == JiraScopeSyncReport.Status.SUCCESS
        assert report.fetched_count == 0
        assert report.inserted_count == 0
        assert report.updated_count == 0
        assert report.unchanged_checked_count == 0
        assert report.deactivated_membership_count == 1
        assert report.effective_jql == scope.base_jql

    def test_run_due_scopes_executes_queued_full_scope_reports(self):
        _, _, scope = build_ready_self_scope()
        scope.last_run_status = SyncScope.RunStatus.QUEUED_FULL
        scope.next_run_at = datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc)
        scope.save(update_fields=["last_run_status", "next_run_at", "updated_at"])
        self.adapter.fetch_issues.return_value = []

        reports = self.service.run_due_scopes(now=datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc))

        scope.refresh_from_db()
        assert len(reports) == 1
        assert reports[0].scope == scope
        assert reports[0].run_type == JiraScopeSyncReport.RunType.FULL
        assert scope.last_run_status == SyncScope.RunStatus.SUCCESS
        assert scope.next_run_at == datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    def test_run_due_scopes_ignores_stale_policy_version_scopes(self):
        policy, _current_version, current_scope = build_ready_self_scope()
        current_scope.next_run_at = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
        current_scope.save(update_fields=["next_run_at", "updated_at"])
        stale_version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=2,
            strategy_hash="hash-stale",
            status=GlobalSyncPolicyVersion.Status.STALE,
            full_sync_required=True,
        )
        stale_scope = SyncScope.objects.create(
            policy_version=stale_version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="Stale OPS",
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "OPS"},
            base_jql='project = "OPS"',
            last_run_status=SyncScope.RunStatus.QUEUED_FULL,
            next_run_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        )
        self.adapter.fetch_issues.return_value = []

        reports = self.service.run_due_scopes(
            now=datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc)
        )

        stale_scope.refresh_from_db()
        assert reports == []
        assert stale_scope.last_run_status == SyncScope.RunStatus.QUEUED_FULL
        self.adapter.fetch_issues.assert_not_called()

    def test_full_scope_sync_marks_policy_ready_after_all_current_scopes_complete(self):
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
            last_run_status=SyncScope.RunStatus.QUEUED_FULL,
            next_run_at=datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc),
        )
        self.adapter.fetch_issues.return_value = []

        self.service.run_scope_full(scope)

        policy.refresh_from_db()
        version.refresh_from_db()
        assert version.status == GlobalSyncPolicyVersion.Status.READY
        assert version.full_sync_required is False
        assert version.full_sync_completed_at is not None
        assert policy.status == GlobalSyncPolicy.Status.READY
        assert policy.last_version_built_at == version.full_sync_completed_at

    def test_full_scope_sync_marks_issue_inactive_when_last_policy_membership_deactivates(self):
        _, version, scope = build_ready_self_scope()
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
            raw_json='{"key":"OPS-778"}',
            last_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )
        self.adapter.fetch_issues.return_value = []

        result = self.service.run_scope_full(scope)

        issue.refresh_from_db()
        membership.refresh_from_db()
        assert result.deactivated_membership_count == 1
        assert membership.is_active is False
        assert membership.last_checked_at == scope.last_successful_check_at
        assert membership.last_synced_success_at == scope.last_successful_check_at
        assert issue.is_active_in_current_policy is False

    def test_full_scope_sync_keeps_issue_active_when_another_policy_membership_remains(self):
        _, version, scope = build_ready_self_scope()
        other_scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="OPS",
            is_required=False,
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "OPS"},
            base_jql='project = "OPS"',
            next_run_at=datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc),
        )
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            updated_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            sprint="Sprint 42",
            raw_json='{"key":"OPS-778"}',
            last_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )
        JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=other_scope,
            policy_version=version,
            first_seen_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_checked_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_synced_success_at=datetime.fromisoformat("2026-06-15T01:00:00+00:00"),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )
        self.adapter.fetch_issues.return_value = []

        result = self.service.run_scope_full(scope)

        issue.refresh_from_db()
        membership.refresh_from_db()
        assert result.deactivated_membership_count == 1
        assert membership.is_active is False
        assert issue.is_active_in_current_policy is True

    def test_incremental_sync_inserts_a_new_issue(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={},
            jql="",
        )
        self.adapter.fetch_current_user.return_value = "xchen17"
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="TESS-321",
                updated_at="2026-06-12T08:30:00+00:00",
                summary="Refine query presets",
                status="In Progress",
            )
        ]

        result = self.service.incremental_sync(profile)

        issue = JiraIssue.objects.get(issue_key="TESS-321")
        profile.refresh_from_db()
        assert result.fetched_count == 1
        assert result.inserted_count == 1
        assert result.updated_count == 0
        assert result.skipped_count == 0
        assert issue.reporter == "reporter1"
        assert issue.priority == "High"
        assert profile.last_cursor == "2026-06-12T08:30:00+00:00"
        assert profile.last_incremental_sync_at is not None
        assert profile.params_json["username"] == "xchen17"
        assert JiraIssueSyncMembership.objects.filter(profile=profile, issue=issue).exists()

    def test_incremental_sync_uses_stored_username_when_identity_refresh_is_blocked(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
        )
        self.adapter.fetch_current_user.side_effect = Exception(
            "403 Client Error: Forbidden for url: https://jira.example.com/rest/api/2/myself"
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="OPS-778",
                updated_at="2026-06-12T10:30:00+00:00",
                summary="Escalate blocker handling",
                status="Blocked",
            )
        ]

        result = self.service.incremental_sync(profile)

        issue = JiraIssue.objects.get(issue_key="OPS-778")
        profile.refresh_from_db()
        assert result.fetched_count == 1
        assert result.inserted_count == 1
        assert profile.params_json["username"] == "xchen17"
        assert issue.assignee == "xchen17"

    def test_incremental_sync_updates_existing_issue_when_updated_at_changes(self):
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Old summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="Medium",
            sprint="Sprint 41",
            updated_at="2026-06-10T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"TESS-321","version":"old"}',
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="TESS-321",
                updated_at="2026-06-12T08:30:00+00:00",
                summary="New summary",
                status="Done",
            )
        ]

        result = self.service.incremental_sync(profile)

        issue = JiraIssue.objects.get(issue_key="TESS-321")
        assert result.updated_count == 1
        assert issue.summary == "New summary"
        assert issue.status == "Done"
        assert issue.updated_at.isoformat() == "2026-06-12T08:30:00+00:00"
        assert issue.priority == "High"

    def test_incremental_sync_increments_skipped_count_for_unchanged_issue(self):
        JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Stable summary",
            status="In Progress",
            assignee="xchen17",
            reporter="reporter1",
            priority="High",
            sprint="Sprint 42",
            updated_at="2026-06-12T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"TESS-321"}',
            last_seen_at="2026-06-12T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Custom Filter",
            profile_type=JiraSyncProfile.ProfileType.CUSTOM_JQL,
            params_json={"jql": 'project = "TESS"'},
            jql='project = "TESS"',
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="TESS-321",
                updated_at="2026-06-12T08:30:00+00:00",
                summary="Stable summary",
                status="In Progress",
            )
        ]

        result = self.service.incremental_sync(profile)

        assert result.inserted_count == 0
        assert result.updated_count == 0
        assert result.skipped_count == 1

    def test_full_sync_refreshes_cached_fields_when_updated_at_is_unchanged(self):
        JiraIssue.objects.create(
            issue_key="SDSTOR-22591",
            project_key="SDSTOR",
            summary="Resolve stubborn heal issues",
            status="Resolved",
            assignee="xchen17",
            reporter="xchen17",
            priority="P3",
            sprint="xchen17",
            updated_at="2026-06-05T12:17:41+00:00",
            created_at="2026-06-05T11:28:00+00:00",
            raw_json='{"key":"SDSTOR-22591","version":"old"}',
            last_seen_at="2026-06-15T05:13:51+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={},
            jql="",
        )
        self.adapter.fetch_current_user.return_value = "xchen17"
        self.adapter.fetch_issues.return_value = [
            {
                **build_issue_payload(
                    key="SDSTOR-22591",
                    updated_at="2026-06-05T12:17:41+00:00",
                    summary="Resolve stubborn heal issues",
                    status="Resolved",
                ),
                "project_key": "SDSTOR",
                "reporter": "xchen17",
                "priority": "P3",
                "sprint": "SDS-CP-Sprint11-2026",
                "raw_json": '{"key":"SDSTOR-22591","version":"new"}',
            }
        ]

        result = self.service.full_sync(profile)

        issue = JiraIssue.objects.get(issue_key="SDSTOR-22591")
        assert result.updated_count == 1
        assert result.skipped_count == 0
        assert issue.sprint == "SDS-CP-Sprint11-2026"
        assert issue.raw_json == '{"key":"SDSTOR-22591","version":"new"}'

    def test_build_jql_differs_for_supported_profile_types(self):
        my_profile = JiraSyncProfile(
            name="Mine",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={},
            jql="",
        )
        project_profile = JiraSyncProfile(
            name="Project",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        custom_profile = JiraSyncProfile(
            name="Custom",
            profile_type=JiraSyncProfile.ProfileType.CUSTOM_JQL,
            params_json={"jql": 'project = "OPS" AND status = "Done"'},
            jql="",
        )
        self.adapter.fetch_current_user.return_value = "xchen17"

        my_jql = self.service.build_jql(my_profile)
        project_jql = self.service.build_jql(project_profile)
        custom_jql = self.service.build_jql(custom_profile)

        assert my_jql == "assignee = currentUser() ORDER BY updated DESC"
        assert project_jql == 'project = "TESS" ORDER BY updated DESC'
        assert custom_jql == 'project = "OPS" AND status = "Done"'

    def test_incremental_sync_persists_base_profile_jql_without_cursor_clause(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
            last_cursor="2026-06-11T08:30:00+00:00",
        )
        self.adapter.fetch_issues.return_value = []

        self.service.incremental_sync(profile)

        profile.refresh_from_db()
        assert profile.jql == 'project = "TESS" ORDER BY updated DESC'

    def test_build_jql_wraps_custom_or_clause_before_appending_cursor(self):
        profile = JiraSyncProfile(
            name="Custom",
            profile_type=JiraSyncProfile.ProfileType.CUSTOM_JQL,
            params_json={"jql": 'project = "OPS" OR status = "Done"'},
            jql="",
        )

        jql = self.service.build_jql(
            profile,
            updated_since="2026-06-11T08:30:00+00:00",
        )

        assert (
            jql
            == '(project = "OPS" OR status = "Done") AND updated >= "2026-06-11T08:30:00+00:00" ORDER BY updated DESC'
        )

    def test_build_jql_preserves_existing_order_by_when_appending_cursor(self):
        profile = JiraSyncProfile(
            name="Custom",
            profile_type=JiraSyncProfile.ProfileType.CUSTOM_JQL,
            params_json={
                "jql": 'project = "OPS"\norder by priority DESC, updated ASC'
            },
            jql="",
        )

        jql = self.service.build_jql(
            profile,
            updated_since="2026-06-11T08:30:00+00:00",
        )

        assert (
            jql
            == '(project = "OPS") AND updated >= "2026-06-11T08:30:00+00:00" order by priority DESC, updated ASC'
        )

    def test_full_sync_removes_orphaned_issue_when_profile_no_longer_returns_it(self):
        issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Old summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="Medium",
            sprint="Sprint 41",
            updated_at="2026-06-10T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"TESS-321","version":"old"}',
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=profile,
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        self.adapter.fetch_issues.return_value = []

        self.service.full_sync(profile)

        assert JiraIssue.objects.filter(issue_key="TESS-321").exists() is False
        assert JiraIssueSyncMembership.objects.filter(profile=profile).exists() is False

    def test_full_sync_keeps_issue_when_another_profile_still_references_it(self):
        issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Old summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="Medium",
            sprint="Sprint 41",
            updated_at="2026-06-10T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"TESS-321","version":"old"}',
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        other_profile = JiraSyncProfile.objects.create(
            name="Project OPS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "OPS"},
            jql="",
        )
        JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=profile,
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=other_profile,
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        self.adapter.fetch_issues.return_value = []

        self.service.full_sync(profile)

        assert JiraIssue.objects.filter(issue_key="TESS-321").exists() is True
        assert JiraIssueSyncMembership.objects.filter(profile=profile).exists() is False
        assert JiraIssueSyncMembership.objects.filter(profile=other_profile).exists() is True

    def test_full_sync_keeps_issue_when_policy_membership_remains(self):
        issue = JiraIssue.objects.create(
            issue_key="OPS-100",
            project_key="OPS",
            summary="Policy-only issue",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="Medium",
            sprint="Sprint 41",
            updated_at="2026-06-10T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"OPS-100","version":"old"}',
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Project OPS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "OPS"},
            jql="",
        )
        other_policy = GlobalSyncPolicy.objects.create(
            name="Policy OPS",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-v1",
            status=GlobalSyncPolicy.Status.READY,
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=other_policy,
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
            next_run_at=datetime(2026, 6, 12, 8, 30, tzinfo=timezone.utc),
        )
        JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=profile,
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=datetime(2026, 6, 10, 8, 30, tzinfo=timezone.utc),
            last_checked_at=datetime(2026, 6, 10, 8, 30, tzinfo=timezone.utc),
            last_synced_success_at=datetime(2026, 6, 10, 8, 30, tzinfo=timezone.utc),
            last_seen_issue_updated_at=datetime(2026, 6, 10, 8, 30, tzinfo=timezone.utc),
            is_active=True,
        )
        self.adapter.fetch_issues.return_value = []

        self.service.full_sync(profile)

        assert JiraIssueSyncMembership.objects.filter(profile=profile, issue=issue).exists() is False
        assert JiraIssue.objects.filter(issue_key="OPS-100").exists() is True
        assert JiraIssueScopeMembership.objects.filter(
            issue=issue,
            scope=scope,
            is_active=True,
        ).exists()

    def test_incremental_sync_does_not_remove_absent_memberships(self):
        issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Old summary",
            status="To Do",
            assignee="xchen17",
            reporter="reporter1",
            priority="Medium",
            sprint="Sprint 41",
            updated_at="2026-06-10T08:30:00+00:00",
            created_at="2026-06-01T09:00:00+00:00",
            raw_json='{"key":"TESS-321","version":"old"}',
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
            last_cursor="2026-06-11T08:30:00+00:00",
        )
        JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=profile,
            last_seen_at="2026-06-10T08:30:00+00:00",
        )
        self.adapter.fetch_issues.return_value = []

        self.service.incremental_sync(profile)

        assert JiraIssue.objects.filter(issue_key="TESS-321").exists() is True
        assert JiraIssueSyncMembership.objects.filter(profile=profile, issue=issue).exists()

    def test_full_sync_writes_success_sync_run(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="TESS-999",
                updated_at="2026-06-12T08:30:00+00:00",
            )
        ]

        result = self.service.full_sync(profile)

        run = JiraSyncRun.objects.get(profile=profile)
        profile.refresh_from_db()
        assert result.inserted_count == 1
        assert run.run_type == JiraSyncRun.RunType.FULL
        assert run.status == JiraSyncRun.Status.SUCCESS
        assert run.finished_at is not None
        assert run.fetched_count == 1
        assert profile.last_full_sync_at is not None

    def test_enqueue_sync_creates_queued_run_without_executing_immediately(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )

        run = self.service.enqueue_sync(
            profile,
            JiraSyncRun.RunType.FULL,
            start_background=False,
        )

        assert run.status == JiraSyncRun.Status.QUEUED
        assert run.run_type == JiraSyncRun.RunType.FULL
        assert run.progress_message == "Queued"
        self.adapter.fetch_issues.assert_not_called()

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
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.QUEUED,
            started_at=datetime.now(timezone.utc),
            progress_message="Queued",
        )

        before_count = JiraSyncRun.objects.count()

        with self.assertRaises(ActiveFullSyncError):
            self.service.enqueue_sync(
                profile,
                JiraSyncRun.RunType.INCREMENTAL,
                start_background=False,
            )

        assert JiraSyncRun.objects.count() == before_count

    def test_enqueue_sync_rejects_full_when_another_full_run_is_running(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            progress_message="Fetched 10 issues.",
        )

        before_count = JiraSyncRun.objects.count()

        with self.assertRaises(ActiveFullSyncError):
            self.service.enqueue_sync(
                profile,
                JiraSyncRun.RunType.FULL,
                start_background=False,
            )

        assert JiraSyncRun.objects.count() == before_count

    def test_sync_progress_updates_run_during_fetch(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )

        def fetch_issues(jql, progress_callback=None):
            progress_callback(1, 2)
            progress_callback(2, 2)
            return [
                build_issue_payload(
                    key="TESS-999",
                    updated_at="2026-06-12T08:30:00+00:00",
                ),
                build_issue_payload(
                    key="TESS-1000",
                    updated_at="2026-06-12T09:30:00+00:00",
                ),
            ]

        self.adapter.fetch_issues.side_effect = fetch_issues

        self.service.full_sync(profile)

        run = JiraSyncRun.objects.get(profile=profile)
        assert run.progress_current_count == 2
        assert run.progress_total_count == 2
        assert run.progress_message == "Stored 2 fetched issues."

    def test_full_sync_creates_success_operation_log(self):
        profile = JiraSyncProfile.objects.create(
            name="Project TESS",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "TESS"},
            jql="",
        )
        self.adapter.fetch_issues.return_value = [
            build_issue_payload(
                key="TESS-999",
                updated_at="2026-06-12T08:30:00+00:00",
            )
        ]

        self.service.full_sync(profile)

        log = OperationLog.objects.get(
            tool=OperationLog.Tool.JIRA_SYNC,
            action=JiraSyncRun.RunType.FULL,
        )
        assert log.status == OperationLog.Status.SUCCESS
        assert "Fetched 1 issues" in log.result_summary
        assert log.target_type == "jira_sync_profile"
        assert log.target_id == str(profile.id)

    def test_sync_status_reports_external_blocker_for_403_failure(self):
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
            started_at=datetime(2026, 6, 12, 8, 30, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 12, 8, 31, tzinfo=timezone.utc),
            error_message="Jira returned 403: The request is blocked.",
        )

        status = self.service.build_sync_status()

        assert status["has_external_blocker"] is True
        assert status["blocker_message"] == "External Jira access is currently blocked."
        assert status["latest_failure"].error_message == "Jira returned 403: The request is blocked."

    def test_sync_status_reports_external_blocker_for_generic_403_forbidden_error(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.FAILED,
            started_at=datetime.now(timezone.utc),
            error_message="403 Client Error: Forbidden for url: https://jira.example.com/rest/api/2/myself",
        )

        status = self.service.build_sync_status()

        assert status["has_external_blocker"] is True
        assert status["blocker_message"] == "External Jira access is currently blocked."

    @override_settings(
        JIRA_API_BASE_URL="https://jira.example.com",
        JIRA_API_TOKEN="token",
    )
    def test_jira_client_uses_live_adapter_from_configured_settings(self):
        service = SyncService()

        adapter = service._jira_client()

        assert adapter.__class__.__name__ == "JiraAdapter"
