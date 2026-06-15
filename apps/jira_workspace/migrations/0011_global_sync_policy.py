from django.db import migrations, models
import django.db.models.deletion


def backfill_jira_issue_policy_fields(apps, schema_editor):
    JiraIssue = apps.get_model("jira_workspace", "JiraIssue")

    for issue in JiraIssue.objects.all().iterator():
        issue.last_checked_at = issue.last_checked_at or issue.last_seen_at
        issue.last_synced_success_at = issue.last_synced_success_at or issue.last_seen_at
        issue.is_active_in_current_policy = True
        issue.save(
            update_fields=[
                "last_checked_at",
                "last_synced_success_at",
                "is_active_in_current_policy",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("jira_workspace", "0010_operation_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlobalSyncPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("strategy_json", models.JSONField(blank=True, default=dict)),
                ("strategy_hash", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(choices=[("ready", "Ready"), ("rebuilding", "Rebuilding"), ("partial", "Partial"), ("stale", "Stale")], default="stale", max_length=24)),
                ("last_strategy_changed_at", models.DateTimeField(blank=True, null=True)),
                ("last_version_built_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="GlobalSyncPolicyVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_no", models.PositiveIntegerField()),
                ("strategy_hash", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(choices=[("pending_full_sync", "Pending Full Sync"), ("building", "Building"), ("ready", "Ready"), ("partial_failed", "Partial Failed"), ("stale", "Stale")], default="pending_full_sync", max_length=32)),
                ("full_sync_required", models.BooleanField(default=True)),
                ("full_sync_started_at", models.DateTimeField(blank=True, null=True)),
                ("full_sync_completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="jira_workspace.globalsyncpolicy")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("policy", "version_no"), name="jira_workspace_policy_version_unique"),
                ],
            },
        ),
        migrations.AddField(
            model_name="globalsyncpolicy",
            name="current_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="jira_workspace.globalsyncpolicyversion"),
        ),
        migrations.CreateModel(
            name="SyncScope",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope_type", models.CharField(choices=[("self_required", "Self Required"), ("assignee_user", "Assignee User"), ("reporter_user", "Reporter User"), ("project", "Project"), ("label", "Label"), ("sprint", "Sprint"), ("custom_jql", "Custom JQL")], max_length=32)),
                ("name", models.CharField(max_length=120)),
                ("is_required", models.BooleanField(default=False)),
                ("is_enabled", models.BooleanField(default=True)),
                ("is_system_scope", models.BooleanField(default=False)),
                ("schedule_minutes", models.PositiveIntegerField(default=30)),
                ("config_json", models.JSONField(blank=True, default=dict)),
                ("base_jql", models.TextField()),
                ("effective_jql_last_run", models.TextField(blank=True, default="")),
                ("last_full_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_incremental_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_successful_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_issue_updated_cursor", models.CharField(blank=True, max_length=128, null=True)),
                ("last_run_status", models.CharField(choices=[("idle", "Idle"), ("queued_full", "Queued Full"), ("running_full", "Running Full"), ("queued_incremental", "Queued Incremental"), ("running_incremental", "Running Incremental"), ("success", "Success"), ("failed", "Failed"), ("blocked", "Blocked")], default="idle", max_length=32)),
                ("last_error_message", models.TextField(blank=True, default="")),
                ("next_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("policy_version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scopes", to="jira_workspace.globalsyncpolicyversion")),
            ],
        ),
        migrations.AddField(
            model_name="jiraissue",
            name="first_seen_policy_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="jira_workspace.globalsyncpolicyversion"),
        ),
        migrations.AddField(
            model_name="jiraissue",
            name="is_active_in_current_policy",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="jiraissue",
            name="last_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jiraissue",
            name="last_seen_policy_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="jira_workspace.globalsyncpolicyversion"),
        ),
        migrations.AddField(
            model_name="jiraissue",
            name="last_synced_success_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="JiraIssueScopeMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_seen_at", models.DateTimeField()),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_issue_updated_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scope_memberships", to="jira_workspace.jiraissue")),
                ("policy_version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="issue_memberships", to="jira_workspace.globalsyncpolicyversion")),
                ("scope", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="issue_memberships", to="jira_workspace.syncscope")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("issue", "scope"), name="jira_workspace_unique_issue_scope_membership"),
                ],
            },
        ),
        migrations.RunPython(backfill_jira_issue_policy_fields, migrations.RunPython.noop),
    ]
