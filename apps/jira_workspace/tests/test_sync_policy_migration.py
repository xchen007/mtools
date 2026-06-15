from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class JiraGlobalSyncPolicyMigrationTests(TransactionTestCase):
    migrate_from = [("jira_workspace", "0010_operation_log")]
    migrate_to = [("jira_workspace", "0011_global_sync_policy")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)

    def test_0011_backfills_issue_policy_fields_from_last_seen_at(self):
        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        JiraIssue = old_apps.get_model("jira_workspace", "JiraIssue")
        seen_at = timezone.now()

        JiraIssue.objects.create(
            issue_key="OPS-910",
            project_key="OPS",
            summary="Legacy issue row",
            status="Open",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=seen_at,
            raw_json="{}",
            last_seen_at=seen_at,
        )

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_to)
        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        JiraIssue = new_apps.get_model("jira_workspace", "JiraIssue")
        issue = JiraIssue.objects.get(issue_key="OPS-910")

        assert issue.last_checked_at == seen_at
        assert issue.last_synced_success_at == seen_at
        assert issue.is_active_in_current_policy is True
