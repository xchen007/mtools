from datetime import datetime, timezone
from unittest.mock import Mock

from django.test import TestCase, override_settings

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
    JiraIssueSyncMembership,
    JiraIssueScopeMembership,
    JiraSyncProfile,
    JiraSyncRun,
    SyncScope,
    SyncScope,
)
from jira_workspace.services.sync_service import SyncService


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
        assert "updated >=" in scope.effective_jql_last_run
        assert result.unchanged_checked_count == 1
        assert issue.last_synced_success_at > datetime.fromisoformat("2026-06-15T01:00:00+00:00")

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
        JIRA_SIMULATION_MODE=True,
        JIRA_SIMULATION_SCENARIO="default",
        JIRA_API_BASE_URL="https://jira.example.com",
        JIRA_API_TOKEN="token",
    )
    def test_jira_client_uses_fake_adapter_when_simulation_mode_enabled(self):
        service = SyncService()

        adapter = service._jira_client()

        assert adapter.__class__.__name__ == "FakeJiraAdapter"
