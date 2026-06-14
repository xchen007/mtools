from django import forms

from jira_workspace.models import (
    JiraSavedQuery,
    JiraSyncProfile,
    Sync2PodProfile,
    default_query_card_columns,
    default_query_card_summary_metrics,
)
from jira_workspace.services.query_card_types import (
    JIRA_ISSUE_QUERY_CARD_KIND,
    get_query_card_type_choices,
)
from jira_workspace.services.query_service import VALID_SORT_FIELDS, VALID_SORT_ORDERS


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
        self.fields["default_column_values"].initial = ", ".join(
            getattr(self.instance, "default_columns_json", None)
            or default_query_card_columns()
        )
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
            _split_csv(cleaned_data.get("default_column_values"))
            or default_query_card_columns()
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
