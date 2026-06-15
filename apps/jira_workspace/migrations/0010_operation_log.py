from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jira_workspace", "0009_jiraconnection"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tool", models.CharField(choices=[("jira_query", "Jira Query"), ("jira_sync", "Jira Sync"), ("sync2pod", "sync2pod"), ("integrations", "Integrations")], db_index=True, max_length=32)),
                ("action", models.CharField(db_index=True, max_length=48)),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failed", "Failed")], db_index=True, default="running", max_length=16)),
                ("title", models.CharField(max_length=160)),
                ("triggered_by", models.CharField(blank=True, default="", max_length=128)),
                ("target_type", models.CharField(blank=True, db_index=True, default="", max_length=48)),
                ("target_id", models.CharField(blank=True, db_index=True, default="", max_length=80)),
                ("request_payload_json", models.JSONField(blank=True, default=dict)),
                ("result_summary", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("log_text", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-started_at", "-id"],
            },
        ),
    ]
