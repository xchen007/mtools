from django.db import models


class JiraIssue(models.Model):
    issue_key = models.CharField(max_length=32, primary_key=True)
    project_key = models.CharField(max_length=32, db_index=True)
    summary = models.TextField()
    status = models.CharField(max_length=64, db_index=True)
    assignee = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    reporter = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    priority = models.CharField(max_length=64, blank=True, null=True)
    sprint = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(blank=True, null=True)
    raw_json = models.TextField()
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.issue_key


class JiraIssueMetric(models.Model):
    issue = models.OneToOneField(JiraIssue, on_delete=models.CASCADE, related_name="metrics")
    cycle_time_minutes = models.IntegerField(blank=True, null=True)
    worklog_minutes = models.IntegerField(blank=True, null=True)
    status_changed_at = models.DateTimeField(blank=True, null=True)


class JiraSyncProfile(models.Model):
    class ProfileType(models.TextChoices):
        MY_ISSUES = "my_issues", "My Issues"
        PROJECT = "project", "Project"
        CUSTOM_JQL = "custom_jql", "Custom JQL"

    name = models.CharField(max_length=120, unique=True)
    profile_type = models.CharField(max_length=32, choices=ProfileType.choices)
    params_json = models.JSONField(default=dict, blank=True)
    jql = models.TextField()
    is_default = models.BooleanField(default=False)
    last_cursor = models.CharField(max_length=128, blank=True, null=True)
    last_full_sync_at = models.DateTimeField(blank=True, null=True)
    last_incremental_sync_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="jira_workspace_single_default_profile",
            )
        ]

    def __str__(self):
        return self.name


class JiraSyncRun(models.Model):
    class RunType(models.TextChoices):
        FULL = "full", "Full"
        INCREMENTAL = "incremental", "Incremental"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    profile = models.ForeignKey(JiraSyncProfile, on_delete=models.CASCADE, related_name="sync_runs")
    run_type = models.CharField(max_length=32, choices=RunType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    fetched_count = models.IntegerField(default=0)
    inserted_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)


class JiraSavedQuery(models.Model):
    name = models.CharField(max_length=120, unique=True)
    profile = models.ForeignKey(JiraSyncProfile, on_delete=models.CASCADE, related_name="saved_queries")
    description = models.TextField(blank=True)
    filters_json = models.JSONField(default=dict, blank=True)
    jql_text = models.TextField(blank=True)
    is_starred = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    sort_by = models.CharField(max_length=32, default="updated_at")
    sort_order = models.CharField(max_length=8, default="desc")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
