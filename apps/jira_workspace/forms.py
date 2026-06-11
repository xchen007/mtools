from django import forms

from jira_workspace.models import JiraSavedQuery, JiraSyncProfile


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
    class Meta:
        model = JiraSyncProfile
        fields = ["name", "profile_type", "params_json", "jql", "is_default"]


class JiraSavedQueryForm(forms.ModelForm):
    class Meta:
        model = JiraSavedQuery
        fields = [
            "name",
            "profile",
            "description",
            "filters_json",
            "jql_text",
            "is_starred",
            "is_pinned",
            "sort_by",
            "sort_order",
        ]
