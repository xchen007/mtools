from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("jira_workspace", "0012_jirasync_run_progress"),
    ]

    operations = [
        migrations.CreateModel(
            name="JiraScopeSyncReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_type", models.CharField(choices=[("full", "Full"), ("incremental", "Incremental")], max_length=32)),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failed", "Failed")], default="running", max_length=32)),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("effective_jql", models.TextField(blank=True, default="")),
                ("fetched_count", models.IntegerField(default=0)),
                ("inserted_count", models.IntegerField(default=0)),
                ("updated_count", models.IntegerField(default=0)),
                ("skipped_count", models.IntegerField(default=0)),
                ("unchanged_checked_count", models.IntegerField(default=0)),
                ("deactivated_membership_count", models.IntegerField(default=0)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("policy_version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scope_sync_reports", to="jira_workspace.globalsyncpolicyversion")),
                ("scope", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sync_reports", to="jira_workspace.syncscope")),
            ],
        ),
    ]
