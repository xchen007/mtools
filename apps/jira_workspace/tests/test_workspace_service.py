from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from jira_workspace.models import (
    IntegrationScanRun,
    IntegrationTool,
    JiraConnection,
    JiraSyncProfile,
    JiraSyncRun,
    JiraSavedQuery,
    Sync2PodProfile,
    Sync2PodRun,
    Sync2PodWatchEvent,
    WorkspaceStar,
)
from jira_workspace.services.star_service import StarService
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

        assert len(context["summary_cards"]) == 4
        assert [card["title"] for card in context["summary_cards"]] == [
            "Jira Sync Runs",
            "sync2pod Queue",
            "Integration Scans",
            "Operation Logs",
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

    @override_settings(
        JIRA_API_BASE_URL="https://jira.example.com",
        JIRA_API_TOKEN="token",
    )
    def test_build_rail_sections_reports_cross_tool_activity(self):
        sections = WorkspaceService().build_rail_sections()

        assert [section["title"] for section in sections] == ["Service Status"]
        assert sections[0]["items"][0] == {
            "label": "Jira",
            "value": "1 run",
            "status": "ok",
            "icon": "J",
        }
        assert sections[0]["items"][1] == {
            "label": "sync2pod",
            "value": "1 queued",
            "status": "blocked",
            "icon": "S",
        }
        assert sections[0]["items"][2] == {
            "label": "Integrations",
            "value": "1 scan",
            "status": "ok",
            "icon": "I",
        }

    @override_settings(JIRA_API_BASE_URL="", JIRA_API_TOKEN="")
    def test_build_rail_sections_marks_jira_blocked_when_api_settings_are_missing(self):
        JiraSyncRun.objects.all().delete()

        sections = WorkspaceService().build_rail_sections()

        assert sections[0]["items"][0] == {
            "label": "Jira",
            "value": "0 runs",
            "status": "blocked",
            "icon": "J",
        }

    @override_settings(JIRA_API_BASE_URL="", JIRA_API_TOKEN="")
    def test_build_rail_sections_uses_database_connection_health(self):
        JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token",
            auth_type=JiraConnection.AuthType.BEARER,
            last_check_status=JiraConnection.CheckStatus.OK,
            last_check_message="Connected as xchen17.",
        )
        JiraSyncRun.objects.all().delete()

        sections = WorkspaceService().build_rail_sections()

        assert sections[0]["items"][0]["status"] == "ok"

    @override_settings(JIRA_API_BASE_URL="", JIRA_API_TOKEN="")
    def test_build_home_context_surfaces_database_connection_failure_message(self):
        JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token",
            auth_type=JiraConnection.AuthType.BEARER,
            last_check_status=JiraConnection.CheckStatus.FAILED,
            last_check_message="401 Client Error: Unauthorized",
        )

        context = WorkspaceService().build_home_context()

        jira_card = next(
            card for card in context["summary_cards"] if card["title"] == "Jira Sync Runs"
        )
        assert jira_card["detail"] == "401 Client Error: Unauthorized"
        jira_health = next(
            item for item in context["health_items"] if item["label"] == "Jira"
        )
        assert jira_health["value"] == "blocked"

    @patch(
        "jira_workspace.services.sync2pod_service.Sync2PodService.check_capabilities",
        return_value={
            "is_available": False,
            "message": "sync2pod command is not available on this host.",
            "command_path": "sync2pod",
        },
    )
    def test_build_home_context_marks_sync2pod_blocked_when_command_is_unavailable(
        self,
        _check_capabilities,
    ):
        Sync2PodRun.objects.all().delete()

        context = WorkspaceService().build_home_context()

        sync2pod_health = next(
            item for item in context["health_items"] if item["label"] == "sync2pod"
        )
        assert sync2pod_health["value"] == "blocked"

    @patch(
        "jira_workspace.services.sync2pod_service.Sync2PodService.check_capabilities",
        return_value={
            "is_available": False,
            "message": "sync2pod command is not available on this host.",
            "command_path": "sync2pod",
        },
    )
    def test_build_home_context_surfaces_sync2pod_capability_message_in_summary_card(
        self,
        _check_capabilities,
    ):
        Sync2PodRun.objects.all().delete()

        context = WorkspaceService().build_home_context()

        sync2pod_card = next(
            card for card in context["summary_cards"] if card["title"] == "sync2pod Queue"
        )
        assert sync2pod_card["detail"] == "sync2pod command is not available on this host."

    def test_build_shell_navigation_groups_tools_current_tool_and_starred_items(self):
        JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=JiraSyncProfile.objects.get(name="My Issues"),
            jql_text='status = "Blocked"',
        )
        WorkspaceStar.objects.create(
            kind=WorkspaceStar.Kind.ROUTE,
            label="Jira Issues",
            route="/jira/issues/",
            group_key="jira",
        )
        WorkspaceStar.objects.create(
            kind=WorkspaceStar.Kind.SAVED_QUERY,
            label="My Open Blockers",
            route="/jira/query/?saved_query=1",
            group_key="jira",
            object_id="1",
        )

        shell = WorkspaceService().build_shell_navigation(current_route_name="issues")

        assert [item["label"] for item in shell["tools"]] == [
            "Workspace",
            "Jira",
            "sync2pod",
            "Integrations",
            "Logs",
        ]
        assert shell["current_tool"]["key"] == "jira"
        assert [item["label"] for item in shell["current_sections"]] == [
            "Dashboard",
            "Query",
            "Sync",
            "Profiles",
        ]
        assert next(
            item for item in shell["current_sections"] if item["label"] == "Dashboard"
        )["active"] is False
        assert [item["label"] for item in shell["starred_items"]] == [
            "Jira Issues",
            "My Open Blockers",
        ]

    def test_build_shell_navigation_expands_jira_sections_for_query(self):
        shell = WorkspaceService().build_shell_navigation(current_route_name="query")

        assert [item["label"] for item in shell["current_sections"]] == [
            "Dashboard",
            "Query",
            "Sync",
            "Profiles",
        ]
        assert next(
            item for item in shell["current_sections"] if item["label"] == "Query"
        )["active"] is True
        assert next(
            item for item in shell["current_sections"] if item["label"] == "Sync"
        )["href"] == reverse("jira_workspace:sync")

    def test_build_shell_navigation_marks_sync_section_active(self):
        shell = WorkspaceService().build_shell_navigation(current_route_name="sync")

        assert shell["current_tool"]["key"] == "jira"
        assert next(
            item for item in shell["current_sections"] if item["label"] == "Sync"
        )["active"] is True
        assert next(
            item for item in shell["current_sections"] if item["label"] == "Query"
        )["active"] is False

    def test_build_shell_navigation_only_expands_current_tool_sections(self):
        shell = WorkspaceService().build_shell_navigation(current_route_name="sync2pod")

        assert shell["current_tool"]["key"] == "sync2pod"
        assert shell["current_sections"] == []

    def test_star_service_toggles_route_and_object_entries(self):
        saved_query = JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=JiraSyncProfile.objects.get(name="My Issues"),
            jql_text='status = "Blocked"',
        )
        service = StarService()

        first = service.toggle(
            kind=WorkspaceStar.Kind.SAVED_QUERY,
            label=saved_query.name,
            route=f"/jira/query/?saved_query={saved_query.id}",
            group_key="jira",
            object_id=str(saved_query.id),
        )
        second = service.toggle(
            kind=WorkspaceStar.Kind.SAVED_QUERY,
            label=saved_query.name,
            route=f"/jira/query/?saved_query={saved_query.id}",
            group_key="jira",
            object_id=str(saved_query.id),
        )

        assert first.created is True
        assert second.created is False
        assert WorkspaceStar.objects.count() == 0
