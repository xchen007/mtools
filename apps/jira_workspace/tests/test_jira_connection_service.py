from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from jira_workspace.models import JiraConnection
from jira_workspace.services.jira_connection_service import JiraConnectionService


class JiraConnectionServiceTests(TestCase):
    @patch("jira_workspace.services.jira_connection_service.JiraAdapter")
    def test_test_connection_records_successful_identity_check(self, adapter_class):
        connection = JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token-123",
        )
        adapter_class.from_connection.return_value.fetch_current_user.return_value = "xchen17"

        result = JiraConnectionService().test_connection(connection)

        result.refresh_from_db()
        assert result.last_check_status == JiraConnection.CheckStatus.OK
        assert result.last_check_message == "Connected as xchen17."
        assert result.last_checked_at is not None

    @patch("jira_workspace.services.jira_connection_service.JiraAdapter")
    def test_test_connection_records_failure_message_before_reraising(self, adapter_class):
        connection = JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token-123",
        )
        adapter_class.from_connection.return_value.fetch_current_user.side_effect = Exception(
            "401 Client Error: Unauthorized"
        )

        with self.assertRaises(Exception):
            JiraConnectionService().test_connection(connection)

        connection.refresh_from_db()
        assert connection.last_check_status == JiraConnection.CheckStatus.FAILED
        assert connection.last_check_message == "401 Client Error: Unauthorized"
        assert connection.last_checked_at is not None


class CheckJiraConnectionCommandTests(TestCase):
    @patch("jira_workspace.management.commands.check_jira_connection.JiraConnectionService")
    def test_check_jira_connection_command_runs_health_check(self, service_class):
        connection = JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token-123",
            last_check_status=JiraConnection.CheckStatus.OK,
            last_check_message="Connected as xchen17.",
        )
        service_class.return_value.test_connection.return_value = connection
        stdout = StringIO()

        call_command("check_jira_connection", stdout=stdout)

        service_class.return_value.test_connection.assert_called_once()
        assert "Jira connection ok: Connected as xchen17." in stdout.getvalue()
