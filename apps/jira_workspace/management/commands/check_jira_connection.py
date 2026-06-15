from django.core.management.base import BaseCommand, CommandError

from jira_workspace.services.jira_connection_service import JiraConnectionService


class Command(BaseCommand):
    help = "Check the active Jira connection and persist the health result."

    def handle(self, *args, **options):
        service = JiraConnectionService()
        try:
            connection = service.test_connection()
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Jira connection ok: {connection.last_check_message}"
            )
        )
