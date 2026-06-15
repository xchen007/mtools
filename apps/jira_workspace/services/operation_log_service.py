from django.utils import timezone

from jira_workspace.models import OperationLog


class OperationLogService:
    def list_logs(self, *, tool="", status="", action=""):
        queryset = OperationLog.objects.order_by("-started_at", "-id")
        if tool:
            queryset = queryset.filter(tool=tool)
        if status:
            queryset = queryset.filter(status=status)
        if action:
            queryset = queryset.filter(action=action)
        return list(queryset)

    def recent_logs(self, *, tool="", target_type="", target_id="", limit=5):
        queryset = OperationLog.objects.order_by("-started_at", "-id")
        if tool:
            queryset = queryset.filter(tool=tool)
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        if target_id != "":
            queryset = queryset.filter(target_id=str(target_id))
        return list(queryset[:limit])

    def start_log(
        self,
        *,
        tool,
        action,
        title,
        triggered_by="",
        target_type="",
        target_id="",
        request_payload=None,
    ):
        return OperationLog.objects.create(
            tool=tool,
            action=action,
            title=title,
            triggered_by=triggered_by or "",
            target_type=target_type or "",
            target_id=str(target_id or ""),
            request_payload_json=request_payload or {},
            started_at=timezone.now(),
        )

    def mark_success(self, log, *, result_summary="", log_text=""):
        log.status = OperationLog.Status.SUCCESS
        log.result_summary = result_summary
        log.log_text = log_text
        log.finished_at = timezone.now()
        log.save(
            update_fields=[
                "status",
                "result_summary",
                "log_text",
                "finished_at",
                "updated_at",
            ]
        )
        return log

    def mark_failure(self, log, *, error_message="", log_text=""):
        log.status = OperationLog.Status.FAILED
        log.error_message = error_message
        log.log_text = log_text
        log.finished_at = timezone.now()
        log.save(
            update_fields=[
                "status",
                "error_message",
                "log_text",
                "finished_at",
                "updated_at",
            ]
        )
        return log
