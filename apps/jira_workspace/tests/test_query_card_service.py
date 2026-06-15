from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from jira_workspace.forms import JiraSavedQueryForm
from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
    JiraSavedQuery,
    JiraSyncProfile,
    OperationLog,
    SyncScope,
)
from jira_workspace.services.query_card_service import QueryCardService
from jira_workspace.services.query_card_types import (
    JIRA_ISSUE_QUERY_CARD_KIND,
    get_query_card_type,
    get_query_card_type_choices,
)


class QueryCardServiceTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.profile = JiraSyncProfile.objects.create(
            name="My Issues",
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json={"username": "xchen17"},
            jql='assignee = "xchen17" ORDER BY updated DESC',
            is_default=True,
        )
        JiraIssue.objects.create(
            issue_key="OPS-1842",
            project_key="OPS",
            summary="Release blocker",
            status="Blocked",
            assignee="xchen17",
            reporter="amy",
            priority="High",
            updated_at=self.now,
            created_at=self.now - timedelta(days=3),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="TESS-2291",
            project_key="TESS",
            summary="Sync status page",
            status="In Progress",
            assignee="xchen17",
            reporter="bob",
            priority="Medium",
            updated_at=self.now - timedelta(days=1),
            created_at=self.now - timedelta(days=4),
            raw_json="{}",
            last_seen_at=self.now,
        )
        JiraIssue.objects.create(
            issue_key="CP-778",
            project_key="CP",
            summary="Reported review queue",
            status="Review",
            assignee="nina",
            reporter="xchen17",
            priority="Low",
            updated_at=self.now - timedelta(days=2),
            created_at=self.now - timedelta(days=5),
            raw_json="{}",
            last_seen_at=self.now,
        )
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
            next_run_at=self.now,
        )
        for issue in JiraIssue.objects.order_by("issue_key"):
            issue.is_active_in_current_policy = True
            issue.first_seen_policy_version_id = version.id
            issue.last_seen_policy_version_id = version.id
            issue.save(
                update_fields=[
                    "is_active_in_current_policy",
                    "first_seen_policy_version",
                    "last_seen_policy_version",
                    "updated_at",
                ]
            )
            JiraIssueScopeMembership.objects.create(
                issue=issue,
                scope=scope,
                policy_version=version,
                first_seen_at=self.now,
                last_checked_at=self.now,
                last_synced_success_at=self.now,
                last_seen_issue_updated_at=issue.updated_at,
                is_active=True,
            )
        self.assigned_card = JiraSavedQuery.objects.create(
            name="Assigned to me",
            profile=self.profile,
            filters_json={"source": "assigned"},
            position=20,
        )
        self.reported_card = JiraSavedQuery.objects.create(
            name="Reported by me",
            profile=self.profile,
            filters_json={"source": "created"},
            position=10,
        )

    def test_list_cards_orders_enabled_cards_by_position_then_name(self):
        JiraSavedQuery.objects.create(
            name="Disabled",
            profile=self.profile,
            is_enabled=False,
            position=1,
        )

        cards = QueryCardService(username="xchen17").list_cards()

        assert [card.name for card in cards] == ["Reported by me", "Assigned to me"]

    def test_resolve_card_accepts_card_and_legacy_saved_query_id(self):
        service = QueryCardService(username="xchen17")

        assert service.resolve_card(card_id=str(self.reported_card.id)) == self.reported_card
        assert service.resolve_card(legacy_saved_query_id=str(self.assigned_card.id)) == self.assigned_card

    def test_evaluate_card_uses_structured_filters_and_summary_metrics(self):
        service = QueryCardService(username="xchen17")

        rows = service.evaluate_card(self.assigned_card)
        metrics = service.compute_metrics(rows)

        assert [row.issue_key for row in rows] == ["OPS-1842", "TESS-2291"]
        assert metrics == [
            {"key": "total", "label": "Total results", "value": 2},
            {"key": "updated_today", "label": "Updated today", "value": 1},
            {"key": "blocked", "label": "Blocked / waiting", "value": 1},
            {"key": "in_progress", "label": "In progress", "value": 1},
            {"key": "high_priority", "label": "High priority", "value": 1},
        ]

    def test_duplicate_card_creates_separate_copy(self):
        duplicate = QueryCardService(username="xchen17").duplicate_card(self.assigned_card)

        assert duplicate.pk != self.assigned_card.pk
        assert duplicate.name == "Assigned to me Copy"
        assert duplicate.filters_json == self.assigned_card.filters_json
        assert duplicate.position == self.assigned_card.position + 1

    def test_persistence_scope_is_card_specific(self):
        scope = QueryCardService(username="xchen17").persistence_scope(self.assigned_card)

        assert scope == f"/jira/query/card/{self.assigned_card.id}/"

    def test_ensure_default_cards_creates_common_cards_when_empty(self):
        JiraSavedQuery.objects.all().delete()

        cards = QueryCardService(username="xchen17").ensure_default_cards()

        assert [card.name for card in cards] == [
            "Assigned to me",
            "Reported by me",
            "Blocked or waiting",
            "Current sprint review",
        ]
        assert cards[0].filters_json == {"source": "assigned"}
        assert cards[1].filters_json == {"source": "created"}
        assert cards[2].filters_json == {"status": ["Blocked"]}
        assert cards[3].filters_json == {"status": ["Review"]}

    def test_query_card_type_choices_are_registry_backed(self):
        form = JiraSavedQueryForm()
        card_type = get_query_card_type(JIRA_ISSUE_QUERY_CARD_KIND)

        assert card_type.value == JIRA_ISSUE_QUERY_CARD_KIND
        assert card_type.label == "Jira Issue Query"
        assert card_type.supports_issue_results is True
        assert list(form.fields["card_kind"].choices) == get_query_card_type_choices()

    def test_evaluate_card_rejects_unimplemented_card_kind(self):
        future_card = JiraSavedQuery.objects.create(
            name="Future card",
            profile=self.profile,
            card_kind="future_dashboard",
            filters_json={"source": "assigned"},
        )

        with self.assertRaisesMessage(
            ValueError,
            "Unsupported query card type 'future_dashboard'.",
        ):
            QueryCardService(username="xchen17").evaluate_card(future_card)

    def test_run_card_creates_success_operation_log(self):
        service = QueryCardService(username="xchen17")

        rows, metrics, log = service.run_card(self.assigned_card)

        assert [row.issue_key for row in rows] == ["OPS-1842", "TESS-2291"]
        assert metrics[0]["value"] == 2
        assert log.tool == OperationLog.Tool.JIRA_QUERY
        assert log.action == "run_card"
        assert log.status == OperationLog.Status.SUCCESS
        assert log.target_type == "query_card"
        assert log.target_id == str(self.assigned_card.id)
