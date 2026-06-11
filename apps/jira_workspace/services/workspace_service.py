from itertools import chain

from jira_workspace.models import (
    IntegrationScanRun,
    JiraSyncRun,
    Sync2PodRun,
    Sync2PodWatchEvent,
)


class WorkspaceService:
    def build_home_context(self):
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
                "detail": self._latest_sync2pod_detail(),
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
            "health_items": self._build_health_items(),
            "rail_sections": self.build_rail_sections(),
        }

    def build_rail_sections(self):
        return [
            {
                "title": "Activity",
                "items": [
                    {
                        "label": "Jira sync runs",
                        "value": str(JiraSyncRun.objects.count()),
                    },
                    {
                        "label": "sync2pod queue",
                        "value": str(
                            Sync2PodWatchEvent.objects.filter(
                                status=Sync2PodWatchEvent.Status.QUEUED
                            ).count()
                        ),
                    },
                    {
                        "label": "integration scans",
                        "value": str(IntegrationScanRun.objects.count()),
                    },
                ],
            },
            {
                "title": "Health",
                "items": self._build_health_items(),
            },
        ]

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

    def _build_health_items(self):
        latest_jira_failure = (
            JiraSyncRun.objects.filter(status=JiraSyncRun.Status.FAILED)
            .order_by("-started_at")
            .first()
        )
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
                "value": "blocked" if latest_sync2pod_failure else "ok",
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
    def _latest_sync2pod_detail():
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
