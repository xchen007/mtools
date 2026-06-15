from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from jira_workspace.models import IntegrationScanRun, IntegrationTool, OperationLog
from jira_workspace.services.operation_log_service import OperationLogService


class IntegrationsService:
    CODE_PATHS = {
        "jira-sync": "apps/jira_workspace/services/sync_service.py",
        "jira-issues": "apps/jira_workspace/services/query_service.py",
        "sync2pod": "apps/jira_workspace/services/sync2pod_service.py",
        "integrations": "apps/jira_workspace/services/integrations_service.py",
    }

    def build_catalog(self, *, query=""):
        normalized_query = (query or "").strip()
        tools = IntegrationTool.objects.select_related("contract").order_by("group", "name")
        if normalized_query:
            tools = tools.filter(
                Q(name__icontains=normalized_query)
                | Q(key__icontains=normalized_query)
                | Q(group__icontains=normalized_query)
                | Q(description__icontains=normalized_query)
            )

        groups = []
        contract_rows = []
        current_group = None
        group_items = []
        tool_ids = []

        for tool in tools:
            if current_group != tool.group:
                if current_group is not None:
                    groups.append({"name": current_group, "items": group_items})
                current_group = tool.group
                group_items = []

            row = self._build_contract_row(tool)
            tool_ids.append(tool.id)
            contract_rows.append(row)
            group_items.append(
                {
                    "key": tool.key,
                    "name": tool.name,
                    "description": tool.description,
                    "readiness": tool.readiness,
                    "missing_fields": row["missing_fields"],
                    "code_available": self._code_available(tool.key),
                }
            )

        if current_group is not None:
            groups.append({"name": current_group, "items": group_items})

        recent_runs = list(
            IntegrationScanRun.objects.select_related("tool")
            .filter(tool_id__in=tool_ids or [-1])
            .order_by("-started_at")[:10]
        )

        return {
            "groups": groups,
            "contract_rows": contract_rows,
            "recent_runs": recent_runs,
            "query": normalized_query,
        }

    def run_scan(self, *, tool, triggered_by=""):
        log_service = OperationLogService()
        log = log_service.start_log(
            tool=OperationLog.Tool.INTEGRATIONS,
            action="run_scan",
            title=tool.name,
            triggered_by=triggered_by,
            target_type="integration_tool",
            target_id=tool.id,
            request_payload={"tool_id": tool.id, "tool_key": tool.key},
        )
        run = IntegrationScanRun.objects.create(
            tool=tool,
            status=IntegrationScanRun.Status.RUNNING,
        )

        try:
            summary = self._build_contract_row(tool)
            missing = summary["missing_fields"]
            summary_text = (
                f"Missing {', '.join(missing)} contracts"
                if missing
                else "All contracts available"
            )
            run.status = IntegrationScanRun.Status.SUCCESS
            run.summary = summary_text
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "summary", "finished_at"])
            log_service.mark_success(
                log,
                result_summary=summary_text,
                log_text=(
                    f"tool={tool.name}\n"
                    f"key={tool.key}\n"
                    f"input_status={summary['input_status']}\n"
                    f"output_status={summary['output_status']}\n"
                    f"event_status={summary['event_status']}\n"
                    f"notes={summary['notes']}"
                ),
            )
            return run
        except Exception as exc:
            run.status = IntegrationScanRun.Status.FAILED
            run.error_message = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])
            log_service.mark_failure(
                log,
                error_message=str(exc),
                log_text=f"tool={tool.name}\nerror={exc}",
            )
            raise

    def _build_contract_row(self, tool):
        contract = getattr(tool, "contract", None)
        input_status = self._field_status(contract.input_contract if contract else "")
        output_status = self._field_status(contract.output_contract if contract else "")
        event_status = self._field_status(contract.event_contract if contract else "")
        missing_fields = []
        if input_status == "missing":
            missing_fields.append("input")
        if output_status == "missing":
            missing_fields.append("output")
        if event_status == "missing":
            missing_fields.append("events")

        return {
            "key": tool.key,
            "name": tool.name,
            "group": tool.group,
            "readiness": tool.readiness,
            "input_status": input_status,
            "output_status": output_status,
            "event_status": event_status,
            "notes": contract.notes if contract else "",
            "missing_fields": missing_fields,
        }

    @staticmethod
    def _field_status(value):
        return "available" if value else "missing"

    def _code_available(self, key):
        relative_path = self.CODE_PATHS.get(key)
        if not relative_path:
            return False
        return Path(relative_path).exists()
