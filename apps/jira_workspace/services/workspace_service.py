from itertools import chain

from django.urls import reverse

from jira_workspace.models import (
    IntegrationScanRun,
    JiraSyncRun,
    Sync2PodRun,
    Sync2PodWatchEvent,
)
from jira_workspace.services.star_service import StarService
from jira_workspace.services.sync2pod_service import Sync2PodService


class WorkspaceService:
    TOOL_ROUTE_NAMES = {
        "workspace": {"workspace_home"},
        "jira": {"dashboard", "query", "queries", "issues", "sync", "profiles"},
        "sync2pod": {"sync2pod"},
        "integrations": {"integrations"},
    }
    JIRA_SECTION_ROUTE_NAMES = {
        "dashboard": {"dashboard"},
        "query": {"query", "queries", "issues"},
        "sync": {"sync"},
        "profiles": {"profiles"},
    }

    def build_shell_navigation(self, *, current_route_name):
        current_tool_key = self._current_tool_key(current_route_name)
        tools = self._build_tool_items(current_tool_key=current_tool_key)
        current_tool = next(
            (tool for tool in tools if tool["key"] == current_tool_key),
            tools[0],
        )
        return {
            "tools": tools,
            "current_tool": current_tool,
            "current_sections": self._build_current_sections(
                current_tool_key=current_tool_key,
                current_route_name=current_route_name,
            ),
            "starred_items": StarService().list_items(),
        }

    def build_home_context(self):
        sync2pod_capability = Sync2PodService().check_capabilities()
        health_items = self._build_health_items(sync2pod_capability=sync2pod_capability)
        summary_cards = [
            {
                "title": "Jira Sync Runs",
                "value": JiraSyncRun.objects.count(),
                "detail": self._latest_jira_detail(),
            },
            {
                "title": "sync2pod Queue",
                "value": Sync2PodWatchEvent.objects.filter(
                    status=Sync2PodWatchEvent.Status.QUEUED
                ).count(),
                "detail": self._latest_sync2pod_detail(
                    sync2pod_capability=sync2pod_capability
                ),
            },
            {
                "title": "Integration Scans",
                "value": IntegrationScanRun.objects.count(),
                "detail": self._latest_integration_detail(),
            },
        ]

        return {
            "summary_cards": summary_cards,
            "recent_activity": self._build_recent_activity(),
            "health_items": health_items,
            "rail_sections": self.build_rail_sections(health_items=health_items),
        }

    def build_rail_sections(self, *, health_items=None):
        health_map = {
            item["label"]: item["value"]
            for item in (health_items or self._build_health_items())
        }
        jira_runs = JiraSyncRun.objects.count()
        sync2pod_queue = Sync2PodWatchEvent.objects.filter(
            status=Sync2PodWatchEvent.Status.QUEUED
        ).count()
        integration_scans = IntegrationScanRun.objects.count()

        return [
            {
                "title": "Service Status",
                "items": [
                    {
                        "label": "Jira",
                        "value": self._count_label(jira_runs, "run", "runs"),
                        "status": health_map.get("Jira", "ok"),
                        "icon": "J",
                    },
                    {
                        "label": "sync2pod",
                        "value": self._count_label(sync2pod_queue, "queued", "queued"),
                        "status": health_map.get("sync2pod", "ok"),
                        "icon": "S",
                    },
                    {
                        "label": "Integrations",
                        "value": self._count_label(integration_scans, "scan", "scans"),
                        "status": health_map.get("Integrations", "ok"),
                        "icon": "I",
                    },
                ],
            },
        ]

    @staticmethod
    def _count_label(count, singular, plural):
        return f"{count} {singular if count == 1 else plural}"

    def _build_recent_activity(self):
        jira_runs = [
            {
                "tool": "Jira Sync",
                "title": run.profile.name,
                "status": run.status,
                "summary": f"{run.get_run_type_display()} run fetched {run.fetched_count} issues.",
                "started_at": run.started_at,
            }
            for run in JiraSyncRun.objects.select_related("profile").order_by("-started_at")[:5]
        ]
        sync2pod_runs = [
            {
                "tool": "sync2pod",
                "title": run.profile.name,
                "status": run.status,
                "summary": run.error_message
                or run.stdout_log
                or run.command_line
                or "No output recorded.",
                "started_at": run.started_at,
            }
            for run in Sync2PodRun.objects.select_related("profile").order_by("-started_at")[:5]
        ]
        integration_runs = [
            {
                "tool": "Integrations",
                "title": run.tool.name,
                "status": run.status,
                "summary": run.error_message or run.summary or "No summary recorded.",
                "started_at": run.started_at,
            }
            for run in IntegrationScanRun.objects.select_related("tool").order_by("-started_at")[:5]
        ]

        return sorted(
            chain(jira_runs, sync2pod_runs, integration_runs),
            key=lambda item: item["started_at"],
            reverse=True,
        )[:10]

    def _build_health_items(self, *, sync2pod_capability=None):
        latest_jira_failure = (
            JiraSyncRun.objects.filter(status=JiraSyncRun.Status.FAILED)
            .order_by("-started_at")
            .first()
        )
        if sync2pod_capability is None:
            sync2pod_capability = Sync2PodService().check_capabilities()
        latest_sync2pod_failure = (
            Sync2PodRun.objects.filter(status=Sync2PodRun.Status.FAILED)
            .order_by("-started_at")
            .first()
        )
        latest_integration_failure = (
            IntegrationScanRun.objects.filter(status=IntegrationScanRun.Status.FAILED)
            .order_by("-started_at")
            .first()
        )
        return [
            {
                "label": "Jira",
                "value": "blocked" if latest_jira_failure else "ok",
            },
            {
                "label": "sync2pod",
                "value": (
                    "blocked"
                    if latest_sync2pod_failure or not sync2pod_capability["is_available"]
                    else "ok"
                ),
            },
            {
                "label": "Integrations",
                "value": "blocked" if latest_integration_failure else "ok",
            },
        ]

    @staticmethod
    def _latest_jira_detail():
        run = JiraSyncRun.objects.order_by("-started_at").first()
        if not run:
            return "No Jira syncs yet."
        return f"Latest status: {run.status}"

    @staticmethod
    def _latest_sync2pod_detail(*, sync2pod_capability=None):
        if sync2pod_capability and not sync2pod_capability["is_available"]:
            return sync2pod_capability["message"]
        run = Sync2PodRun.objects.order_by("-started_at").first()
        if not run:
            return "No sync2pod runs yet."
        return run.error_message or run.stdout_log or run.status

    @staticmethod
    def _latest_integration_detail():
        run = IntegrationScanRun.objects.order_by("-started_at").first()
        if not run:
            return "No integration scans yet."
        return run.error_message or run.summary or run.status

    def _current_tool_key(self, current_route_name):
        for tool_key, route_names in self.TOOL_ROUTE_NAMES.items():
            if current_route_name in route_names:
                return tool_key
        return "workspace"

    def _build_tool_items(self, *, current_tool_key):
        items = [
            ("workspace", "Workspace", "/workspace/", "Home"),
            ("jira", "Jira", reverse("jira_workspace:query"), "Tool"),
            ("sync2pod", "sync2pod", "/sync2pod/", "Tool"),
            ("integrations", "Integrations", "/integrations/", "Tool"),
        ]
        return [
            {
                "key": key,
                "label": label,
                "href": href,
                "badge": badge,
                "active": key == current_tool_key,
            }
            for key, label, href, badge in items
        ]

    def _build_current_sections(self, *, current_tool_key, current_route_name):
        if current_tool_key != "jira":
            return []

        items = [
            ("dashboard", "Dashboard", reverse("jira_workspace:dashboard")),
            ("query", "Query", reverse("jira_workspace:query")),
            ("sync", "Sync", reverse("jira_workspace:sync")),
            ("profiles", "Profiles", reverse("jira_workspace:profiles")),
        ]
        return [
            {
                "key": key,
                "label": label,
                "href": href,
                "active": current_route_name in self.JIRA_SECTION_ROUTE_NAMES[key],
            }
            for key, label, href in items
        ]
