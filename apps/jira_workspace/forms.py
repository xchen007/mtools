from django import forms

from jira_workspace.models import (
    GlobalSyncPolicy,
    JiraConnection,
    JiraSavedQuery,
    JiraSyncProfile,
    SyncScope,
    Sync2PodProfile,
    default_query_card_columns,
    default_query_card_summary_metrics,
)
from jira_workspace.services.query_card_types import (
    JIRA_ISSUE_QUERY_CARD_KIND,
    get_query_card_type_choices,
)
from jira_workspace.services.query_service import VALID_SORT_FIELDS, VALID_SORT_ORDERS


QUERY_CARD_COLUMN_CHOICES = [
    ("issue_key", "Key"),
    ("project_key", "Project"),
    ("summary", "Summary"),
    ("status", "Status"),
    ("assignee", "Assignee"),
    ("reporter", "Reporter"),
    ("priority", "Priority"),
    ("updated_at", "Updated"),
    ("sprint", "Sprint"),
    ("created_at", "Created"),
]


def normalize_query_card_columns(column_keys):
    valid_keys = {key for key, _label in QUERY_CARD_COLUMN_CHOICES}
    normalized = []
    for key in column_keys or []:
        if key in valid_keys and key not in normalized:
            normalized.append(key)
    return normalized or default_query_card_columns()


class JiraIssueFilterForm(forms.Form):
    source = forms.ChoiceField(required=False)
    project = forms.ChoiceField(required=False)
    status = forms.ChoiceField(required=False)
    sort_by = forms.ChoiceField(required=False)
    sort_order = forms.ChoiceField(required=False)
    query = forms.CharField(required=False, max_length=120)

    def __init__(self, *args, filter_options=None, **kwargs):
        super().__init__(*args, **kwargs)
        filter_options = filter_options or {}
        self.fields["source"].choices = [("", "All Sources")] + [
            (value, value.title()) for value in filter_options.get("source_options", ())
        ]
        self.fields["project"].choices = [("", "All Projects")] + [
            (value, value) for value in filter_options.get("project_options", ())
        ]
        self.fields["status"].choices = [("", "Any Status")] + [
            (value, value) for value in filter_options.get("status_options", ())
        ]
        self.fields["sort_by"].choices = [
            (value, value.replace("_", " ").title())
            for value in filter_options.get("sort_field_options", ())
        ]
        self.fields["sort_order"].choices = [
            (value, value.upper()) for value in filter_options.get("sort_order_options", ())
        ]


class GlobalSyncPolicyForm(forms.ModelForm):
    class Meta:
        model = GlobalSyncPolicy
        fields = ["name"]


class SyncScopeForm(forms.Form):
    scope_type = forms.ChoiceField(
        choices=[
            choice
            for choice in SyncScope.ScopeType.choices
            if choice[0] != SyncScope.ScopeType.SELF_REQUIRED
        ]
    )
    name = forms.CharField(max_length=120)
    schedule_minutes = forms.IntegerField(min_value=5, initial=30)
    is_required = forms.BooleanField(required=False)
    username = forms.CharField(required=False, max_length=128)
    project_key = forms.CharField(required=False, max_length=32)
    label = forms.CharField(required=False, max_length=64)
    sprint = forms.CharField(required=False, max_length=120)
    custom_jql = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        cleaned_data = super().clean()
        scope_type = cleaned_data.get("scope_type")
        username = (cleaned_data.get("username") or "").strip()
        project_key = (cleaned_data.get("project_key") or "").strip().upper()
        label = (cleaned_data.get("label") or "").strip()
        sprint = (cleaned_data.get("sprint") or "").strip()
        custom_jql = (cleaned_data.get("custom_jql") or "").strip()

        if scope_type in {
            SyncScope.ScopeType.ASSIGNEE_USER,
            SyncScope.ScopeType.REPORTER_USER,
        } and not username:
            self.add_error("username", "Username is required for user scopes.")
        if scope_type == SyncScope.ScopeType.PROJECT and not project_key:
            self.add_error("project_key", "Project key is required for project scopes.")
        if scope_type == SyncScope.ScopeType.LABEL and not label:
            self.add_error("label", "Label is required for label scopes.")
        if scope_type == SyncScope.ScopeType.SPRINT and not sprint:
            self.add_error("sprint", "Sprint is required for sprint scopes.")
        if scope_type == SyncScope.ScopeType.CUSTOM_JQL and not custom_jql:
            self.add_error("custom_jql", "Custom JQL is required for custom JQL scopes.")

        cleaned_data["username"] = username
        cleaned_data["project_key"] = project_key
        cleaned_data["label"] = label
        cleaned_data["sprint"] = sprint
        cleaned_data["custom_jql"] = custom_jql
        return cleaned_data

    def to_strategy_scope(self):
        scope_type = self.cleaned_data["scope_type"]
        scope_config = {
            "scope_type": scope_type,
            "name": self.cleaned_data["name"].strip(),
            "schedule_minutes": self.cleaned_data["schedule_minutes"],
            "is_required": bool(self.cleaned_data.get("is_required")),
            "is_enabled": True,
        }
        if scope_type in {
            SyncScope.ScopeType.ASSIGNEE_USER,
            SyncScope.ScopeType.REPORTER_USER,
        }:
            scope_config["username"] = self.cleaned_data["username"]
        elif scope_type == SyncScope.ScopeType.PROJECT:
            scope_config["project_key"] = self.cleaned_data["project_key"]
        elif scope_type == SyncScope.ScopeType.LABEL:
            scope_config["label"] = self.cleaned_data["label"]
        elif scope_type == SyncScope.ScopeType.SPRINT:
            scope_config["sprint"] = self.cleaned_data["sprint"]
        elif scope_type == SyncScope.ScopeType.CUSTOM_JQL:
            scope_config["jql"] = self.cleaned_data["custom_jql"]
        return scope_config


class JiraSyncProfileForm(forms.ModelForm):
    username = forms.CharField(required=False, max_length=128)
    project_key = forms.CharField(required=False, max_length=32)
    custom_jql = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    class Meta:
        model = JiraSyncProfile
        fields = ["name", "profile_type", "params_json", "jql", "is_default"]
        widgets = {
            "params_json": forms.HiddenInput(),
            "jql": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["params_json"].required = False
        self.fields["jql"].required = False
        params_json = dict(getattr(self.instance, "params_json", {}) or {})
        profile_type = getattr(self.instance, "profile_type", "")
        self.fields["username"].initial = (
            params_json.get("username", "")
            if profile_type == JiraSyncProfile.ProfileType.MY_ISSUES
            else ""
        )
        self.fields["project_key"].initial = (
            params_json.get("project_key", "")
            if profile_type == JiraSyncProfile.ProfileType.PROJECT
            else ""
        )
        self.fields["custom_jql"].initial = (
            params_json.get("jql") or getattr(self.instance, "jql", "")
            if profile_type == JiraSyncProfile.ProfileType.CUSTOM_JQL
            else ""
        )

    def clean(self):
        cleaned_data = super().clean()
        profile_type = cleaned_data.get("profile_type")
        username = (cleaned_data.get("username") or "").strip()
        project_key = (cleaned_data.get("project_key") or "").strip().upper()
        custom_jql = (cleaned_data.get("custom_jql") or "").strip()

        if profile_type == JiraSyncProfile.ProfileType.MY_ISSUES:
            cleaned_data["params_json"] = (
                {"username": username} if username else {}
            )
            cleaned_data["jql"] = "assignee = currentUser() ORDER BY updated DESC"
        elif profile_type == JiraSyncProfile.ProfileType.PROJECT:
            if not project_key:
                self.add_error("project_key", "Project key is required for project profiles.")
            cleaned_data["params_json"] = {"project_key": project_key} if project_key else {}
            cleaned_data["jql"] = (
                f'project = "{project_key}" ORDER BY updated DESC' if project_key else ""
            )
        elif profile_type == JiraSyncProfile.ProfileType.CUSTOM_JQL:
            if not custom_jql:
                self.add_error("custom_jql", "Custom JQL is required for custom profiles.")
            cleaned_data["params_json"] = {"jql": custom_jql} if custom_jql else {}
            cleaned_data["jql"] = custom_jql

        return cleaned_data

class JiraConnectionForm(forms.ModelForm):
    api_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = JiraConnection
        fields = ["base_url", "auth_type", "user_email", "api_token"]

    def clean_base_url(self):
        return (self.cleaned_data.get("base_url") or "").strip().rstrip("/")

    def clean(self):
        cleaned_data = super().clean()
        auth_type = cleaned_data.get("auth_type")
        user_email = (cleaned_data.get("user_email") or "").strip()
        api_token = (cleaned_data.get("api_token") or "").strip()

        if auth_type == JiraConnection.AuthType.BASIC and not user_email:
            self.add_error("user_email", "User email is required for basic auth.")
        if not api_token and not getattr(self.instance, "api_token", ""):
            self.add_error("api_token", "API token is required.")

        cleaned_data["user_email"] = user_email
        if api_token:
            cleaned_data["api_token"] = api_token
        return cleaned_data

    def save(self, commit=True):
        connection = super().save(commit=False)
        submitted_token = (self.cleaned_data.get("api_token") or "").strip()
        if submitted_token:
            connection.api_token = submitted_token
        elif self.instance and self.instance.pk:
            connection.api_token = self.instance.api_token
        connection.is_active = True
        if commit:
            JiraConnection.objects.active().exclude(pk=connection.pk).update(is_active=False)
            connection.save()
        return connection


class JiraSavedQueryForm(forms.ModelForm):
    source = forms.ChoiceField(
        required=False,
        choices=[
            ("all", "Assigned or Reported"),
            ("assigned", "Assigned to Me"),
            ("created", "Reported by Me"),
        ],
    )
    reporter_value = forms.CharField(required=False, max_length=128)
    assignee_value = forms.CharField(required=False, max_length=128)
    project_values = forms.CharField(required=False, max_length=200)
    status_values = forms.CharField(required=False, max_length=200)
    label_values = forms.CharField(required=False, max_length=255)
    sprint_value = forms.CharField(required=False, max_length=200)
    issue_type_values = forms.CharField(required=False, max_length=200)
    priority_values = forms.CharField(required=False, max_length=200)
    search_value = forms.CharField(required=False, max_length=120)
    summary_metric_values = forms.CharField(required=False, max_length=255)
    default_column_values = forms.CharField(required=False, max_length=255)
    sort_by = forms.ChoiceField(required=False)
    sort_order = forms.ChoiceField(required=False)

    class Meta:
        model = JiraSavedQuery
        fields = [
            "name",
            "profile",
            "description",
            "filters_json",
            "jql_text",
            "card_kind",
            "query_syntax",
            "summary_metrics_json",
            "default_columns_json",
            "default_page_size",
            "is_starred",
            "is_pinned",
            "sort_by",
            "sort_order",
        ]

    def __init__(self, *args, username=None, filter_options=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username or ""
        self.filter_options = filter_options or {}
        self.fields["filters_json"].required = False
        self.fields["card_kind"].required = False
        self.fields["card_kind"].choices = get_query_card_type_choices()
        self.fields["query_syntax"].required = False
        self.fields["summary_metrics_json"].required = False
        self.fields["default_columns_json"].required = False
        self.fields["default_page_size"].required = False
        filters_json = dict(getattr(self.instance, "filters_json", {}) or {})
        is_new = not getattr(self.instance, "pk", None)
        if is_new and not self.is_bound:
            default_profile = JiraSyncProfile.objects.order_by("-is_default", "name", "id").first()
            if default_profile:
                self.fields["profile"].initial = default_profile.id
        self.fields["source"].initial = filters_json.get("source", "all")
        self.fields["reporter_value"].initial = filters_json.get(
            "reporter",
            self.username if is_new else "",
        )
        self.fields["assignee_value"].initial = filters_json.get(
            "assignee",
            self.username if is_new else "",
        )
        self.fields["project_values"].initial = ", ".join(filters_json.get("project", []))
        self.fields["status_values"].initial = ", ".join(filters_json.get("status", []))
        self.fields["label_values"].initial = ", ".join(filters_json.get("labels", []))
        self.fields["sprint_value"].initial = filters_json.get("sprint", "")
        self.fields["issue_type_values"].initial = ", ".join(filters_json.get("issue_type", []))
        self.fields["priority_values"].initial = ", ".join(filters_json.get("priority", []))
        self.fields["search_value"].initial = filters_json.get("search", "")
        self.fields["summary_metric_values"].initial = ", ".join(
            getattr(self.instance, "summary_metrics_json", None)
            or default_query_card_summary_metrics()
        )
        selected_columns = normalize_query_card_columns(
            getattr(self.instance, "default_columns_json", None)
            or default_query_card_columns()
        )
        self.fields["default_column_values"].initial = ", ".join(selected_columns)
        selected_column_set = set(selected_columns)
        labels_by_key = dict(QUERY_CARD_COLUMN_CHOICES)
        self.column_choices = [
            {
                "value": key,
                "label": labels_by_key[key],
                "checked": key in selected_column_set,
            }
            for key in selected_columns
        ] + [
            {
                "value": key,
                "label": label,
                "checked": False,
            }
            for key, label in QUERY_CARD_COLUMN_CHOICES
            if key not in selected_column_set
        ]
        self.fields["sort_by"].choices = [
            (value, value.replace("_", " ").title()) for value in VALID_SORT_FIELDS
        ]
        self.fields["sort_order"].choices = [(value, value.upper()) for value in VALID_SORT_ORDERS]

    def clean(self):
        cleaned_data = super().clean()

        def _split_csv(value):
            return [item.strip() for item in (value or "").split(",") if item.strip()]

        filters_json = {}
        cleaned_data["card_kind"] = (
            cleaned_data.get("card_kind") or JIRA_ISSUE_QUERY_CARD_KIND
        )
        cleaned_data["query_syntax"] = (
            cleaned_data.get("query_syntax") or JiraSavedQuery.QuerySyntax.LOCAL_FILTER
        )
        cleaned_data["default_page_size"] = cleaned_data.get("default_page_size") or 25
        source = cleaned_data.get("source") or "all"
        if source != "all":
            filters_json["source"] = source
        project_values = _split_csv(cleaned_data.get("project_values"))
        status_values = _split_csv(cleaned_data.get("status_values"))
        label_values = _split_csv(cleaned_data.get("label_values"))
        issue_type_values = _split_csv(cleaned_data.get("issue_type_values"))
        priority_values = _split_csv(cleaned_data.get("priority_values"))
        reporter_value = (cleaned_data.get("reporter_value") or "").strip()
        assignee_value = (cleaned_data.get("assignee_value") or "").strip()
        sprint_value = (cleaned_data.get("sprint_value") or "").strip()
        search_value = (cleaned_data.get("search_value") or "").strip()
        if reporter_value:
            filters_json["reporter"] = reporter_value
        if assignee_value:
            filters_json["assignee"] = assignee_value
        if project_values:
            filters_json["project"] = project_values
        if status_values:
            filters_json["status"] = status_values
        if label_values:
            filters_json["labels"] = label_values
        if sprint_value:
            filters_json["sprint"] = sprint_value
        if issue_type_values:
            filters_json["issue_type"] = issue_type_values
        if priority_values:
            filters_json["priority"] = priority_values
        if search_value:
            filters_json["search"] = search_value
        cleaned_data["filters_json"] = filters_json
        cleaned_data["summary_metrics_json"] = (
            _split_csv(cleaned_data.get("summary_metric_values"))
            or default_query_card_summary_metrics()
        )
        cleaned_data["default_columns_json"] = (
            normalize_query_card_columns(
                _split_csv(cleaned_data.get("default_column_values"))
            )
        )
        return cleaned_data


class Sync2PodProfileForm(forms.ModelForm):
    class Meta:
        model = Sync2PodProfile
        fields = [
            "name",
            "pod_name",
            "namespace",
            "watch_path",
            "config_path",
            "command",
            "extra_args",
            "is_enabled",
        ]
