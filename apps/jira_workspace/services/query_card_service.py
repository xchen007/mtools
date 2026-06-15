from django.utils import timezone

from jira_workspace.models import OperationLog, JiraSavedQuery, JiraSyncProfile
from jira_workspace.services.operation_log_service import OperationLogService
from jira_workspace.services.query_card_types import require_query_card_type
from jira_workspace.services.query_service import build_issue_queryset, normalize_issue_filters


DEFAULT_SUMMARY_METRICS = [
    "total",
    "updated_today",
    "blocked",
    "in_progress",
    "high_priority",
]

METRIC_LABELS = {
    "total": "Total results",
    "updated_today": "Updated today",
    "blocked": "Blocked / waiting",
    "in_progress": "In progress",
    "high_priority": "High priority",
}


class QueryCardService:
    def __init__(self, *, username):
        self.username = username

    def list_cards(self):
        return list(
            JiraSavedQuery.objects.select_related("profile")
            .filter(is_enabled=True)
            .order_by("position", "-is_pinned", "-is_starred", "name")
        )

    def ensure_default_cards(self):
        cards = self.list_cards()
        if cards:
            return cards

        profile = (
            JiraSyncProfile.objects.order_by("-is_default", "name", "id").first()
        )
        if not profile:
            return []

        defaults = [
            {
                "name": "Assigned to me",
                "description": "Issues currently assigned to the active user.",
                "filters_json": {"source": "assigned"},
                "jql_text": "assignee = currentUser() ORDER BY updated DESC",
            },
            {
                "name": "Reported by me",
                "description": "Issues reported by the active user.",
                "filters_json": {"source": "created"},
                "jql_text": "reporter = currentUser() ORDER BY updated DESC",
            },
            {
                "name": "Blocked or waiting",
                "description": "Blocked local cached issues that need attention.",
                "filters_json": {"status": ["Blocked"]},
                "jql_text": 'status = "Blocked" ORDER BY updated DESC',
            },
            {
                "name": "Current sprint review",
                "description": "Review queue from cached Jira issues.",
                "filters_json": {"status": ["Review"]},
                "jql_text": 'status = "Review" ORDER BY updated DESC',
            },
        ]
        for position, data in enumerate(defaults, start=10):
            JiraSavedQuery.objects.create(
                profile=profile,
                position=position,
                **data,
            )
        return self.list_cards()

    def resolve_card(self, *, card_id=None, legacy_saved_query_id=None):
        selected_id = card_id or legacy_saved_query_id
        cards = self.list_cards()
        if selected_id:
            for card in cards:
                if str(card.id) == str(selected_id):
                    return card
        return cards[0] if cards else None

    def evaluate_card(self, card, *, limit=240):
        if not card:
            return []

        card_type = require_query_card_type(card.card_kind)
        if not card_type.supports_issue_results:
            raise ValueError(f"Unsupported query card type '{card.card_kind}'.")

        filters_json = dict(card.filters_json or {})
        normalized_filters = normalize_issue_filters(
            username=self.username,
            source=self._first_filter_value(filters_json, "source") or "all",
            projects=filters_json.get("project"),
            statuses=filters_json.get("status"),
            reporter=self._explicit_filter_value(filters_json, "reporter"),
            assignee=self._explicit_filter_value(filters_json, "assignee"),
            labels=filters_json.get("labels"),
            sprint=self._first_filter_value(filters_json, "sprint"),
            issue_types=filters_json.get("issue_type"),
            priorities=filters_json.get("priority"),
            search=self._first_filter_value(filters_json, "search"),
            sort_by=card.sort_by,
            sort_order=card.sort_order,
        )
        return list(build_issue_queryset(**normalized_filters)[:limit])

    def compute_metrics(self, rows, metric_keys=None):
        metric_keys = list(metric_keys or DEFAULT_SUMMARY_METRICS)
        today = timezone.localdate()
        metric_values = {
            "total": len(rows),
            "updated_today": sum(1 for row in rows if row.updated_at and timezone.localdate(row.updated_at) == today),
            "blocked": sum(1 for row in rows if (row.status or "").lower() in {"blocked", "waiting", "reopened"}),
            "in_progress": sum(1 for row in rows if (row.status or "").lower() in {"in progress", "review", "qa", "selected for development"}),
            "high_priority": sum(1 for row in rows if (row.priority or "").lower() in {"high", "highest", "critical", "blocker"}),
        }
        return [
            {
                "key": key,
                "label": METRIC_LABELS.get(key, key.replace("_", " ").title()),
                "value": metric_values.get(key, 0),
            }
            for key in metric_keys
        ]

    def run_card(self, card):
        log_service = OperationLogService()
        request_payload = {
            "filters": dict(card.filters_json or {}),
            "jql_text": card.jql_text,
            "query_syntax": card.query_syntax,
            "sort_by": card.sort_by,
            "sort_order": card.sort_order,
        }
        log = log_service.start_log(
            tool=OperationLog.Tool.JIRA_QUERY,
            action="run_card",
            title=card.name,
            triggered_by=self.username,
            target_type="query_card",
            target_id=card.id,
            request_payload=request_payload,
        )

        try:
            rows = self.evaluate_card(card)
            metrics = self.compute_metrics(
                rows,
                getattr(card, "summary_metrics_json", None),
            )
            metric_summary = ", ".join(
                f"{metric['key']}={metric['value']}" for metric in metrics
            )
            log_service.mark_success(
                log,
                result_summary=f"{len(rows)} results",
                log_text=(
                    f"card={card.name}\n"
                    f"query_syntax={card.query_syntax}\n"
                    f"filters={dict(card.filters_json or {})}\n"
                    f"jql_text={card.jql_text or ''}\n"
                    f"metrics={metric_summary}"
                ),
            )
            return rows, metrics, log
        except Exception as exc:
            log_service.mark_failure(
                log,
                error_message=str(exc),
                log_text=(
                    f"card={card.name}\n"
                    f"query_syntax={card.query_syntax}\n"
                    f"filters={dict(card.filters_json or {})}\n"
                    f"jql_text={card.jql_text or ''}\n"
                    f"error={exc}"
                ),
            )
            raise

    def duplicate_card(self, card):
        duplicate = JiraSavedQuery.objects.create(
            name=self._copy_name(card.name),
            profile=card.profile,
            description=card.description,
            filters_json=dict(card.filters_json or {}),
            jql_text=card.jql_text,
            card_kind=card.card_kind,
            query_syntax=card.query_syntax,
            summary_metrics_json=list(card.summary_metrics_json or []),
            default_columns_json=list(card.default_columns_json or []),
            default_page_size=card.default_page_size,
            position=card.position + 1,
            is_enabled=card.is_enabled,
            is_starred=False,
            is_pinned=card.is_pinned,
            sort_by=card.sort_by,
            sort_order=card.sort_order,
        )
        return duplicate

    def delete_card(self, card):
        card.delete()
        return self.resolve_card()

    def persistence_scope(self, card):
        return f"/jira/query/card/{card.id}/" if card else "/jira/query/card/new/"

    def build_context(self, *, selected_card=None, form=None, editor_open=False, form_action="update_card"):
        cards = self.list_cards()
        selected_card = selected_card or (cards[0] if cards else None)
        rows = self.evaluate_card(selected_card)
        return {
            "query_cards": cards,
            "saved_queries": cards,
            "selected_card": selected_card,
            "selected_query": selected_card,
            "query_form": form,
            "query_rows": rows,
            "query_card_metrics": self.compute_metrics(
                rows,
                getattr(selected_card, "summary_metrics_json", None),
            ),
            "query_card_persistence_scope": self.persistence_scope(selected_card),
            "query_card_editor_open": editor_open,
            "query_card_form_action": form_action,
        }

    def _copy_name(self, name):
        base_name = f"{name} Copy"
        candidate = base_name
        suffix = 2
        while JiraSavedQuery.objects.filter(name=candidate).exists():
            candidate = f"{base_name} {suffix}"
            suffix += 1
        return candidate

    def _first_filter_value(self, filters_json, key):
        value = filters_json.get(key)
        if isinstance(value, (list, tuple)):
            return value[0] if value else ""
        return value or ""

    def _explicit_filter_value(self, filters_json, key):
        if key not in filters_json:
            return None
        return self._first_filter_value(filters_json, key)
