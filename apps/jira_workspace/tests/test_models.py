from django.db import IntegrityError, transaction
from django.test import TestCase

from jira_workspace.models import JiraIssue, JiraSavedQuery, JiraSyncProfile, JiraSyncRun


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

    def test_only_one_default_profile_can_exist(self):
        JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
            is_default=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                JiraSyncProfile.objects.create(
                    name="Project Issues",
                    profile_type=JiraSyncProfile.ProfileType.PROJECT,
                    params_json={"project_key": "TESS"},
                    jql='project = "TESS" ORDER BY updated DESC',
                    is_default=True,
                )

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

    def test_profile_related_names_expose_saved_queries_and_sync_runs(self):
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
        run = JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            started_at="2026-06-11T10:00:00+00:00",
        )

        assert profile.saved_queries.get() == query
        assert profile.sync_runs.get() == run
