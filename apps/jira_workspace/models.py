from django.core.exceptions import ValidationError
from django.db import models


def default_query_card_summary_metrics():
    return ["total", "updated_today", "blocked", "in_progress", "high_priority"]


def default_query_card_columns():
    return [
        "issue_key",
        "project_key",
        "summary",
        "status",
        "assignee",
        "reporter",
        "priority",
        "updated_at",
        "sprint",
        "created_at",
    ]


class JiraIssue(models.Model):
    issue_key = models.CharField(max_length=32, primary_key=True)
    project_key = models.CharField(max_length=32, db_index=True)
    summary = models.TextField()
    status = models.CharField(max_length=64, db_index=True)
    assignee = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    reporter = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    priority = models.CharField(max_length=64, blank=True, null=True)
    sprint = models.TextField(blank=True, null=True)
    issue_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    labels_json = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(blank=True, null=True)
    raw_json = models.TextField()
    last_seen_at = models.DateTimeField()
    last_checked_at = models.DateTimeField(blank=True, null=True)
    last_synced_success_at = models.DateTimeField(blank=True, null=True)
    is_active_in_current_policy = models.BooleanField(default=True)
    first_seen_policy_version = models.ForeignKey(
        "GlobalSyncPolicyVersion",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    last_seen_policy_version = models.ForeignKey(
        "GlobalSyncPolicyVersion",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.issue_key


class JiraIssueMetric(models.Model):
    issue = models.OneToOneField(JiraIssue, on_delete=models.CASCADE, related_name="metrics")
    cycle_time_minutes = models.IntegerField(blank=True, null=True)
    worklog_minutes = models.IntegerField(blank=True, null=True)
    status_changed_at = models.DateTimeField(blank=True, null=True)


class JiraConnectionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class JiraConnection(models.Model):
    class AuthType(models.TextChoices):
        BEARER = "bearer", "Bearer Token"
        BASIC = "basic", "Basic Auth"

    class CheckStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        OK = "ok", "OK"
        FAILED = "failed", "Failed"

    base_url = models.URLField(max_length=255)
    api_token = models.TextField()
    auth_type = models.CharField(
        max_length=16,
        choices=AuthType.choices,
        default=AuthType.BEARER,
    )
    user_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    last_check_status = models.CharField(
        max_length=16,
        choices=CheckStatus.choices,
        default=CheckStatus.UNKNOWN,
    )
    last_check_message = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JiraConnectionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="jira_workspace_single_active_connection",
            )
        ]

    @property
    def masked_token(self):
        token = self.api_token or ""
        if not token:
            return ""
        visible = token[-4:] if len(token) > 4 else token
        return f"{'*' * max(len(token) - len(visible), 0)}{visible}"

    def __str__(self):
        return self.base_url


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
    progress_current_count = models.IntegerField(default=0)
    progress_total_count = models.IntegerField(default=0)
    progress_message = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, null=True)

    @property
    def progress_percent(self):
        if self.progress_total_count <= 0:
            return 0
        return min(100, int((self.progress_current_count / self.progress_total_count) * 100))


class GlobalSyncPolicy(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        REBUILDING = "rebuilding", "Rebuilding"
        PARTIAL = "partial", "Partial"
        STALE = "stale", "Stale"

    name = models.CharField(max_length=120, unique=True)
    strategy_json = models.JSONField(default=dict, blank=True)
    strategy_hash = models.CharField(max_length=64, db_index=True)
    current_version = models.ForeignKey(
        "GlobalSyncPolicyVersion",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.STALE)
    last_strategy_changed_at = models.DateTimeField(blank=True, null=True)
    last_version_built_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self._state.adding and self.current_version_id is not None:
            raise ValidationError(
                {"current_version": "Current version cannot be set when creating a policy."}
            )
        if (
            self.current_version_id is not None
            and self.id is not None
            and self.current_version.policy_id != self.id
        ):
            raise ValidationError(
                {"current_version": "Current version must belong to the same policy."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class GlobalSyncPolicyVersion(models.Model):
    class Status(models.TextChoices):
        PENDING_FULL_SYNC = "pending_full_sync", "Pending Full Sync"
        BUILDING = "building", "Building"
        READY = "ready", "Ready"
        PARTIAL_FAILED = "partial_failed", "Partial Failed"
        STALE = "stale", "Stale"

    policy = models.ForeignKey(GlobalSyncPolicy, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    strategy_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_FULL_SYNC,
    )
    full_sync_required = models.BooleanField(default=True)
    full_sync_started_at = models.DateTimeField(blank=True, null=True)
    full_sync_completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "version_no"],
                name="jira_workspace_policy_version_unique",
            ),
        ]


class SyncScope(models.Model):
    class ScopeType(models.TextChoices):
        SELF_REQUIRED = "self_required", "Self Required"
        ASSIGNEE_USER = "assignee_user", "Assignee User"
        REPORTER_USER = "reporter_user", "Reporter User"
        PROJECT = "project", "Project"
        LABEL = "label", "Label"
        SPRINT = "sprint", "Sprint"
        CUSTOM_JQL = "custom_jql", "Custom JQL"

    class RunStatus(models.TextChoices):
        IDLE = "idle", "Idle"
        QUEUED_FULL = "queued_full", "Queued Full"
        RUNNING_FULL = "running_full", "Running Full"
        QUEUED_INCREMENTAL = "queued_incremental", "Queued Incremental"
        RUNNING_INCREMENTAL = "running_incremental", "Running Incremental"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"

    policy_version = models.ForeignKey(
        GlobalSyncPolicyVersion,
        on_delete=models.CASCADE,
        related_name="scopes",
    )
    scope_type = models.CharField(max_length=32, choices=ScopeType.choices)
    name = models.CharField(max_length=120)
    is_required = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    is_system_scope = models.BooleanField(default=False)
    schedule_minutes = models.PositiveIntegerField(default=30)
    config_json = models.JSONField(default=dict, blank=True)
    base_jql = models.TextField()
    effective_jql_last_run = models.TextField(blank=True, default="")
    last_full_sync_at = models.DateTimeField(blank=True, null=True)
    last_incremental_sync_at = models.DateTimeField(blank=True, null=True)
    last_successful_check_at = models.DateTimeField(blank=True, null=True)
    last_issue_updated_cursor = models.CharField(max_length=128, blank=True, null=True)
    last_run_status = models.CharField(max_length=32, choices=RunStatus.choices, default=RunStatus.IDLE)
    last_error_message = models.TextField(blank=True, default="")
    next_run_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class JiraIssueSyncMembership(models.Model):
    issue = models.ForeignKey(
        JiraIssue, on_delete=models.CASCADE, related_name="profile_sync_memberships"
    )
    profile = models.ForeignKey(
        JiraSyncProfile, on_delete=models.CASCADE, related_name="issue_memberships"
    )
    last_seen_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "profile"],
                name="jira_workspace_unique_issue_profile_membership",
            )
        ]


class JiraIssueScopeMembership(models.Model):
    issue = models.ForeignKey(
        JiraIssue,
        on_delete=models.CASCADE,
        related_name="sync_memberships",
    )
    scope = models.ForeignKey(
        SyncScope,
        on_delete=models.CASCADE,
        related_name="issue_memberships",
    )
    policy_version = models.ForeignKey(
        GlobalSyncPolicyVersion,
        on_delete=models.CASCADE,
        related_name="issue_memberships",
    )
    first_seen_at = models.DateTimeField()
    last_checked_at = models.DateTimeField(blank=True, null=True)
    last_synced_success_at = models.DateTimeField(blank=True, null=True)
    last_seen_issue_updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "scope"],
                name="jira_workspace_unique_issue_scope_membership",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.scope_id is not None
            and self.policy_version_id is not None
            and self.scope.policy_version_id != self.policy_version_id
        ):
            raise ValidationError(
                {"policy_version": "Policy version must match the scope policy version."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class JiraScopeSyncReport(models.Model):
    class RunType(models.TextChoices):
        FULL = "full", "Full"
        INCREMENTAL = "incremental", "Incremental"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    policy_version = models.ForeignKey(
        GlobalSyncPolicyVersion,
        on_delete=models.CASCADE,
        related_name="scope_sync_reports",
    )
    scope = models.ForeignKey(
        SyncScope,
        on_delete=models.CASCADE,
        related_name="sync_reports",
    )
    run_type = models.CharField(max_length=32, choices=RunType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    effective_jql = models.TextField(blank=True, default="")
    fetched_count = models.IntegerField(default=0)
    inserted_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    unchanged_checked_count = models.IntegerField(default=0)
    deactivated_membership_count = models.IntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class JiraSavedQuery(models.Model):
    class CardKind(models.TextChoices):
        JIRA_ISSUE_QUERY = "jira_issue_query", "Jira Issue Query"

    class QuerySyntax(models.TextChoices):
        LOCAL_FILTER = "local_filter", "Local Filter"
        JQL_TEXT = "jql_text", "JQL Text"
        SAVED_FILTER_REFERENCE = "saved_filter_reference", "Saved Filter Reference"

    name = models.CharField(max_length=120, unique=True)
    profile = models.ForeignKey(JiraSyncProfile, on_delete=models.CASCADE, related_name="saved_queries")
    description = models.TextField(blank=True)
    filters_json = models.JSONField(default=dict, blank=True)
    jql_text = models.TextField(blank=True)
    card_kind = models.CharField(
        max_length=48,
        default=CardKind.JIRA_ISSUE_QUERY,
    )
    query_syntax = models.CharField(
        max_length=48,
        choices=QuerySyntax.choices,
        default=QuerySyntax.LOCAL_FILTER,
    )
    summary_metrics_json = models.JSONField(
        default=default_query_card_summary_metrics,
        blank=True,
    )
    default_columns_json = models.JSONField(
        default=default_query_card_columns,
        blank=True,
    )
    default_page_size = models.PositiveIntegerField(default=25)
    position = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    is_starred = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    sort_by = models.CharField(max_length=32, default="updated_at")
    sort_order = models.CharField(max_length=8, default="desc")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OperationLog(models.Model):
    class Tool(models.TextChoices):
        JIRA_QUERY = "jira_query", "Jira Query"
        JIRA_SYNC = "jira_sync", "Jira Sync"
        SYNC2POD = "sync2pod", "sync2pod"
        INTEGRATIONS = "integrations", "Integrations"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    tool = models.CharField(max_length=32, choices=Tool.choices, db_index=True)
    action = models.CharField(max_length=48, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    title = models.CharField(max_length=160)
    triggered_by = models.CharField(max_length=128, blank=True, default="")
    target_type = models.CharField(max_length=48, blank=True, default="", db_index=True)
    target_id = models.CharField(max_length=80, blank=True, default="", db_index=True)
    request_payload_json = models.JSONField(default=dict, blank=True)
    result_summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    log_text = models.TextField(blank=True)
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self):
        return self.title


class Sync2PodProfile(models.Model):
    name = models.CharField(max_length=120, unique=True)
    pod_name = models.CharField(max_length=120)
    namespace = models.CharField(max_length=120, default="default")
    watch_path = models.CharField(max_length=255)
    config_path = models.CharField(max_length=255, blank=True)
    command = models.CharField(max_length=255, default="sync2pod")
    extra_args = models.CharField(max_length=255, blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Sync2PodRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manual"
        WATCH = "watch", "Watch"

    profile = models.ForeignKey(
        Sync2PodProfile,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    trigger = models.CharField(max_length=32, choices=Trigger.choices, default=Trigger.MANUAL)
    command_line = models.TextField(blank=True)
    exit_code = models.IntegerField(blank=True, null=True)
    stdout_log = models.TextField(blank=True)
    stderr_log = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]


class Sync2PodWatchEvent(models.Model):
    class EventType(models.TextChoices):
        FILE_CHANGED = "file_changed", "File Changed"
        MANUAL_TRIGGER = "manual_trigger", "Manual Trigger"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    profile = models.ForeignKey(
        Sync2PodProfile,
        on_delete=models.CASCADE,
        related_name="watch_events",
    )
    run = models.ForeignKey(
        Sync2PodRun,
        on_delete=models.SET_NULL,
        related_name="watch_events",
        blank=True,
        null=True,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    file_path = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]


class WorkspaceStar(models.Model):
    class Kind(models.TextChoices):
        ROUTE = "route", "Route"
        SAVED_QUERY = "saved_query", "Saved Query"
        JIRA_SYNC_PROFILE = "jira_sync_profile", "Jira Sync Profile"
        SYNC2POD_PROFILE = "sync2pod_profile", "sync2pod Profile"

    kind = models.CharField(max_length=48, choices=Kind.choices)
    label = models.CharField(max_length=160)
    route = models.CharField(max_length=255)
    group_key = models.CharField(max_length=80, db_index=True)
    object_id = models.CharField(max_length=80, blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "route", "object_id"],
                name="jira_workspace_unique_workspace_star",
            )
        ]

    def __str__(self):
        return self.label


class IntegrationTool(models.Model):
    class Readiness(models.TextChoices):
        READY = "ready", "Ready"
        BETA = "beta", "Beta"
        PLANNED = "planned", "Planned"

    key = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    group = models.CharField(max_length=80)
    readiness = models.CharField(max_length=32, choices=Readiness.choices)
    description = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group", "name"]

    def __str__(self):
        return self.name


class IntegrationContract(models.Model):
    tool = models.OneToOneField(
        IntegrationTool,
        on_delete=models.CASCADE,
        related_name="contract",
    )
    input_contract = models.CharField(max_length=255, blank=True)
    output_contract = models.CharField(max_length=255, blank=True)
    event_contract = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)


class IntegrationScanRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    tool = models.ForeignKey(
        IntegrationTool,
        on_delete=models.CASCADE,
        related_name="scan_runs",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    summary = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]
