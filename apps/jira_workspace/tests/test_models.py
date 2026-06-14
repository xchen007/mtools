from django.db import IntegrityError, transaction
from django.test import TestCase

from jira_workspace.models import (
    IntegrationContract,
    IntegrationScanRun,
    IntegrationTool,
    JiraIssue,
    JiraSavedQuery,
    JiraSyncProfile,
    JiraSyncRun,
    Sync2PodProfile,
    Sync2PodRun,
    Sync2PodWatchEvent,
)


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

    def test_saved_query_has_query_card_defaults(self):
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
        )
        query = JiraSavedQuery.objects.create(
            name="Assigned to me",
            profile=profile,
            filters_json={"source": "assigned"},
        )

        assert query.card_kind == JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY
        assert query.query_syntax == JiraSavedQuery.QuerySyntax.LOCAL_FILTER
        assert query.summary_metrics_json == [
            "total",
            "updated_today",
            "blocked",
            "in_progress",
            "high_priority",
        ]
        assert query.default_columns_json == [
            "issue_key",
            "project_key",
            "summary",
            "status",
            "assignee",
            "reporter",
            "priority",
            "updated_at",
        ]
        assert query.default_page_size == 25
        assert query.position == 0
        assert query.is_enabled is True

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

    def test_sync2pod_profile_string_representation_uses_name(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
            config_path="/tmp/sync2pod.yaml",
        )

        assert str(profile) == "Primary Pod"

    def test_sync2pod_run_related_name_exposes_profile_runs(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        run = Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=2,
            error_message="Binary missing",
        )

        assert profile.runs.get() == run

    def test_sync2pod_watch_event_related_names_link_profile_and_run(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        run = Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.QUEUED,
            trigger=Sync2PodRun.Trigger.WATCH,
            command_line="sync2pod push --watch",
        )
        event = Sync2PodWatchEvent.objects.create(
            profile=profile,
            run=run,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="Detected local change",
        )

        assert profile.watch_events.get() == event
        assert run.watch_events.get() == event

    def test_integration_contract_and_scan_runs_are_linked_to_tool(self):
        tool = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Pod file sync orchestration.",
        )
        contract = IntegrationContract.objects.create(
            tool=tool,
            input_contract="local path + pod target",
            output_contract="run summary",
            event_contract="watch queue",
            notes="Supports watch-triggered sync.",
        )
        run = IntegrationScanRun.objects.create(
            tool=tool,
            status=IntegrationScanRun.Status.SUCCESS,
            summary="catalog refresh finished",
        )

        assert tool.contract == contract
        assert tool.scan_runs.get() == run
