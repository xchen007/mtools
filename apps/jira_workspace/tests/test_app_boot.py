from django.apps import apps
from django.test import SimpleTestCase
from django.urls import reverse


class JiraWorkspaceBootTests(SimpleTestCase):
    def test_dashboard_route_resolves_and_returns_ok(self):
        assert apps.is_installed("jira_workspace")

        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        assert b"Jira Dashboard" in response.content
