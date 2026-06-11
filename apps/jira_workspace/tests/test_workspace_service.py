from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from jira_workspace.models import (
    IntegrationScanRun,
    IntegrationTool,
    JiraSyncProfile,
    JiraSyncRun,
    Sync2PodProfile,
    Sync2PodRun,
    Sync2PodWatchEvent,
)
from jira_workspace.services.workspace_service import WorkspaceService


class WorkspaceServiceTests(TestCase):
    def setUp(self):
        jira_profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
        )
        JiraSyncRun.objects.create(
            profile=jira_profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.SUCCESS,
            started_at=timezone.now() - timedelta(minutes=15),
            finished_at=timezone.now() - timedelta(minutes=14),
            fetched_count=5,
            inserted_count=2,
            updated_count=2,
            skipped_count=1,
        )

        sync2pod_profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        Sync2PodRun.objects.create(
            profile=sync2pod_profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=127,
            error_message="sync2pod command is not available on this host.",
        )
        Sync2PodWatchEvent.objects.create(
            profile=sync2pod_profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued after edit",
        )

        tool = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into pods.",
        )
        IntegrationScanRun.objects.create(
            tool=tool,
            status=IntegrationScanRun.Status.SUCCESS,
            summary="catalog refresh completed",
        )

    def test_build_home_context_combines_recent_activity_and_health(self):
        context = WorkspaceService().build_home_context()

        assert len(context["summary_cards"]) == 3
        assert [card["title"] for card in context["summary_cards"]] == [
            "Jira Sync Runs",
            "sync2pod Queue",
            "Integration Scans",
        ]
        assert [item["tool"] for item in context["recent_activity"]] == [
            "Integrations",
            "sync2pod",
            "Jira Sync",
        ]
        health_labels = [item["label"] for item in context["health_items"]]
        assert "Jira" in health_labels
        assert "sync2pod" in health_labels
        assert "Integrations" in health_labels

    def test_build_rail_sections_reports_cross_tool_activity(self):
        sections = WorkspaceService().build_rail_sections()

        assert [section["title"] for section in sections] == ["Activity", "Health"]
        assert sections[0]["items"][0]["label"] == "Jira sync runs"
        assert sections[0]["items"][1]["label"] == "sync2pod queue"
        assert sections[0]["items"][2]["label"] == "integration scans"
