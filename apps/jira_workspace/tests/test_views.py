import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from jira_workspace.models import (
    IntegrationContract,
    IntegrationScanRun,
    IntegrationTool,
    JiraConnection,
    JiraIssue,
    JiraIssueScopeMembership,
    JiraScopeSyncReport,
    OperationLog,
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraSavedQuery,
    JiraSyncProfile,
    JiraSyncRun,
    SyncScope,
    Sync2PodProfile,
    Sync2PodRun,
    Sync2PodWatchEvent,
    WorkspaceStar,
)
from jira_workspace.services.sync_service import ActiveFullSyncError


def create_current_policy_scope():
    policy = GlobalSyncPolicy.objects.create(
        name="Primary Jira Policy",
        strategy_json={"required_self": True, "scopes": []},
        strategy_hash="hash-v1",
        status=GlobalSyncPolicy.Status.READY,
    )
    version = GlobalSyncPolicyVersion.objects.create(
        policy=policy,
        version_no=1,
        strategy_hash="hash-v1",
        status=GlobalSyncPolicyVersion.Status.READY,
        full_sync_required=False,
    )
    policy.current_version = version
    policy.save(update_fields=["current_version", "updated_at"])
    scope = SyncScope.objects.create(
        policy_version=version,
        scope_type=SyncScope.ScopeType.SELF_REQUIRED,
        name="My Assigned or Reported Issues",
        is_required=True,
        is_enabled=True,
        is_system_scope=True,
        schedule_minutes=30,
        config_json={"mode": "self"},
        base_jql="assignee = currentUser() OR reporter = currentUser()",
        next_run_at=datetime.now(timezone.utc),
    )
    return version, scope


def add_policy_membership(*, issue, version, scope):
    JiraIssueScopeMembership.objects.create(
        issue=issue,
        scope=scope,
        policy_version=version,
        first_seen_at=datetime.now(timezone.utc),
        last_checked_at=datetime.now(timezone.utc),
        last_synced_success_at=datetime.now(timezone.utc),
        last_seen_issue_updated_at=issue.updated_at,
        is_active=True,
    )


class JiraWorkspaceDashboardViewTests(TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.policy_version, self.sync_scope = create_current_policy_scope()
        assigned_issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="Review",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=self.now - timedelta(days=1),
            created_at=self.now - timedelta(days=2),
            raw_json="{}",
            last_seen_at=self.now,
        )
        created_issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Created issue",
            status="Blocked",
            assignee="ravi",
            reporter="xchen17",
            priority="Medium",
            updated_at=self.now - timedelta(days=2),
            created_at=self.now - timedelta(days=3),
            raw_json="{}",
            last_seen_at=self.now,
        )
        for issue in [assigned_issue, created_issue]:
            add_policy_membership(
                issue=issue,
                version=self.policy_version,
                scope=self.sync_scope,
            )

    def test_dashboard_renders_recent_assigned_and_created_ticket_table_without_default_detail(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "15d" in content
        assert "Assigned Issues" in content
        assert "Created Issues" in content
        assert "Tracked Projects" in content
        assert "Blocked Issues" in content
        assert "Issue Results" in content
        assert "TESS-321" in content
        assert "OPS-778" in content
        assert 'data-ticket-row' in content
        assert 'data-ticket-key="TESS-321"' in content
        assert 'data-ticket-summary="Refine query presets"' in content
        assert 'data-ticket-drawer' in content
        assert 'aria-hidden="true"' in content
        assert "Recently Updated" not in content
        assert "Assigned To Me" not in content
        assert "Created By Me" not in content
        assert "Issue Detail" not in content
        assert "?range=30d" in content

    def test_dashboard_uses_compact_controlbar_without_duplicate_location_header(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="workspace-breadcrumb"' not in content
        assert '<h1 class="page-title">Dashboard</h1>' not in content
        assert "Current issue activity across your tracked Jira work." not in content
        assert 'class="page-section page-section--dashboard"' in content
        assert 'class="dashboard-controlbar"' in content
        assert 'class="dashboard-range"' in content
        assert content.index('class="dashboard-range"') < content.index("Assigned Issues")
        assert 'aria-label="Time range"' in content

    def test_dashboard_and_ticket_drawer_use_productized_workflow_hooks(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="dashboard-summary-strip"' in content
        assert 'class="ticket-drawer__actions"' in content
        assert 'data-ticket-copy-active-key' in content
        assert 'class="ticket-drawer__tabs"' in content
        assert 'data-ticket-drawer-tab="properties"' in content
        assert 'data-ticket-drawer-tab="activity"' in content

    def test_dashboard_ticket_table_partial_filters_assigned_project(self):
        JiraConnection.objects.create(
            base_url="https://jirap-cli.corp.ebay.com",
            api_token="token-123",
            auth_type=JiraConnection.AuthType.BEARER,
        )

        response = self.client.get(
            reverse("jira_workspace:dashboard_ticket_table"),
            {"source": "assigned", "project": "TESS"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "TESS-321" in content
        assert "OPS-778" not in content
        assert 'data-rich-table-ticket-browse-base-url="https://jirap.corp.ebay.com"' in content

    def test_live_state_endpoint_reports_asset_and_data_versions(self):
        response = self.client.get(reverse("jira_workspace:live_state"))

        assert response.status_code == 200
        payload = response.json()
        assert payload["asset_version"]
        assert payload["data_version"]
        assert payload["poll_interval_ms"] == 2500

    def test_dashboard_ticket_table_has_auto_refresh_target(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-auto-refresh-target="dashboard-tickets"' in content
        assert 'data-auto-refresh-url="/jira/dashboard/tickets/' in content

    def test_dashboard_surfaces_external_blocker_when_local_cache_is_empty(self):
        JiraIssue.objects.all().delete()
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
            is_default=True,
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=self.now - timedelta(minutes=10),
            finished_at=self.now - timedelta(minutes=9),
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
            error_message="Jira returned 403: The request is blocked.",
        )

        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "External Jira access is currently blocked" in content
        assert "No cached Jira issues are available yet." in content

    def test_dashboard_does_not_treat_out_of_range_active_cache_as_empty(self):
        JiraIssueScopeMembership.objects.update(is_active=False)
        old_issue = JiraIssue.objects.create(
            issue_key="OLD-100",
            project_key="OLD",
            summary="Older active cache",
            status="Done",
            assignee="xchen17",
            reporter="amy",
            priority="Low",
            updated_at=self.now - timedelta(days=30),
            created_at=self.now - timedelta(days=31),
            raw_json="{}",
            last_seen_at=self.now,
            is_active_in_current_policy=True,
        )
        add_policy_membership(
            issue=old_issue,
            version=self.policy_version,
            scope=self.sync_scope,
        )
        profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
            is_default=True,
        )
        JiraSyncRun.objects.create(
            profile=profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=self.now - timedelta(minutes=10),
            finished_at=self.now - timedelta(minutes=9),
            error_message="Jira returned 403: The request is blocked.",
        )

        response = self.client.get(reverse("jira_workspace:dashboard"), {"range": "7d"})

        assert response.status_code == 200
        content = response.content.decode()
        assert "External Jira access is currently blocked" not in content
        assert "No cached Jira issues are available yet." not in content

    def test_dashboard_surfaces_current_cache_alignment_status(self):
        self.sync_scope.last_run_status = SyncScope.RunStatus.FAILED
        self.sync_scope.last_error_message = "Required scope failure"
        self.sync_scope.save(update_fields=["last_run_status", "last_error_message", "updated_at"])
        policy = self.policy_version.policy
        policy.status = GlobalSyncPolicy.Status.STALE
        policy.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Cache Alignment" in content
        assert "Stale" in content
        assert "Required scope failure" in content


class JiraWorkspaceSecondaryPagesTests(TestCase):
    def setUp(self):
        self.policy_version, self.sync_scope = create_current_policy_scope()
        self.profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
            is_default=True,
        )
        JiraSavedQuery.objects.create(
            name="My Open Blockers",
            profile=self.profile,
            description="Blocked work owned by me.",
            filters_json={"status": ["Blocked"]},
            jql_text='status = "Blocked"',
            is_starred=True,
            is_pinned=True,
        )
        JiraSavedQuery.objects.create(
            name="Team Review Queue",
            profile=self.profile,
            filters_json={"status": ["Review"], "project": ["TESS"]},
            jql_text='project = "TESS" AND status = "Review"',
            sort_by="priority",
            sort_order="asc",
        )
        review_issue = JiraIssue.objects.create(
            issue_key="TESS-321",
            project_key="TESS",
            summary="Refine query presets",
            status="Review",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            sprint="Sprint 42",
            issue_type="Bug",
            labels_json=["backend", "urgent"],
            updated_at=datetime.now(timezone.utc) - timedelta(hours=4),
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            raw_json="{}",
            last_seen_at=datetime.now(timezone.utc),
        )
        blocker_issue = JiraIssue.objects.create(
            issue_key="OPS-778",
            project_key="OPS",
            summary="Escalate blocker handling",
            status="Blocked",
            assignee="xchen17",
            reporter="xchen17",
            priority="Highest",
            sprint="Sprint 42",
            issue_type="Incident",
            labels_json=["customer-impact", "urgent"],
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            raw_json="{}",
            last_seen_at=datetime.now(timezone.utc),
        )
        for issue in [review_issue, blocker_issue]:
            add_policy_membership(
                issue=issue,
                version=self.policy_version,
                scope=self.sync_scope,
            )
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.SUCCESS,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            finished_at=datetime.now(timezone.utc),
            fetched_count=3,
            inserted_count=1,
            updated_count=1,
            skipped_count=1,
        )
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=19),
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
            error_message="Jira returned 403: The request is blocked.",
        )

    def test_query_page_renders_query_library_and_filter_details(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        assert "Query Cards" in content
        assert "My Open Blockers" in content
        assert "Blocked work owned by me." in content
        assert 'status = "Blocked"' in content
        assert "New Card" in content
        assert "Card type" in content
        assert "Query syntax" in content
        assert "Query Results" in content
        assert "OPS-778" in content
        assert "TESS-321" not in content

    def test_query_page_surfaces_empty_cache_state_instead_of_silent_zero_results(self):
        JiraIssue.objects.all().delete()

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Jira Data Status" in content
        assert "No cached Jira issues are available yet." in content
        assert "External Jira access is currently blocked" in content
        assert "Jira returned 403: The request is blocked." in content

    def test_query_page_treats_inactive_only_policy_cache_as_empty(self):
        JiraIssueScopeMembership.objects.update(is_active=False)

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "No cached Jira issues are available yet." in content

    def test_query_page_surfaces_active_policy_ticket_freshness(self):
        self.sync_scope.last_successful_check_at = datetime.now(timezone.utc)
        self.sync_scope.save(update_fields=["last_successful_check_at", "updated_at"])

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Current Policy Version" in content
        assert "Last Successful Check" in content

    def test_query_page_can_persist_a_saved_query_from_editor_form(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "save_query",
                "name": "OPS Blockers",
                "profile": str(self.profile.id),
                "description": "Track OPS blockers",
                "project_values": "OPS",
                "status_values": "Blocked",
                "jql_text": 'project = "OPS" AND status = "Blocked"',
                "sort_by": "priority",
                "sort_order": "asc",
                "is_starred": "on",
            },
        )

        assert response.status_code == 302
        saved_query = JiraSavedQuery.objects.get(name="OPS Blockers")
        assert saved_query.profile == self.profile
        assert saved_query.filters_json == {"project": ["OPS"], "status": ["Blocked"]}
        assert saved_query.sort_by == "priority"
        assert saved_query.sort_order == "asc"
        assert saved_query.is_starred is True

    def test_query_page_allows_selecting_a_saved_query(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"saved_query": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        assert "Team Review Queue" in content
        assert "TESS-321" in content
        assert "OPS-778" not in content

    def test_query_page_can_create_query_card(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "create_card",
                "name": "OPS Blockers",
                "profile": str(self.profile.id),
                "description": "Track OPS blockers",
                "card_kind": JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY,
                "query_syntax": JiraSavedQuery.QuerySyntax.LOCAL_FILTER,
                "project_values": "OPS",
                "status_values": "Blocked",
                "jql_text": 'project = "OPS" AND status = "Blocked"',
                "summary_metric_values": "total, blocked, high_priority",
                "default_column_values": "issue_key, summary, status, priority",
                "default_page_size": "50",
                "sort_by": "priority",
                "sort_order": "asc",
                "is_starred": "on",
            },
        )

        assert response.status_code == 302
        saved_query = JiraSavedQuery.objects.get(name="OPS Blockers")
        assert response["Location"] == f"{reverse('jira_workspace:query')}?card={saved_query.id}"
        assert saved_query.filters_json == {"project": ["OPS"], "status": ["Blocked"]}
        assert saved_query.summary_metrics_json == ["total", "blocked", "high_priority"]
        assert saved_query.default_columns_json == ["issue_key", "summary", "status", "priority"]
        assert saved_query.default_page_size == 50
        assert saved_query.query_syntax == JiraSavedQuery.QuerySyntax.LOCAL_FILTER
        assert saved_query.is_starred is True

    def test_new_query_card_defaults_to_all_ticket_columns_when_column_order_is_omitted(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "create_card",
                "name": "All Column Card",
                "profile": str(self.profile.id),
                "description": "Uses all default columns",
                "card_kind": JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY,
                "query_syntax": JiraSavedQuery.QuerySyntax.LOCAL_FILTER,
                "default_page_size": "25",
                "sort_by": "updated_at",
                "sort_order": "desc",
            },
        )

        assert response.status_code == 302
        saved_query = JiraSavedQuery.objects.get(name="All Column Card")
        assert saved_query.default_columns_json == [
            "issue_key",
            "project_key",
            "summary",
            "status",
            "assignee",
            "reporter",
            "priority",
            "updated_at",
            "sprint",
            "created_at",
        ]

    def test_query_page_can_update_query_card(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "update_card",
                "card_id": str(selected.id),
                "name": "TESS Review Updated",
                "profile": str(self.profile.id),
                "description": "Updated review queue",
                "card_kind": JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY,
                "query_syntax": JiraSavedQuery.QuerySyntax.JQL_TEXT,
                "project_values": "TESS",
                "status_values": "Review",
                "jql_text": 'project = "TESS" AND status = "Review"',
                "summary_metric_values": "total, in_progress",
                "default_column_values": "issue_key, project_key, summary",
                "default_page_size": "25",
                "sort_by": "updated_at",
                "sort_order": "desc",
                "is_pinned": "on",
            },
        )

        assert response.status_code == 302
        selected.refresh_from_db()
        assert response["Location"] == f"{reverse('jira_workspace:query')}?card={selected.id}"
        assert selected.name == "TESS Review Updated"
        assert selected.query_syntax == JiraSavedQuery.QuerySyntax.JQL_TEXT
        assert selected.summary_metrics_json == ["total", "in_progress"]
        assert selected.default_columns_json == ["issue_key", "project_key", "summary"]
        assert selected.is_pinned is True

    def test_query_page_saves_submitted_default_column_order(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "update_card",
                "card_id": str(selected.id),
                "name": "Ordered Columns",
                "profile": str(self.profile.id),
                "card_kind": JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY,
                "query_syntax": JiraSavedQuery.QuerySyntax.LOCAL_FILTER,
                "default_column_values": "summary, issue_key, created_at, sprint",
                "default_page_size": "25",
                "sort_by": "updated_at",
                "sort_order": "desc",
            },
        )

        assert response.status_code == 302
        selected.refresh_from_db()
        assert selected.default_columns_json == ["summary", "issue_key", "created_at", "sprint"]

    def test_query_page_allows_selecting_card_parameter_and_legacy_saved_query_parameter(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        card_response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})
        legacy_response = self.client.get(reverse("jira_workspace:query"), {"saved_query": selected.id})

        assert card_response.status_code == 200
        assert legacy_response.status_code == 200
        assert "TESS-321" in card_response.content.decode()
        assert "TESS-321" in legacy_response.content.decode()

    def test_query_page_can_duplicate_and_delete_query_cards(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        duplicate_response = self.client.post(
            reverse("jira_workspace:query"),
            {"action": "duplicate_card", "card_id": str(selected.id)},
        )

        duplicate = JiraSavedQuery.objects.get(name="Team Review Queue Copy")
        assert duplicate_response.status_code == 302
        assert duplicate_response["Location"] == f"{reverse('jira_workspace:query')}?card={duplicate.id}"
        assert duplicate.filters_json == selected.filters_json

        delete_response = self.client.post(
            reverse("jira_workspace:query"),
            {"action": "delete_card", "card_id": str(duplicate.id)},
        )

        assert delete_response.status_code == 302
        assert not JiraSavedQuery.objects.filter(id=duplicate.id).exists()
        assert "card=" in delete_response["Location"]

    def test_query_run_now_post_creates_operation_log(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.post(
            reverse("jira_workspace:query"),
            {"action": "run_card", "card_id": str(selected.id)},
        )

        assert response.status_code == 302
        assert response["Location"] == f"{reverse('jira_workspace:query')}?card={selected.id}"
        log = OperationLog.objects.get(tool=OperationLog.Tool.JIRA_QUERY, action="run_card")
        assert log.title == "Team Review Queue"
        assert log.status == OperationLog.Status.SUCCESS
        assert log.target_type == "query_card"
        assert log.target_id == str(selected.id)

    def test_query_page_renders_recent_operation_logs(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")
        OperationLog.objects.create(
            tool=OperationLog.Tool.JIRA_QUERY,
            action="run_card",
            status=OperationLog.Status.SUCCESS,
            title="Team Review Queue",
            triggered_by="xchen17",
            target_type="query_card",
            target_id=str(selected.id),
            result_summary="1 results",
            log_text="query run succeeded",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        assert "Recent Logs" not in content
        assert "Logs" in content
        assert "Team Review Queue" in content
        assert 'data-query-results-view-tab="results"' in content
        assert 'data-query-results-view-tab="logs"' in content
        assert 'data-query-results-panel="results"' in content
        assert 'data-query-results-panel="logs"' in content

    def test_query_page_preserves_editor_state_for_invalid_card_input(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "create_card",
                "name": "",
                "profile": str(self.profile.id),
                "card_kind": JiraSavedQuery.CardKind.JIRA_ISSUE_QUERY,
                "query_syntax": JiraSavedQuery.QuerySyntax.LOCAL_FILTER,
                "default_page_size": "25",
                "sort_by": "updated_at",
                "sort_order": "desc",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-query-card-editor' in content
        assert 'data-editor-open="true"' in content

    def test_new_query_card_uses_centered_modal_with_filter_fields_and_suggestions(self):
        response = self.client.get(reverse("jira_workspace:query"), {"editor": "new"})

        assert response.status_code == 200
        content = unescape(response.content.decode())
        assert 'class="query-card-editor__panel query-card-editor__panel--modal"' in content
        assert 'name="reporter_value" value="xchen17"' in content
        assert 'name="assignee_value" value="xchen17"' in content
        assert 'name="project_values"' in content
        assert 'list="query-card-project-options"' in content
        assert '<option value="TESS">' in content
        assert '<option value="OPS">' in content
        assert 'name="label_values"' in content
        assert 'name="sprint_value"' in content
        assert 'name="issue_type_values"' in content
        assert 'name="priority_values"' in content
        assert 'data-query-card-column-editor' in content
        assert 'name="default_column_values"' in content
        assert 'value="issue_key, project_key, summary, status, assignee, reporter, priority, updated_at, sprint, created_at"' in content
        assert 'data-column-key="created_at"' in content
        assert 'data-column-move="up"' in content
        assert 'data-column-move="down"' in content

    def test_new_query_card_can_save_people_project_label_sprint_type_and_priority_filters(self):
        response = self.client.post(
            reverse("jira_workspace:query"),
            {
                "action": "create_card",
                "name": "Focused Jira Search",
                "profile": str(self.profile.id),
                "description": "Focused search",
                "reporter_value": "amy",
                "assignee_value": "xchen17",
                "project_values": "TESS, NEWPROJ",
                "label_values": "backend, urgent",
                "sprint_value": "Sprint 42",
                "issue_type_values": "Bug",
                "priority_values": "High",
                "sort_by": "updated_at",
                "sort_order": "desc",
            },
        )

        assert response.status_code == 302
        saved_query = JiraSavedQuery.objects.get(name="Focused Jira Search")
        assert saved_query.filters_json == {
            "reporter": "amy",
            "assignee": "xchen17",
            "project": ["TESS", "NEWPROJ"],
            "labels": ["backend", "urgent"],
            "sprint": "Sprint 42",
            "issue_type": ["Bug"],
            "priority": ["High"],
        }

        detail_response = self.client.get(
            reverse("jira_workspace:query"),
            {"card": saved_query.id},
        )
        detail_content = unescape(detail_response.content.decode())
        assert "reporter = amy" in detail_content
        assert "assignee = xchen17" in detail_content
        assert "labels include backend, urgent" in detail_content
        assert "sprint = Sprint 42" in detail_content
        assert "type in (Bug)" in detail_content
        assert "priority in (High)" in detail_content

    def test_query_page_renders_query_card_workbench(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        assert "Query Cards" in content
        assert "New Card" in content
        assert "Edit card" in content
        assert "Duplicate" in content
        assert "Copy query" in content
        assert 'data-query-card-editor' in content
        assert 'data-query-card-editor-open' in content
        assert 'data-query-card-editor-close' in content
        assert f'data-rich-table-persist-scope="/jira/query/card/{selected.id}/"' in content
        assert "Total results" in content
        assert "In progress" in content
        assert "Card type" in content
        assert "Query syntax" in content

    def test_query_page_renders_open_jira_sync_shortcut(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        header = content.split('<header class="query-card-header">', 1)[1].split("</header>", 1)[0]

        assert "Open Jira Sync" in header
        assert f'href="{reverse("jira_workspace:sync")}"' in header
        assert "Run now" in header

    def test_query_summary_metrics_render_inside_results_header(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        before_results, results_panel = content.split(
            '<section class="panel dashboard-main query-workbench__results">',
            1,
        )
        results_header = results_panel.split('data-query-results-panel="results"', 1)[0]

        assert 'aria-label="Current query summary"' not in before_results
        assert 'aria-label="Current query summary"' in results_header
        assert results_header.index("Query Results") < results_header.index("Current query summary")
        assert results_header.index("Results") < results_header.index("Logs")
        assert "Total results" in results_header
        assert "status-pill--neutral" not in results_header
        assert " rows" not in results_header

    def test_query_results_default_to_results_panel_with_logs_panel_hidden(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        results_panel = content.split('data-query-results-panel="results"', 1)[1].split(">", 1)[0]
        logs_panel = content.split('data-query-results-panel="logs"', 1)[1].split(">", 1)[0]

        assert 'data-view-active="true"' in results_panel
        assert "hidden" in logs_panel

    def test_query_cards_remain_in_left_sidebar_after_sync_navigation_addition(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]
        app_main = content.split('<main class="app-main">', 1)[1].split("</main>", 1)[0]

        assert 'aria-label="Jira Query Cards"' in app_nav
        assert "My Open Blockers" in app_nav
        assert "Team Review Queue" in app_nav
        assert "New Card" in app_nav
        assert 'aria-label="Current Tool"' not in app_nav
        assert "Sync" not in app_nav
        assert 'aria-label="Jira Query Cards"' not in app_main
        assert 'query-workbench__nav' not in app_main

    def test_query_card_rules_render_in_main_detail_not_left_nav(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]
        app_main = content.split('<main class="app-main">', 1)[1].split("</main>", 1)[0]

        assert 'query-card-nav__preview' not in app_nav
        assert 'status = "Blocked"' not in app_nav
        assert "Query rule" in app_main
        assert 'status = "Blocked"' in app_main

    def test_query_card_nav_shows_only_function_names_without_data_chips(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]
        app_main = content.split('<main class="app-main">', 1)[1].split("</main>", 1)[0]

        assert "My Open Blockers" in app_nav
        assert "Team Review Queue" in app_nav
        assert 'query-card-nav__count' not in app_nav
        assert 'query-card-nav__tags' not in app_nav
        assert "Local Filter" not in app_nav
        assert "Table" not in app_nav
        assert "metrics" not in app_nav
        assert "Local Filter" in app_main
        assert "Total results" in app_main

    def test_query_card_nav_uses_single_new_card_entry(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]

        assert app_nav.count("New Card") == 1
        assert "+ Create a reusable query card" not in app_nav
        assert "query-card-nav__create" not in app_nav

    def test_new_query_card_editor_does_not_render_delete_action(self):
        response = self.client.get(reverse("jira_workspace:query"), {"editor": "new"})

        assert response.status_code == 200
        content = unescape(response.content.decode())
        editor = content.split('<div class="query-card-editor', 1)[1].split("</form>", 1)[0]

        assert "New Query Card" in editor
        assert "Edit Query Card" not in editor
        assert 'name="action" value="create_card"' in editor
        assert 'name="action" value="delete_card"' not in editor
        assert 'name="card_id"' not in editor

    def test_global_shell_renders_new_query_card_editor_on_non_query_pages(self):
        response = self.client.get(reverse("jira_workspace:issues"))

        assert response.status_code == 200
        content = unescape(response.content.decode())
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]
        editor = content.split('<div class="query-card-editor', 1)[1].split("</form>", 1)[0]

        assert "Query Cards" in app_nav
        assert "New Card" in app_nav
        assert "Team Review Queue" in app_nav
        assert content.count('data-query-card-editor data-editor-open') == 1
        assert "New Query Card" in editor
        assert 'name="action" value="create_card"' in editor
        assert 'name="action" value="delete_card"' not in editor
        assert 'name="card_id"' not in editor

    def test_query_page_renders_single_editor_for_editing_selected_card(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = unescape(response.content.decode())
        editor = content.split('<div class="query-card-editor', 1)[1].split("</form>", 1)[0]

        assert content.count('data-query-card-editor data-editor-open') == 1
        assert "Edit Query Card" in editor
        assert 'name="action" value="update_card"' in editor
        assert f'name="card_id" value="{selected.id}"' in editor
        assert 'name="action" value="delete_card"' in editor

    def test_issues_page_renders_saved_views_filters_and_issue_rows(self):
        response = self.client.get(
            reverse("jira_workspace:issues"),
            {"query": "OPS", "project": "OPS", "status": "Blocked"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Saved Views" in content
        assert "Issue Results" in content
        assert "Bulk Actions" in content
        assert "TESS-321" not in content
        assert "OPS-778" in content
        assert "Project" in content
        assert "Status" in content
        assert "Search" in content
        assert 'aria-label="Search issue key or summary"' in content
        assert 'aria-label="Issue source"' in content
        assert 'aria-label="Issue project"' in content
        assert 'aria-label="Issue status"' in content
        assert 'aria-label="Sort issues by"' in content
        assert 'aria-label="Sort issue direction"' in content
        assert 'class="table-wrap table-wrap--ticket-scroll"' in content
        assert 'class="ticket-table ticket-table--dense ticket-table--no-wrap"' in content

    def test_issues_page_can_render_large_local_cache_for_table_testing(self):
        for index in range(30):
            issue = JiraIssue.objects.create(
                issue_key=f"API-{index + 1000}",
                project_key="API",
                summary=f"Generated issue {index}",
                status="Open",
                assignee="xchen17",
                reporter="amy",
                priority="Medium",
                updated_at=datetime.now(timezone.utc) - timedelta(minutes=index),
                created_at=datetime.now(timezone.utc) - timedelta(days=1, minutes=index),
                raw_json="{}",
                last_seen_at=datetime.now(timezone.utc),
            )
            add_policy_membership(
                issue=issue,
                version=self.policy_version,
                scope=self.sync_scope,
            )

        response = self.client.get(reverse("jira_workspace:issues"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "API-1000" in content
        assert "API-1029" in content

    def test_dashboard_table_exposes_stable_rich_table_configuration(self):
        response = self.client.get(reverse("jira_workspace:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-rich-table-id="jira-dashboard-tickets"' in content
        assert 'data-rich-table-persist-scope="/jira/dashboard/"' in content
        assert 'data-rich-table-row-click="drawer"' in content

    def test_query_table_exposes_stable_rich_table_configuration(self):
        selected = JiraSavedQuery.objects.order_by("-is_pinned", "-is_starred", "name").first()

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-rich-table-id="jira-query-results"' in content
        assert f'data-rich-table-persist-scope="/jira/query/card/{selected.id}/"' in content
        assert 'data-rich-table-default-columns="' in content

    def test_query_table_ticket_keys_link_to_jira_browse_url(self):
        JiraConnection.objects.create(
            base_url="https://jirap-cli.corp.ebay.com",
            api_token="token-123",
            auth_type=JiraConnection.AuthType.BEARER,
        )

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-rich-table-ticket-browse-base-url="https://jirap.corp.ebay.com"' in content
        assert 'href="https://jirap.corp.ebay.com/browse/OPS-778"' in content
        assert 'target="_blank"' in content

    def test_query_page_renders_ticket_detail_drawer_for_row_click_details(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-rich-table-row-click="drawer"' in content
        assert 'data-ticket-drawer' in content
        assert 'aria-hidden="true"' in content

    def test_issues_table_exposes_stable_rich_table_configuration(self):
        response = self.client.get(reverse("jira_workspace:issues"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-rich-table-id="jira-issues-results"' in content
        assert 'data-rich-table-persist-scope="/jira/issues/"' in content

    def test_shell_renders_top_tool_switcher_query_cards_and_starred_sections(self):
        WorkspaceStar.objects.create(
            kind=WorkspaceStar.Kind.ROUTE,
            label="Jira Issues",
            route=reverse("jira_workspace:issues"),
            group_key="jira",
        )

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]
        assert 'aria-label="Tool Switcher"' in content
        assert "Workspace" in content.split('aria-label="Tool Switcher"', 1)[1].split("</nav>", 1)[0]
        assert "Jira" in content.split('aria-label="Tool Switcher"', 1)[1].split("</nav>", 1)[0]
        assert "sync2pod" in content.split('aria-label="Tool Switcher"', 1)[1].split("</nav>", 1)[0]
        assert "Integrations" in content.split('aria-label="Tool Switcher"', 1)[1].split("</nav>", 1)[0]
        assert "Logs" in content.split('aria-label="Tool Switcher"', 1)[1].split("</nav>", 1)[0]
        assert 'aria-label="Tools"' not in content
        assert 'aria-label="Current Tool"' not in app_nav
        assert "Query Cards" in app_nav
        assert "Starred" in app_nav
        assert "Jira Issues" in app_nav.split("Starred", 1)[1]

    def test_query_page_renders_jira_secondary_navigation(self):
        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        current_tool_nav = content.split('<nav class="tool-context-nav"', 1)[1].split(
            "</nav>", 1
        )[0]

        assert 'aria-label="Current Tool"' in current_tool_nav
        assert "Dashboard" in current_tool_nav
        assert "Query" in current_tool_nav
        assert "Sync" in current_tool_nav
        assert "Profiles" in current_tool_nav
        query_href = reverse("jira_workspace:query")
        assert (
            f'<a class="tool-context-nav__link active" href="{query_href}"'
            in current_tool_nav
        )
        assert 'aria-current="page"' in current_tool_nav

    def test_query_page_renders_query_card_nav_with_active_card_link(self):
        selected = JiraSavedQuery.objects.get(name="Team Review Queue")

        response = self.client.get(reverse("jira_workspace:query"), {"card": selected.id})

        assert response.status_code == 200
        content = response.content.decode()
        query_card_nav = content.split('aria-label="Jira Query Cards"', 1)[1].split(
            "</nav>", 1
        )[0]

        assert "My Open Blockers" in query_card_nav
        assert "Team Review Queue" in query_card_nav
        query_link = query_card_nav.rsplit(
            '<a class="query-card-nav__item', 1
        )[1].split("</a>", 1)[0]
        assert f'href="{reverse("jira_workspace:query")}?card={selected.id}"' in query_link
        assert "is-active" in query_link

    def test_toggle_star_route_adds_and_removes_starred_page_entry(self):
        response = self.client.post(
            reverse("jira_workspace:toggle_star"),
            {
                "kind": WorkspaceStar.Kind.ROUTE,
                "label": "Jira Issues",
                "route": reverse("jira_workspace:issues"),
                "group_key": "jira",
                "next": reverse("jira_workspace:issues"),
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"] == reverse("jira_workspace:issues")
        assert WorkspaceStar.objects.filter(label="Jira Issues").exists()

        self.client.post(
            reverse("jira_workspace:toggle_star"),
            {
                "kind": WorkspaceStar.Kind.ROUTE,
                "label": "Jira Issues",
                "route": reverse("jira_workspace:issues"),
                "group_key": "jira",
                "next": reverse("jira_workspace:issues"),
            },
        )

        assert WorkspaceStar.objects.filter(label="Jira Issues").exists() is False

    def test_issues_page_uses_floating_drawer_instead_of_default_detail_sidebar(self):
        response = self.client.get(
            reverse("jira_workspace:issues"),
            {"issue": "OPS-778"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Issue Detail" not in content
        assert 'data-ticket-drawer' in content
        assert 'data-ticket-row' in content
        assert 'data-ticket-key="OPS-778"' in content
        assert 'data-ticket-sprint="Sprint 42"' in content
        assert "Escalate blocker handling" in content

    def test_sync_page_renders_command_center_summary_sections(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Current Profile" in content
        assert "Latest Status" in content
        assert "Recent Runs Summary" in content
        assert "Recent Logs Summary" in content
        assert "Details" in content
        assert "Run History" in content
        assert "Profile Editor" in content
        assert "Sync Run Timeline" not in content
        assert "Run Configuration Presets" not in content

    def test_sync_page_applies_command_center_layout_classes_to_rendered_panels(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="panel sync-card sync-card--profile"' in content
        assert 'class="panel panel--tight sync-card sync-card--controls"' in content
        assert 'class="panel sync-card sync-card--status"' in content
        assert 'class="panel panel--tight sync-card sync-card--runs"' in content
        assert 'class="panel panel--tight sync-card sync-card--logs"' in content
        assert 'class="panel sync-details"' in content
        assert 'class="panel__header sync-details__header"' in content
        details_panel_tags = re.findall(r"<section[^>]+data-sync-details-panel=\"[^\"]+\"[^>]*>", content)
        assert details_panel_tags
        for panel_tag in details_panel_tags:
            assert "sync-details__panel" in panel_tag

    def test_sync_page_renders_global_policy_status_and_scope_cards(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Global Sync Policy" in content
        assert "Current Policy Version" in content
        assert "Required Scopes" in content
        assert "Run Due Scopes" in content
        assert "My Assigned or Reported Issues" in content

    def test_sync_post_can_rebuild_current_version(self):
        policy = GlobalSyncPolicy.objects.get(name="Primary Jira Policy")
        before_version_count = policy.versions.count()

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {"action": "rebuild_policy", "policy_id": str(policy.id)},
        )

        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.status == GlobalSyncPolicy.Status.STALE
        assert policy.versions.count() == before_version_count + 1

    @patch("jira_workspace.views.SyncService.run_scope_incremental")
    def test_sync_post_can_run_scope_incremental(self, run_scope_incremental):
        scope = self.sync_scope

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {"action": "run_scope_incremental", "scope_id": str(scope.id)},
        )

        assert response.status_code == 302
        run_scope_incremental.assert_called_once()
        assert run_scope_incremental.call_args.args[0] == scope

    @patch("jira_workspace.views.SyncService.run_scope_full")
    def test_sync_post_can_run_scope_full(self, run_scope_full):
        scope = self.sync_scope

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {"action": "run_scope_full", "scope_id": str(scope.id)},
        )

        assert response.status_code == 302
        run_scope_full.assert_called_once()
        assert run_scope_full.call_args.args[0] == scope

    @patch("jira_workspace.views.SyncService.run_due_scopes")
    def test_sync_post_can_run_due_scopes(self, run_due_scopes):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {"action": "run_due_scopes"},
        )

        assert response.status_code == 302
        run_due_scopes.assert_called_once()

    def test_sync_page_renders_scope_sync_reports(self):
        JiraScopeSyncReport.objects.create(
            policy_version=self.policy_version,
            scope=self.sync_scope,
            run_type=JiraScopeSyncReport.RunType.FULL,
            status=JiraScopeSyncReport.Status.SUCCESS,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            effective_jql=self.sync_scope.base_jql,
            fetched_count=3,
            inserted_count=1,
            updated_count=1,
            unchanged_checked_count=1,
            deactivated_membership_count=2,
            duration_ms=123,
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Scope Sync Reports" in content
        assert "My Assigned or Reported Issues" in content
        assert "Deactivated" in content
        assert "123ms" in content

    def test_sync_page_renders_policy_editor_and_scope_form(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Policy Editor" in content
        assert 'name="action" value="save_policy"' in content
        assert 'name="action" value="add_scope"' in content
        assert 'name="scope_type"' in content
        assert "Add Scope" in content

    def test_sync_post_can_save_global_policy(self):
        policy = GlobalSyncPolicy.objects.get(name="Primary Jira Policy")

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "save_policy",
                "policy_id": str(policy.id),
                "name": "Primary Jira Policy Renamed",
            },
        )

        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.name == "Primary Jira Policy Renamed"

    def test_sync_post_can_add_policy_scope_and_create_new_version(self):
        policy = GlobalSyncPolicy.objects.get(name="Primary Jira Policy")
        before_version_count = policy.versions.count()

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "add_scope",
                "policy_id": str(policy.id),
                "scope_type": SyncScope.ScopeType.PROJECT,
                "name": "OPS Project",
                "schedule_minutes": "45",
                "project_key": "OPS",
            },
        )

        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.versions.count() == before_version_count + 1
        assert policy.current_version.scopes.filter(
            scope_type=SyncScope.ScopeType.PROJECT,
            name="OPS Project",
            config_json__project_key="OPS",
        ).exists()

    def test_sync_page_collapses_details_by_default(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-sync-details-toggle' in content
        assert 'data-sync-details-panel="history"' in content
        assert 'data-sync-details-panel="profile"' in content
        history_open_tag = content.split('data-sync-details-panel="history"', 1)[1].split(">", 1)[0]
        profile_open_tag = content.split('data-sync-details-panel="profile"', 1)[1].split(">", 1)[0]
        assert "hidden" in history_open_tag
        assert "hidden" in profile_open_tag

    def test_sync_page_renders_compact_recent_run_summary_rows(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-sync-summary-runs' in content
        assert 'data-sync-summary-run-item' in content
        assert "Recent Sync Runs" in content

    def test_sync_page_keeps_full_run_history_table_inside_details(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        details_region = content.split('data-sync-details-panel="history"', 1)[1]
        assert "<th scope=\"col\">Log</th>" in details_region
        assert "Recent Sync Runs" in content

    def test_sync_page_renders_profiles_runs_and_blocker_state(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Current Profile" in content
        assert "Recent Runs Summary" in content
        assert "My Issues" in content
        assert "success" in content.lower()
        assert "The request is blocked." in content
        assert "External Jira access is currently blocked" in content
        assert "Profile Editor" in content
        assert "Sync Controls" in content
        main_content = content.split('<main class="app-main">', 1)[1].split("</main>", 1)[0]
        assert "Jira Connection" not in main_content
        assert "Save connection" not in main_content
        assert "Jira Connection" in content
        assert "Save connection" in content

    def test_sync_page_renders_failed_run_log_in_recent_runs_table(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.FAILED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            error_message="JIRA_API_BASE_URL and JIRA_API_TOKEN are required.",
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "<th scope=\"col\">Log</th>" in content
        assert "JIRA_API_BASE_URL and JIRA_API_TOKEN are required." in content

    def test_sync_page_can_persist_a_profile(self):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "save_profile",
                "name": "OPS Project",
                "profile_type": JiraSyncProfile.ProfileType.PROJECT,
                "project_key": "OPS",
                "is_default": "on",
            },
        )

        assert response.status_code == 302
        profile = JiraSyncProfile.objects.get(name="OPS Project")
        assert profile.profile_type == JiraSyncProfile.ProfileType.PROJECT
        assert profile.params_json == {"project_key": "OPS"}
        assert profile.is_default is True

    def test_sync_page_can_save_jira_connection_settings(self):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "save_connection",
                "base_url": "https://jira.example.com/",
                "auth_type": JiraConnection.AuthType.BASIC,
                "user_email": "xchen17@example.com",
                "api_token": "token-123",
            },
        )

        assert response.status_code == 302
        connection = JiraConnection.objects.get()
        assert connection.base_url == "https://jira.example.com"
        assert connection.auth_type == JiraConnection.AuthType.BASIC
        assert connection.user_email == "xchen17@example.com"
        assert connection.api_token == "token-123"

    def test_jira_connection_settings_returns_to_safe_next_url(self):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "save_connection",
                "next": reverse("jira_workspace:query"),
                "base_url": "https://jira.example.com/",
                "auth_type": JiraConnection.AuthType.BEARER,
                "api_token": "token-123",
            },
        )

        assert response.status_code == 302
        assert response["Location"] == reverse("jira_workspace:query")

    @patch("jira_workspace.views.JiraConnectionService.test_connection")
    def test_sync_page_can_test_jira_connection(self, test_connection):
        connection = JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token-123",
            auth_type=JiraConnection.AuthType.BEARER,
        )
        test_connection.return_value = connection

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "test_connection",
                "connection_id": str(connection.id),
            },
        )

        assert response.status_code == 302
        test_connection.assert_called_once_with(connection)

    def test_settings_drawer_contains_jira_connection_controls(self):
        JiraConnection.objects.create(
            base_url="https://jira.example.com",
            api_token="token-123",
            auth_type=JiraConnection.AuthType.BEARER,
            last_check_status=JiraConnection.CheckStatus.UNKNOWN,
        )

        response = self.client.get(reverse("jira_workspace:query"))

        assert response.status_code == 200
        content = response.content.decode()
        drawer = content.split('id="workspace-settings-drawer"', 1)[1]
        assert "Jira Connection" in drawer
        assert 'name="base_url"' in drawer
        assert 'name="api_token"' in drawer
        assert "Save connection" in drawer
        assert "Test connection" in drawer

    @patch("jira_workspace.views.SyncService.enqueue_sync")
    def test_sync_page_queues_incremental_sync(self, enqueue_sync):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.INCREMENTAL,
            },
        )

        assert response.status_code == 302
        enqueue_sync.assert_called_once()
        assert enqueue_sync.call_args.args[0] == self.profile
        assert enqueue_sync.call_args.args[1] == JiraSyncRun.RunType.INCREMENTAL

    @patch("jira_workspace.views.SyncService.enqueue_sync")
    def test_sync_page_queues_full_sync(self, enqueue_sync):
        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.FULL,
            },
        )

        assert response.status_code == 302
        enqueue_sync.assert_called_once()
        assert enqueue_sync.call_args.args[0] == self.profile
        assert enqueue_sync.call_args.args[1] == JiraSyncRun.RunType.FULL

    @patch("jira_workspace.views.SyncService.enqueue_sync")
    def test_sync_page_shows_error_when_full_run_blocks_new_enqueue(self, enqueue_sync):
        enqueue_sync.side_effect = ActiveFullSyncError(
            "A Jira full sync is already queued or running. "
            "Wait for it to finish before starting another Jira sync task."
        )

        response = self.client.post(
            reverse("jira_workspace:sync"),
            {
                "action": "run_sync",
                "profile_id": str(self.profile.id),
                "run_type": JiraSyncRun.RunType.INCREMENTAL,
            },
            follow=True,
        )

        assert response.status_code == 200
        assert "A Jira full sync is already queued or running." in response.content.decode()

    def test_sync_page_keeps_run_buttons_enabled_when_full_run_is_active(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            progress_message="Fetched 10 of 20 issues.",
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        incremental_button = content.split('name="run_type" value="incremental"', 1)[1].split(">", 1)[0]
        full_button = content.split('name="run_type" value="full"', 1)[1].split(">", 1)[0]
        assert "disabled" not in incremental_button
        assert "disabled" not in full_button
        assert "A Jira full sync is already queued or running." in content

    def test_sync_page_renders_running_progress(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            fetched_count=40,
            progress_current_count=40,
            progress_total_count=100,
            progress_message="Fetched 40 of 100 issues.",
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-sync-refresh="active"' in content
        assert "Fetched 40 of 100 issues." in content
        assert 'aria-valuenow="40"' in content

    def test_sync_page_renders_running_progress_inside_latest_status(self):
        JiraSyncRun.objects.create(
            profile=self.profile,
            run_type=JiraSyncRun.RunType.FULL,
            status=JiraSyncRun.Status.RUNNING,
            started_at=datetime.now(timezone.utc),
            fetched_count=40,
            progress_current_count=40,
            progress_total_count=100,
            progress_message="Fetched 40 of 100 issues.",
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Latest Status" in content
        latest_status_block = content.split("Latest Status", 1)[1].split("Recent Runs Summary", 1)[0]
        assert "Fetched 40 of 100 issues." in latest_status_block
        assert 'aria-valuenow="40"' in latest_status_block

    def test_sync_page_keeps_recent_logs_summary_links(self):
        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Recent Logs Summary" in content
        assert "/jira/logs/" in content

    def test_sync_page_renders_recent_operation_logs(self):
        OperationLog.objects.create(
            tool=OperationLog.Tool.JIRA_SYNC,
            action=JiraSyncRun.RunType.FULL,
            status=OperationLog.Status.FAILED,
            title="My Issues full",
            triggered_by="xchen17",
            target_type="jira_sync_profile",
            target_id=str(self.profile.id),
            error_message="Jira returned 403",
            log_text="sync failed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(reverse("jira_workspace:sync"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Recent Logs" in content
        assert "My Issues full" in content


class JiraWorkspaceNavigationTests(TestCase):
    def test_all_primary_pages_return_ok(self):
        for name in ["dashboard", "query", "issues", "sync"]:
            response = self.client.get(reverse(f"jira_workspace:{name}"))
            assert response.status_code == 200

    def test_workspace_shell_routes_render(self):
        route_expectations = [
            ("/workspace/", "Workspace"),
            (reverse("jira_workspace:query"), "Jira Dashboard"),
            (reverse("jira_workspace:issues"), "Jira Issues"),
            (reverse("jira_workspace:sync"), "Jira Sync"),
            (reverse("jira_workspace:logs"), "Operation Logs"),
            ("/sync2pod/", "sync2pod"),
            ("/integrations/", "Integrations"),
        ]

        for route_path, title_text in route_expectations:
            response = self.client.get(route_path)
            assert response.status_code == 200
            content = response.content.decode()
            assert "mtools" in content
            assert title_text in content

    def test_legacy_queries_and_profiles_routes_redirect_to_new_pages(self):
        route_expectations = [
            (reverse("jira_workspace:queries"), reverse("jira_workspace:query")),
            (reverse("jira_workspace:profiles"), reverse("jira_workspace:sync")),
        ]

        for old_route, new_route in route_expectations:
            response = self.client.get(old_route)
            assert response.status_code == 302
            assert response.headers["Location"] == new_route

    def test_root_redirects_to_workspace_home(self):
        response = self.client.get("/")

        assert response.status_code == 302
        assert response.headers["Location"] == "/workspace/"

    def test_workspace_home_renders_cross_tool_summary_cards_and_activity(self):
        jira_profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql="assignee = currentUser() ORDER BY updated DESC",
        )
        JiraSyncRun.objects.create(
            profile=jira_profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            status=JiraSyncRun.Status.SUCCESS,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=19),
            fetched_count=4,
            inserted_count=1,
            updated_count=2,
            skipped_count=1,
        )
        sync2pod_profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        Sync2PodRun.objects.create(
            profile=sync2pod_profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=127,
            error_message="sync2pod command is not available on this host.",
        )
        Sync2PodWatchEvent.objects.create(
            profile=sync2pod_profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued after edit",
        )
        tool = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into pods.",
        )
        IntegrationScanRun.objects.create(
            tool=tool,
            status=IntegrationScanRun.Status.SUCCESS,
            summary="catalog refresh completed",
        )

        response = self.client.get("/workspace/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Workspace Overview" in content
        assert "Jira Sync Runs" in content
        assert "sync2pod Queue" in content
        assert "Integration Scans" in content
        assert "Cross-Tool Activity" in content
        assert "catalog refresh completed" in content
        assert "sync2pod command is not available on this host." in content

    def test_workspace_shell_exposes_logs_tool(self):
        response = self.client.get("/workspace/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Logs" in content
        assert "/logs/" in content

    def test_logs_page_lists_operation_logs_and_filters(self):
        failed_log = OperationLog.objects.create(
            tool=OperationLog.Tool.JIRA_QUERY,
            action="run_card",
            status=OperationLog.Status.FAILED,
            title="Assigned to me",
            triggered_by="xchen17",
            error_message="query failed",
            log_text="trace",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        OperationLog.objects.create(
            tool=OperationLog.Tool.SYNC2POD,
            action="start_sync",
            status=OperationLog.Status.SUCCESS,
            title="Primary Pod",
            triggered_by="xchen17",
            result_summary="Exit code 0",
            log_text="stdout",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(
            reverse("jira_workspace:logs"),
            {"tool": OperationLog.Tool.JIRA_QUERY, "status": OperationLog.Status.FAILED},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Operation Logs" in content
        assert "Assigned to me" in content
        assert "Primary Pod" not in content
        assert reverse("jira_workspace:log_detail", args=[failed_log.id]) in content

    def test_log_detail_page_renders_full_log_body(self):
        log = OperationLog.objects.create(
            tool=OperationLog.Tool.JIRA_SYNC,
            action=JiraSyncRun.RunType.FULL,
            status=OperationLog.Status.SUCCESS,
            title="OPS Sync",
            triggered_by="xchen17",
            result_summary="Fetched 4 issues",
            log_text="effective_jql=project = OPS",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(reverse("jira_workspace:log_detail", args=[log.id]))

        assert response.status_code == 200
        content = response.content.decode()
        assert "OPS Sync" in content
        assert "Fetched 4 issues" in content
        assert "effective_jql=project = OPS" in content


class Sync2PodViewTests(TestCase):
    def test_sync2pod_page_renders_persisted_profiles_runs_and_queue_state(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            config_path="/tmp/sync2pod.yaml",
            command="sync2pod",
            extra_args="--delete",
        )
        Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.SUCCESS,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push --delete",
            exit_code=0,
            stdout_log="synced 4 files",
        )
        Sync2PodWatchEvent.objects.create(
            profile=profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued after edit",
        )

        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Sync2pod Profiles" in content
        assert "Recent Runs" in content
        assert "Queued Watch Events" in content
        assert "Primary Pod" in content
        assert "pod-a" in content
        assert "synced 4 files" in content
        assert "src/module.py" in content
        assert "Project Configuration Manager" in content
        assert "Sync Strategy Panel" in content
        assert "Execution Console" in content
        assert "Watch Mode" in content
        assert "Archive / Chunk Upload Insights" in content
        assert "Safety / Validation Strip" in content
        assert 'autocomplete="off"' in content

    def test_sync2pod_page_renders_actionable_failure_state(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=127,
            error_message="sync2pod command is not available on this host.",
        )

        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Action Required" in content
        assert "sync2pod command is not available on this host." in content

    def test_sync2pod_page_uses_shared_commercial_surfaces(self):
        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="workspace-panel tool-surface"' in content
        assert 'class="tool-status-strip"' in content

    def test_sync2pod_post_can_persist_a_profile(self):
        response = self.client.post(
            reverse("jira_workspace:sync2pod"),
            {
                "action": "save_profile",
                "name": "Primary Pod",
                "pod_name": "pod-a",
                "namespace": "sync",
                "watch_path": "/tmp/watch",
                "config_path": "/tmp/sync2pod.yaml",
                "command": "true",
                "extra_args": "--delete",
                "is_enabled": "on",
            },
        )

        assert response.status_code == 302
        profile = Sync2PodProfile.objects.get(name="Primary Pod")
        assert profile.command == "true"
        assert profile.extra_args == "--delete"

    def test_sync2pod_post_can_start_a_sync_run(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            config_path="/tmp/sync2pod.yaml",
            command="true",
            extra_args="--delete",
        )

        response = self.client.post(
            reverse("jira_workspace:sync2pod"),
            {
                "action": "start_sync",
                "profile_id": str(profile.id),
            },
        )

        assert response.status_code == 302
        run = Sync2PodRun.objects.latest("started_at")
        assert run.profile == profile
        assert run.status == Sync2PodRun.Status.SUCCESS

    def test_sync2pod_page_renders_recent_operation_logs(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="true",
        )
        OperationLog.objects.create(
            tool=OperationLog.Tool.SYNC2POD,
            action="start_sync",
            status=OperationLog.Status.SUCCESS,
            title="Primary Pod",
            triggered_by="xchen17",
            target_type="sync2pod_profile",
            target_id=str(profile.id),
            result_summary="Exit code 0",
            log_text="stdout=synced 4 files",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(reverse("jira_workspace:sync2pod"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Recent Logs" in content
        assert "Primary Pod" in content


class IntegrationsViewTests(TestCase):
    def setUp(self):
        jira_sync = IntegrationTool.objects.create(
            key="jira-sync",
            name="Jira Sync",
            group="Issue Ops",
            readiness=IntegrationTool.Readiness.READY,
            description="Refreshes cached Jira issues.",
        )
        IntegrationContract.objects.create(
            tool=jira_sync,
            input_contract="profile + JQL",
            output_contract="issue cache rows",
            event_contract="sync runs",
            notes="Stable contract surface.",
        )
        sync2pod = IntegrationTool.objects.create(
            key="sync2pod",
            name="sync2pod",
            group="Sync Ops",
            readiness=IntegrationTool.Readiness.BETA,
            description="Push local files into pods.",
        )
        IntegrationContract.objects.create(
            tool=sync2pod,
            input_contract="watch path + pod target",
            output_contract="transfer summary",
            event_contract="",
            notes="Event stream not wired yet.",
        )
        IntegrationScanRun.objects.create(
            tool=sync2pod,
            status=IntegrationScanRun.Status.FAILED,
            summary="catalog refresh stalled on sync2pod metadata",
            error_message="event stream contract missing",
        )

    def test_integrations_page_renders_catalog_matrix_and_recent_activity(self):
        response = self.client.get(reverse("jira_workspace:integrations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Tool Catalog by Type" in content
        assert "Contract Surface Matrix" in content
        assert "Recent Scan Activity" in content
        assert "Issue Ops" in content
        assert "Jira Sync" in content
        assert "sync2pod" in content
        assert "event stream contract missing" in content
        assert "events" in content

    def test_integrations_page_uses_shared_commercial_surfaces(self):
        response = self.client.get(reverse("jira_workspace:integrations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="workspace-panel tool-surface"' in content
        assert 'class="tool-status-strip"' in content

    def test_integrations_page_filters_catalog_by_query(self):
        response = self.client.get(reverse("jira_workspace:integrations"), {"query": "pod"})

        assert response.status_code == 200
        content = response.content.decode()
        assert "sync2pod" in content
        assert "Push local files into pods." in content
        assert "Refreshes cached Jira issues." not in content

    def test_integrations_post_runs_catalog_scan_and_creates_operation_log(self):
        sync2pod = IntegrationTool.objects.get(key="sync2pod")

        response = self.client.post(
            reverse("jira_workspace:integrations"),
            {"action": "run_scan", "tool_id": str(sync2pod.id)},
        )

        assert response.status_code == 302
        log = OperationLog.objects.get(
            tool=OperationLog.Tool.INTEGRATIONS,
            action="run_scan",
        )
        assert log.title == "sync2pod"
        assert log.status == OperationLog.Status.SUCCESS

    def test_integrations_page_renders_recent_operation_logs(self):
        sync2pod = IntegrationTool.objects.get(key="sync2pod")
        OperationLog.objects.create(
            tool=OperationLog.Tool.INTEGRATIONS,
            action="run_scan",
            status=OperationLog.Status.SUCCESS,
            title="sync2pod",
            triggered_by="xchen17",
            target_type="integration_tool",
            target_id=str(sync2pod.id),
            result_summary="events missing",
            log_text="scan completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        response = self.client.get(reverse("jira_workspace:integrations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Recent Logs" in content
        assert "sync2pod" in content


class JiraWorkspaceStylesheetTests(TestCase):
    def test_shared_stylesheet_includes_toolbar_and_form_layout_hooks(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        for selector in [
            ".toolbar",
            ".toolbar--actions",
            ".toolbar__search",
            ".form-grid",
            ".checkbox-row",
            ".data-table",
            ".meta-inline",
            ".group-stack",
        ]:
            assert selector in css

    def test_sync_run_log_column_wraps_long_error_messages(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ".sync-run-log {" in css
        assert "overflow-wrap: anywhere;" in css

    def test_topbar_uses_compact_global_toolbar_treatment(self):
        topbar_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/topbar.html"
        ).read_text()
        nav_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_nav.html"
        ).read_text()
        base_template = Path(settings.BASE_DIR / "templates/jira_workspace/base.html").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert 'rel="icon" href="data:,"' in base_template
        assert base_template.index('{% include "jira_workspace/partials/topbar.html" %}') < base_template.index('{% include "jira_workspace/partials/app_nav.html" %}')
        assert '<main class="app-main">\n      {% include "jira_workspace/partials/topbar.html" %}' not in base_template
        assert 'class="workspace-breadcrumb"' not in base_template
        assert 'name="workspace_search"' not in topbar_template
        assert "Workspace search" not in topbar_template
        assert 'class="workspace-topbar__spacer"' in topbar_template
        assert 'data-nav-toggle' in topbar_template
        assert 'class="workspace-tool-name"' in topbar_template
        assert 'class="app-brand"' not in nav_template
        assert 'class="workspace-topbar workspace-topbar--compact"' in topbar_template
        assert ".workspace-topbar--compact" in css
        assert ".workspace-topbar__primary" in css
        assert ".workspace-topbar__spacer" in css
        assert ".workspace-nav-toggle" in css
        assert ".workspace-command" not in css
        assert "min-height: 42px;" in css
        assert "box-shadow: none;" in css
        assert "height: 30px;" in css
        assert "@media (max-width: 520px)" in css
        assert ".workspace-topbar,\n  .page-header" not in css

    def test_shell_uses_low_noise_commercial_navigation(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        nav_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_nav.html"
        ).read_text()
        topbar_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/topbar.html"
        ).read_text()

        assert "app-nav--commercial" in nav_template
        assert "nav-section-label" in nav_template
        assert "nav-link__hint" in nav_template
        assert "data-shell-health-summary" not in nav_template
        assert "Jira Query Cards" in nav_template
        assert ".app-nav--commercial" in css
        assert ".nav-link__hint" in css
        assert ".shell-health-summary" not in css
        assert ".workspace-topbar__actions" in css
        assert 'class="workspace-topbar__actions"' in topbar_template

    def test_shell_sidebar_width_is_user_resizable_and_persisted(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        nav_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_nav.html"
        ).read_text()

        assert 'data-sidebar-resize-handle' in nav_template
        assert "--app-nav-width: 236px;" in css
        assert "grid-template-columns: var(--app-nav-width) minmax(0, 1fr);" in css
        assert ".app-nav__resize-handle" in css
        assert "cursor: col-resize;" in css
        assert "mtools.nav.width" in js
        assert "function initializeSidebarResize()" in js
        assert "data-sidebar-resize-handle" in js
        assert "pointermove" in js
        assert "setProperty(\"--app-nav-width\"" in js

    def test_stylesheet_uses_agentsview_compact_typography_density(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert (
            "body.workspace-body {\n"
            "  margin: 0;\n"
            '  font-family: "IBM Plex Sans", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n'
            "  font-size: 13px;\n"
            "  line-height: 1.5;"
        ) in css
        assert ".page-title {\n  font-size: 24px;" in css
        assert ".section-title {\n  font-size: 15px;" in css
        assert ".page-subtitle {\n  margin: 4px 0 0;" in css
        assert "padding: 9px 8px;" in css
        assert ".ticket-table--dense th,\n.ticket-table--dense td {\n  padding: 7px 8px;" in css
        assert ".tabulator .tabulator-cell {\n  border-color: var(--border);\n  line-height: 1.35;" in css

    def test_stylesheet_exposes_commercial_ui_primitives(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "--radius-control: 7px;" in css
        assert "--radius-panel: 8px;" in css
        assert "--space-panel: 12px;" in css
        assert "--shadow-raised: 0 10px 28px" in css
        assert ".workspace-surface" in css
        assert ".workspace-control" in css
        assert ".workspace-panel" in css
        assert ".workspace-density-compact" in css

    def test_query_card_editor_javascript_hooks_are_present(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert "function openQueryCardEditor" in js
        assert "function closeQueryCardEditor" in js
        assert "function initializeQueryCardColumnEditors" in js
        assert "function syncQueryCardColumnOrder" in js
        assert "data-query-card-editor" in js
        assert "data-query-card-editor-open" in js
        assert "data-query-card-editor-close" in js
        assert "data-query-card-column-editor" in js
        assert "data-column-move" in js
        assert "closeTicketDrawer();" in js
        assert "closeQueryCardEditor();" in js

    def test_stylesheet_includes_compact_dashboard_layout_hooks(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ".page-section--dashboard {\n  gap: 10px;" in css
        assert ".dashboard-controlbar" in css
        assert ".dashboard-range" in css
        assert ".page-section--dashboard .workspace-card-grid--compact {\n  grid-template-columns: repeat(4, minmax(0, 1fr));" in css
        assert ".page-section--dashboard .workspace-card {\n  border-radius: var(--radius-panel);\n  padding: 10px 12px;" in css
        assert ".dashboard-main {\n  padding: 12px;" in css

    def test_shell_styles_place_status_rail_below_workspace_columns(self):
        rail_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_rail.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert '<aside class="app-rail" aria-label="Service Status">' in rail_template
        assert rail_template.strip().endswith("</aside>")
        assert "</aside>\naside" not in rail_template
        assert "height: 100vh;" in css
        assert "overflow: hidden;" in css
        assert "grid-template-columns: var(--app-nav-width) minmax(0, 1fr);" in css
        assert "grid-template-rows: auto minmax(0, 1fr) auto;" in css
        assert '"topbar topbar"' in css
        assert '"nav main"' in css
        assert '"rail main"' in css
        assert "align-self: start;" in css
        assert "grid-column: 1;" in css
        assert "grid-row: 3;" in css
        assert "align-self: end;" in css
        assert "grid-template-columns: 1fr;" in css

    def test_shell_status_rail_merges_activity_and_health_with_collapsed_icons(self):
        rail_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_rail.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "Service Status" in rail_template
        assert "Activity" not in rail_template
        assert "Health" not in rail_template
        assert "rail-item__icon" in rail_template
        assert "rail-item__status" in rail_template
        assert 'data-rail-status="{{ item.status }}"' in rail_template
        assert "body.nav-collapsed .rail-item__body" in css
        assert "body.nav-collapsed .rail-item__icon" in css
        assert "border-top: 1px solid var(--border);" in css
        assert "border-right: 1px solid var(--border);" in css

    def test_shell_assets_include_collapsible_nav_hooks(self):
        nav_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/app_nav.html"
        ).read_text()
        topbar_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/topbar.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert 'data-nav-toggle' in topbar_template
        assert 'data-nav-toggle' not in nav_template
        assert 'data-app-nav' in nav_template
        assert "nav-link__label" in nav_template
        assert "nav-collapsed" in css
        assert "function initializeNavCollapse()" in js
        assert "mtools.nav.collapsed" in js
        assert "data-nav-toggle" in js

    def test_shell_assets_include_system_light_dark_theme_switcher(self):
        topbar_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/topbar.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert 'data-theme-toggle' in topbar_template
        assert 'data-theme-icon' in topbar_template
        assert '<svg' in topbar_template
        assert 'data-theme-label' in topbar_template
        assert 'aria-label="Theme: System"' in topbar_template
        assert 'data-theme-select' not in topbar_template
        assert '<option value="system">System</option>' not in topbar_template
        assert '[data-theme="light"]' in css
        assert '[data-theme="dark"]' in css
        assert "@media (prefers-color-scheme: light)" in css
        assert "function initializeThemeSwitcher()" in js
        assert "function nextThemeMode" in js
        assert "function themeIconMarkup" in js
        assert "icon.innerHTML" in js
        assert "<svg" in js
        assert '["system", "light", "dark"]' in js
        assert "mtools.theme.mode" in js
        assert "matchMedia(\"(prefers-color-scheme: dark)\")" in js
        assert "data-resolved-theme" in js
        assert "data-theme-toggle" in js

    def test_shell_assets_include_global_settings_drawer_with_tool_overrides(self):
        base_template = Path(settings.BASE_DIR / "templates/jira_workspace/base.html").read_text()
        topbar_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/topbar.html"
        ).read_text()
        drawer_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/settings_drawer.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert 'data-settings-open' in topbar_template
        assert 'aria-controls="workspace-settings-drawer"' in topbar_template
        assert '{% include "jira_workspace/partials/settings_drawer.html" %}' in base_template
        assert 'id="workspace-settings-drawer"' in drawer_template
        assert 'data-settings-drawer' in drawer_template
        assert 'data-settings-form' in drawer_template
        assert 'data-setting-scope="global"' in drawer_template
        assert 'data-tool-settings="jira"' in drawer_template
        assert 'data-tool-settings="sync2pod"' in drawer_template
        assert 'data-tool-settings="integrations"' in drawer_template
        assert 'data-tool-override="jira"' in drawer_template
        assert 'data-tool-override="sync2pod"' in drawer_template
        assert 'data-tool-override="integrations"' in drawer_template
        assert ".settings-drawer" in css
        assert ".workspace-settings-button" in css
        assert "function initializeSettingsDrawer()" in js
        assert "mtools.settings.v1" in js
        assert "data-settings-open" in js
        assert "data-settings-close" in js
        assert "data-tool-override" in js

    def test_rich_table_uses_tabulator_assets_and_hooks(self):
        base_template = Path(settings.BASE_DIR / "templates/jira_workspace/base.html").read_text()
        table_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/ticket_table.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert "tabulator-tables@6.4.0" in base_template
        assert "tabulator_midnight.min.css" in base_template
        assert "tabulator.min.js" in base_template
        assert "data-rich-table" in table_template
        assert 'data-rich-table-type="tickets"' in table_template
        assert "initializeRichTables" in js
        assert "new Tabulator" in js
        assert ".tabulator" in css

    def test_rich_table_assets_include_persistence_and_column_menu_hooks(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert "function initializeRichTable(container, options)" in js
        assert "function buildRichTableStorageKey(container)" in js
        assert "function buildTicketColumns(container)" in js
        assert "function ticketKeyLinkFormatter(container)" in js
        assert 'formatter: ticketKeyLinkFormatter(container)' in js
        assert 'event.target.closest(".ticket-key-link")' in js
        assert "function readRichTableDefaultColumns(container)" in js
        assert "function applyRichTableDefaultColumns(container, columns)" in js
        assert "var TICKET_COLUMN_WIDTHS" in js
        assert "initialWidth" not in js
        assert "function renderRichTableToolbar(container, table)" in js
        assert "data-rich-table-toolbar" in js
        assert "data-rich-table-search" in js
        assert "search.autocomplete = \"off\"" in js
        assert "data-rich-table-properties" in js
        assert "function applyRichTableSearch(table, query)" in js
        assert "function labelRichTableControls(container)" in js
        assert 'setAttribute("name", "page_size")' in js
        assert 'label.className = "sr-only"' in js
        assert 'label.setAttribute("for", pageSize.id)' in js
        assert 'label.classList.add("sr-only")' in js
        assert 'headerFilter: "input"' not in js
        assert "headerMenu:" not in js
        assert "persistence:" in js
        assert "localStorage" in js

    def test_rich_table_assets_include_notion_inspired_property_formatters(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "function makeTicketToken" in js
        assert "function ticketTokenFormatter" in js
        assert 'formatter: ticketTokenFormatter("project")' in js
        assert 'formatter: ticketTokenFormatter("status")' in js
        assert 'formatter: ticketTokenFormatter("priority")' in js
        assert ".rich-table-toolbar" in css
        assert ".rich-table-search input" in css
        assert ".ticket-token" in css
        assert ".ticket-token--status-blocked" in css
        assert ".ticket-token--priority-highest" in css

    def test_rich_table_supports_view_tabs_density_and_row_actions(self):
        table_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/ticket_table.html"
        ).read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert 'data-rich-table-views="tickets"' in table_template
        assert "function renderRichTableViewTabs(container, table)" in js
        assert "function setRichTableDensity(table, density)" in js
        assert "function renderTicketRowActions" in js
        assert "data-ticket-copy-key" in js
        assert ".rich-table-view-tabs" in css
        assert ".rich-table-row-actions" in css
        assert ".tabulator-row:hover .rich-table-row-actions" in css

    def test_rich_table_header_groups_title_views_and_actions_on_one_responsive_row(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "function ensureRichTableHeader(parent, container)" in js
        assert 'header.className = "rich-table-header"' in js
        assert 'header.setAttribute("data-rich-table-header", "true")' in js
        assert 'header.appendChild(heading)' in js
        assert 'toolbarLeft.insertBefore(tabs, toolbarLeft.firstChild)' in js
        assert 'header.appendChild(toolbar)' in js
        assert ".rich-table-header" in css
        assert "flex-wrap: wrap;" in css
        assert ".rich-table-heading {\n  flex: 1 0 100%;" in css
        assert ".rich-table-heading" in css
        assert ".rich-table-toolbar {\n  position: relative;\n  display: flex;" in css

    def test_query_card_rule_uses_compact_single_line_layout(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ".query-card-rule {\n  display: flex;" in css
        assert "min-height: 38px;" in css
        assert ".query-card-rule__meta {\n  display: inline-flex;" in css
        assert ".query-card-rule code {\n  flex: 1 1 auto;" in css

    def test_query_card_summary_metrics_use_compact_strip(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "grid-template-rows: auto auto auto minmax(0, 1fr);" in css
        assert ".query-card-summary-strip {\n  grid-template-columns: repeat(5, minmax(0, 1fr));\n  align-items: start;" in css
        assert ".rich-table-heading .query-card-summary-strip" in css
        assert ".query-card-summary {\n  display: flex;" in css
        assert "min-height: 210px;" not in css

    def test_query_results_summary_adapts_inside_responsive_header(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "@media (max-width: 1100px)" in css
        assert ".rich-table-heading .query-card-summary-strip {\n    order: 3;\n    flex: 1 0 100%;" in css
        assert "grid-auto-flow: column;" in css
        assert "grid-template-columns: none;" in css
        assert "overflow-x: auto;" in css
        assert ".rich-table-toolbar {\n    align-items: flex-start;\n    flex-wrap: wrap;" in css
        assert ".rich-table-toolbar__group {\n    flex-wrap: wrap;" in css
        assert ".rich-table-search {\n    flex: 1 1 220px;" in css
        assert "@media (max-width: 640px)" in css
        assert ".rich-table-heading .query-card-summary {\n    min-width: 104px;" in css

    def test_query_results_table_fills_remaining_viewport_height(self):
        query_template = Path(settings.BASE_DIR / "templates/jira_workspace/queries.html").read_text()
        table_template = Path(
            settings.BASE_DIR / "templates/jira_workspace/partials/ticket_table.html"
        ).read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert 'rich_table_fill_height=True' in query_template
        assert 'data-rich-table-fill-height="{{ rich_table_fill_height|yesno' in table_template
        assert 'container.getAttribute("data-rich-table-fill-height") === "true"' in js
        assert 'height: fillHeight ? "100%" : "460px"' in js
        assert ".query-workbench {\n  grid-template-columns: minmax(0, 1fr);\n  align-items: stretch;\n  gap: 10px;\n  block-size: 100%;\n  min-height: 0;" in css
        assert ".query-workbench__main {\n  display: grid;\n  grid-template-rows: auto auto auto minmax(0, 1fr);\n  gap: 10px;\n  block-size: 100%;\n  min-height: 0;" in css
        assert ".query-workbench__results {\n  display: grid;\n  grid-template-rows: auto minmax(0, 1fr);" in css
        assert "padding: 12px 12px 0;" in css
        assert ".query-workbench__results .table-wrap--ticket-scroll {\n  block-size: 100%;" in css
        assert "max-block-size: none;" in css
        assert ".query-workbench__results .tabulator-tableholder {\n  min-height: 0;" in css

    def test_query_results_logs_switcher_has_javascript_and_styles(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "function initializeQueryResultsViewToggle(scope)" in js
        assert 'data-query-results-view-tab' in js
        assert 'data-query-results-panel' in js
        assert ".query-results-switcher" in css
        assert ".query-results-switcher__tab" in css
        assert ".query-results-panel[hidden]" in css

    def test_collapsed_sidebar_does_not_constrain_mobile_shell_width(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert "@media (max-width: 900px)" in css
        assert "body.nav-collapsed .app-shell {\n    grid-template-columns: 1fr;" in css
        assert "body.nav-collapsed .workspace-topbar,\n  body.nav-collapsed .app-nav,\n  body.nav-collapsed .app-main" in css

    def test_rich_table_assets_preserve_horizontal_overflow_for_dense_ticket_columns(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert 'layout: "fitDataTable"' in js
        assert 'layout: "fitDataStretch"' not in js
        assert ".app-main,\n.page-section,\n.panel" in css
        assert "min-width: 0;" in css
        assert ".table-wrap--ticket-scroll.tabulator" in css
        assert "display: block;" in css
        assert "width: 100%;" in css
        assert ".tabulator .tabulator-tableholder" in css
        assert "overflow-x: auto;" in css
        assert "min-width: max(100%, 1380px);" in css

    def test_rich_table_styles_flatten_tabulator_visual_chrome(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ".tabulator" in css
        assert ".tabulator-header" in css
        assert ".tabulator-footer" in css
        assert ".tabulator-menu" in css

    def test_rich_table_styles_override_midnight_theme_text_in_light_mode(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ':root[data-resolved-theme="light"] .tabulator .tabulator-col-title' in css
        assert ':root[data-resolved-theme="light"] .tabulator .tabulator-row .tabulator-cell' in css
        assert ':root[data-resolved-theme="light"] .tabulator .tabulator-header .tabulator-col .tabulator-header-filter input' in css
        assert ':root[data-resolved-theme="light"] .tabulator .tabulator-page' in css
        assert "color: var(--text);" in css
        assert "background: var(--control-bg);" in css

    def test_frontend_includes_live_update_polling_hooks(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()

        assert "initializeLiveUpdates" in js
        assert "/jira/live-state/" in js
        assert "asset_version" in js
        assert "data_version" in js
        assert "refreshAutoTargets" in js

    def test_base_template_cache_busts_local_frontend_assets(self):
        base_template = Path(settings.BASE_DIR / "templates/jira_workspace/base.html").read_text()

        assert "jira_workspace/jira.css' %}?v={{ shell_asset_version" in base_template
        assert "jira_workspace/jira.js' %}?v={{ shell_asset_version" in base_template

    def test_sync_command_center_styles_and_hooks_exist(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()
        html = Path(settings.BASE_DIR / "templates/jira_workspace/sync.html").read_text()

        assert ".sync-command-center" in css
        assert ".sync-card--profile" in css
        assert ".sync-card--controls" in css
        assert ".sync-card--status" in css
        assert ".sync-details__panel[hidden]" in css
        assert "@media (min-width: 1401px)" in css
        assert ".sync-command-center > .dashboard-grid" in css
        assert "display: contents;" in css
        assert 'data-sync-summary-runs' in html
        assert 'data-sync-details-toggle="history"' in html
        assert 'data-sync-details-toggle="profile"' in html

    def test_sync_command_center_javascript_hooks_are_present(self):
        js = Path(settings.BASE_DIR / "static/jira_workspace/jira.js").read_text()
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert 'data-sync-details-toggle' in js
        assert 'data-sync-details-panel' in js
        assert 'sync-details__panel' in css
        assert 'initializeSyncRefresh();' in js

    def test_tool_context_nav_styles_are_present(self):
        css = Path(settings.BASE_DIR / "static/jira_workspace/jira.css").read_text()

        assert ".tool-context-nav" in css
        assert ".tool-context-nav__link" in css
        assert ".tool-context-nav__link.active" in css
