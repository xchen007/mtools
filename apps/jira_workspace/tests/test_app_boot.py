from django.apps import apps
from django.test import TestCase
from django.urls import reverse


class JiraWorkspaceBootTests(TestCase):
    def test_dashboard_route_resolves_and_returns_ok(self):
        assert apps.is_installed("jira_workspace")

        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        assert b"Dashboard" in response.content

    def test_notion_app_is_not_installed(self):
        assert not apps.is_installed("notion")

    def test_notion_test_route_is_not_available(self):
        response = self.client.get("/notion/test/")

        assert response.status_code == 404
