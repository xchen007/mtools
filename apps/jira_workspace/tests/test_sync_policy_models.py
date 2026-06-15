from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueSyncMembership,
    JiraIssueScopeMembership,
    JiraSyncProfile,
    SyncScope,
)


class JiraGlobalSyncPolicyModelTests(TestCase):
    def test_policy_creates_single_current_version_pointer(self):
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

        policy.refresh_from_db()
        assert policy.current_version_id == version.id

    def test_self_scope_is_marked_required_and_system_managed(self):
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

        scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.SELF_REQUIRED,
            name="My Assigned or Reported Issues",
            is_required=True,
            is_enabled=True,
            is_system_scope=True,
            schedule_minutes=30,
            config_json={"mode": "self"},
            base_jql="assignee = currentUser() OR reporter = currentUser() ORDER BY updated DESC",
            next_run_at=timezone.now(),
        )

        assert scope.is_required is True
        assert scope.is_system_scope is True

    def test_policy_rejects_current_version_from_different_policy(self):
        first_policy = GlobalSyncPolicy.objects.create(
            name="Primary Jira Policy",
            strategy_json={"required_self": True, "scopes": []},
            strategy_hash="hash-v1",
            status=GlobalSyncPolicy.Status.STALE,
        )
        other_policy = GlobalSyncPolicy.objects.create(
            name="Secondary Jira Policy",
            strategy_json={"required_self": False, "scopes": []},
            strategy_hash="hash-v2",
            status=GlobalSyncPolicy.Status.STALE,
        )
        other_version = GlobalSyncPolicyVersion.objects.create(
            policy=other_policy,
            version_no=1,
            strategy_hash="hash-v2",
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )

        first_policy.current_version = other_version

        with self.assertRaises(ValidationError):
            first_policy.save()

    def test_policy_rejects_current_version_on_initial_create(self):
        other_policy = GlobalSyncPolicy.objects.create(
            name="Secondary Jira Policy",
            strategy_json={"required_self": False, "scopes": []},
            strategy_hash="hash-v2",
            status=GlobalSyncPolicy.Status.STALE,
        )
        other_version = GlobalSyncPolicyVersion.objects.create(
            policy=other_policy,
            version_no=1,
            strategy_hash="hash-v2",
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )

        with self.assertRaises(ValidationError):
            GlobalSyncPolicy.objects.create(
                name="Bad Policy",
                strategy_json={},
                strategy_hash="bad",
                current_version=other_version,
            )

    def test_issue_membership_can_be_marked_inactive_without_deleting_issue(self):
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
        scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="OPS",
            is_required=False,
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "OPS"},
            base_jql='project = "OPS" ORDER BY updated DESC',
            next_run_at=timezone.now(),
        )
        issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Escalate blocker handling",
            status="Blocked",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=timezone.now(),
            raw_json="{}",
            last_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )

        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        issue.refresh_from_db()

        assert JiraIssue.objects.filter(issue_key="OPS-778").exists()
        assert JiraIssueScopeMembership.objects.get(pk=membership.pk).is_active is False

    def test_issue_membership_rejects_policy_version_mismatch_with_scope(self):
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
        other_version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=2,
            strategy_hash="hash-v2",
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
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
            next_run_at=timezone.now(),
        )
        issue = JiraIssue.objects.create(
            issue_key="OPS-779",
            project_key="OPS",
            summary="Keep version consistency",
            status="Blocked",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=timezone.now(),
            raw_json="{}",
            last_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        membership = JiraIssueScopeMembership(
            issue=issue,
            scope=scope,
            policy_version=other_version,
            first_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            membership.save()

    def test_issue_exposes_policy_memberships_as_canonical_sync_memberships(self):
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
        scope = SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.PROJECT,
            name="OPS",
            is_required=False,
            is_enabled=True,
            schedule_minutes=30,
            config_json={"project_key": "OPS"},
            base_jql='project = "OPS" ORDER BY updated DESC',
            next_run_at=timezone.now(),
        )
        issue = JiraIssue.objects.create(
            issue_key="OPS-780",
            project_key="OPS",
            summary="Canonical relation names",
            status="Blocked",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=timezone.now(),
            raw_json="{}",
            last_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            is_active_in_current_policy=True,
            first_seen_policy_version_id=version.id,
            last_seen_policy_version_id=version.id,
        )
        profile = JiraSyncProfile.objects.create(
            name="Legacy Profile",
            profile_type=JiraSyncProfile.ProfileType.PROJECT,
            params_json={"project_key": "OPS"},
            jql='project = "OPS" ORDER BY updated DESC',
        )
        policy_membership = JiraIssueScopeMembership.objects.create(
            issue=issue,
            scope=scope,
            policy_version=version,
            first_seen_at=timezone.now(),
            last_checked_at=timezone.now(),
            last_synced_success_at=timezone.now(),
            last_seen_issue_updated_at=issue.updated_at,
            is_active=True,
        )
        legacy_membership = JiraIssueSyncMembership.objects.create(
            issue=issue,
            profile=profile,
            last_seen_at=timezone.now(),
        )

        assert issue.sync_memberships.get() == policy_membership
        assert issue.profile_sync_memberships.get() == legacy_membership
