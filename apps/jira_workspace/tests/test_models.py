from django.test import TestCase

from jira_workspace.models import JiraIssue, JiraSavedQuery, JiraSyncProfile


class JiraWorkspaceModelTests(TestCase):
    def test_issue_string_representation_uses_issue_key(self):
        issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="In Progress",
            assignee="xchen17",
            reporter="xchen17",
            updated_at="2026-06-11T10:00:00+00:00",
            created_at="2026-06-10T10:00:00+00:00",
            raw_json="{}",
            last_seen_at="2026-06-11T10:00:00+00:00",
        )

        assert str(issue) == "TESS-321"

    def test_default_profile_flag_can_be_saved(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
            is_default=True,
        )

        assert profile.is_default is True

    def test_saved_query_defaults_to_not_starred_and_not_pinned(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
        )
        query = JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=profile,
            filters_json={"status": ["Blocked"]},
        )

        assert query.is_starred is False
        assert query.is_pinned is False
