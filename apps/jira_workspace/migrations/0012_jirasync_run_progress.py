from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jira_workspace", "0011_global_sync_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="jirasyncrun",
            name="progress_current_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="jirasyncrun",
            name="progress_total_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="jirasyncrun",
            name="progress_message",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
