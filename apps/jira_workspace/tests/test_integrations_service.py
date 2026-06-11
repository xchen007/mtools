from django.test import TestCase

from jira_workspace.models import IntegrationContract, IntegrationScanRun, IntegrationTool
from jira_workspace.services.integrations_service import IntegrationsService


class IntegrationsServiceTests(TestCase):
    def setUp(self):
        self.jira_sync = IntegrationTool.objects.create(
            key="jira-sync",
            name="Jira Sync",
            group="Issue Ops",
            readiness=IntegrationTool.Readiness.READY,
            description="Refreshes the Jira issue cache.",
        )
        IntegrationContract.objects.create(
            tool=self.jira_sync,
            input_contract="profile + JQL",
            output_contract="issue cache rows",
            event_contract="sync runs",
            notes="Stable contract surface.",
        )
        self.sync2pod = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into running pods.",
        )
        IntegrationContract.objects.create(
            tool=self.sync2pod,
            input_contract="watch path + pod target",
            output_contract="transfer summary",
            event_contract="",
            notes="Event stream not wired yet.",
        )
        IntegrationScanRun.objects.create(
            tool=self.sync2pod,
            status=IntegrationScanRun.Status.FAILED,
            summary="catalog refresh stalled on sync2pod metadata",
            error_message="event stream contract missing",
        )

    def test_build_catalog_groups_tools_and_filters_by_query(self):
        catalog = IntegrationsService().build_catalog(query="pod")

        assert len(catalog["groups"]) == 1
        assert catalog["groups"][0]["name"] == "Sync Ops"
        assert catalog["groups"][0]["items"][0]["key"] == "sync2pod"

    def test_build_catalog_exposes_contract_matrix_missing_fields_and_recent_runs(self):
        catalog = IntegrationsService().build_catalog()

        sync2pod_row = next(row for row in catalog["contract_rows"] if row["key"] == "sync2pod")
        assert sync2pod_row["readiness"] == IntegrationTool.Readiness.BETA
        assert sync2pod_row["event_status"] == "missing"
        assert sync2pod_row["missing_fields"] == ["events"]
        assert catalog["recent_runs"][0].tool == self.sync2pod
