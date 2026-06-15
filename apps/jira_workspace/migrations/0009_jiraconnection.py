from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jira_workspace", "0008_jiraissue_query_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="JiraConnection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("base_url", models.URLField(max_length=255)),
                ("api_token", models.TextField()),
                (
                    "auth_type",
                    models.CharField(
                        choices=[
                            ("bearer", "Bearer Token"),
                            ("basic", "Basic Auth"),
                        ],
                        default="bearer",
                        max_length=16,
                    ),
                ),
                ("user_email", models.EmailField(blank=True, max_length=254)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "last_check_status",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("ok", "OK"),
                            ("failed", "Failed"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("last_check_message", models.TextField(blank=True)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="jiraconnection",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("is_active",),
                name="jira_workspace_single_active_connection",
            ),
        ),
    ]
