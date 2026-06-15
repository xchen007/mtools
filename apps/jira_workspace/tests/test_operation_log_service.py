from django.test import TestCase

from jira_workspace.models import OperationLog
from jira_workspace.services.operation_log_service import OperationLogService


class OperationLogServiceTests(TestCase):
    def test_start_log_creates_running_entry(self):
        service = OperationLogService()

        log = service.start_log(
            tool=OperationLog.Tool.JIRA_QUERY,
            action="run_card",
            title="Assigned to me",
            triggered_by="xchen17",
            request_payload={"card_id": 12},
        )

        assert log.status == OperationLog.Status.RUNNING
        assert log.request_payload_json == {"card_id": 12}

    def test_mark_success_updates_summary_and_body(self):
        service = OperationLogService()
        log = service.start_log(
            tool=OperationLog.Tool.JIRA_SYNC,
            action="full_sync",
            title="OPS Full Sync",
            triggered_by="xchen17",
        )

        service.mark_success(
            log,
            result_summary="Fetched 4 issues",
            log_text="inserted=2 updated=2",
        )
        log.refresh_from_db()

        assert log.status == OperationLog.Status.SUCCESS
        assert log.result_summary == "Fetched 4 issues"
        assert log.log_text == "inserted=2 updated=2"
        assert log.finished_at is not None
