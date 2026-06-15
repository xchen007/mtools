from django.utils import timezone

from jira_workspace.models import JiraConnection
from jira_workspace.services.jira_adapter import JiraAdapter


class JiraConnectionService:
    def get_active_connection(self):
        return JiraConnection.objects.active().order_by("-updated_at").first()

    def test_connection(self, connection=None):
        connection = connection or self.get_active_connection()
        if connection is None:
            raise ValueError("No active Jira connection is configured.")

        try:
            username = JiraAdapter.from_connection(connection).fetch_current_user()
        except Exception as exc:
            connection.last_check_status = JiraConnection.CheckStatus.FAILED
            connection.last_check_message = str(exc)
            connection.last_checked_at = timezone.now()
            connection.save(
                update_fields=[
                    "last_check_status",
                    "last_check_message",
                    "last_checked_at",
                    "updated_at",
                ]
            )
            raise

        connection.last_check_status = JiraConnection.CheckStatus.OK
        connection.last_check_message = (
            f"Connected as {username}." if username else "Connected to Jira."
        )
        connection.last_checked_at = timezone.now()
        connection.save(
            update_fields=[
                "last_check_status",
                "last_check_message",
                "last_checked_at",
                "updated_at",
            ]
        )
        return connection
