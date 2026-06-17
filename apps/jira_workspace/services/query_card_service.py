import json
import re
from datetime import datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from jira_workspace.models import (
    JiraIssueMetric,
    OperationLog,
    JiraSavedQuery,
    JiraSyncProfile,
)
from jira_workspace.services.operation_log_service import OperationLogService
from jira_workspace.services.query_card_types import (
    SPRINT_REPORT_CARD_KIND,
    require_query_card_type,
)
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

SPRINT_REPORT_SUMMARY_METRICS = [
    "total",
    "estimated_hours",
    "log_hours",
    "done",
    "remaining_hours",
    "completion_rate",
]

SPRINT_REPORT_METRIC_LABELS = {
    "total": "Total tickets",
    "estimated_hours": "Estimated",
    "log_hours": "Log time",
    "done": "Done tickets",
    "remaining_hours": "Remaining",
    "completion_rate": "Completion",
}

SPRINT_DONE_STATUSES = {"closed", "done", "resolved"}


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

    def compute_card_metrics(self, card, rows):
        if card and card.card_kind == SPRINT_REPORT_CARD_KIND:
            metric_keys = list(card.summary_metrics_json or [])
            if not metric_keys or set(metric_keys).issubset(set(DEFAULT_SUMMARY_METRICS)):
                metric_keys = SPRINT_REPORT_SUMMARY_METRICS
            return self.compute_sprint_metrics(rows, metric_keys)
        return self.compute_metrics(
            rows,
            getattr(card, "summary_metrics_json", None),
        )

    def compute_sprint_metrics(self, rows, metric_keys=None):
        metric_keys = list(metric_keys or SPRINT_REPORT_SUMMARY_METRICS)
        report = self.build_sprint_report(rows)
        total = len(rows)
        done = sum(1 for row in report["rows"] if row["done_label"])
        estimated_minutes = sum(row["estimated_minutes"] for row in report["rows"])
        log_minutes = sum(row["log_minutes"] for row in report["rows"])
        remaining_minutes = max(estimated_minutes - log_minutes, 0)
        metric_values = {
            "total": total,
            "estimated_hours": self._format_minutes_as_hours(estimated_minutes),
            "log_hours": self._format_minutes_as_hours(log_minutes),
            "done": done,
            "remaining_hours": self._format_minutes_as_hours(remaining_minutes),
            "completion_rate": f"{int((done / total) * 100)}%" if total else "0%",
        }
        return [
            {
                "key": key,
                "label": SPRINT_REPORT_METRIC_LABELS.get(
                    key,
                    METRIC_LABELS.get(key, key.replace("_", " ").title()),
                ),
                "value": metric_values.get(key, 0),
            }
            for key in metric_keys
        ]

    def build_sprint_report(self, rows, labels=None):
        report_rows = []
        completion_counts = {}
        status_counts = {}
        worklog_entries = []
        report_labels = list(labels or [])
        metrics_by_issue_key = {
            metric.issue_id: metric
            for metric in JiraIssueMetric.objects.filter(
                issue_id__in=[row.issue_key for row in rows]
            )
        }
        for row in rows:
            raw_fields = self._raw_fields(row)
            estimated_minutes = self._estimated_minutes(row, raw_fields)
            log_minutes = self._log_minutes(
                row,
                raw_fields,
                metrics_by_issue_key.get(row.issue_key),
            )
            row_labels = self._row_report_labels(row, report_labels)
            if not report_labels:
                for label in row_labels:
                    if label not in report_labels:
                        report_labels.append(label)
            entries = self._worklog_entries(row, raw_fields, row_labels)
            if entries:
                worklog_entries.extend(entries)
            elif log_minutes:
                fallback_date = timezone.localdate(row.updated_at or timezone.now())
                worklog_entries.append(
                    {
                        "date": fallback_date.isoformat(),
                        "week": self._week_start(fallback_date).isoformat(),
                        "label": row_labels[0] if row_labels else row.project_key or "Sprint",
                        "minutes": log_minutes,
                    }
                )
            done_label = self._done_label(row, raw_fields)
            if done_label:
                completion_counts[done_label] = completion_counts.get(done_label, 0) + 1
            status = row.status or "-"
            status_counts[status] = status_counts.get(status, 0) + 1
            report_rows.append(
                {
                    "issue": row,
                    "estimated_minutes": estimated_minutes,
                    "log_minutes": log_minutes,
                    "estimated_hours": self._format_minutes_as_hours(estimated_minutes),
                    "log_hours": self._format_minutes_as_hours(log_minutes),
                    "done_label": done_label,
                }
            )
        weekly_stats = self._weekly_stats(worklog_entries)
        return {
            "rows": report_rows,
            "done_count": sum(1 for row in report_rows if row["done_label"]),
            "total_logged_hours": self._format_minutes_as_hours(
                sum(row["log_minutes"] for row in report_rows)
            ),
            "daily_average_hours": self._format_minutes_as_hours(weekly_stats["this_week_avg_minutes"]),
            "last_week_total_hours": self._format_minutes_as_hours(weekly_stats["last_week_minutes"]),
            "last_week_average_hours": self._format_minutes_as_hours(weekly_stats["last_week_avg_minutes"]),
            "completion_buckets": [
                {"label": label, "count": count}
                for label, count in sorted(completion_counts.items())
            ],
            "status_counts": [
                {"label": label, "count": count}
                for label, count in sorted(status_counts.items())
            ],
            "labels": report_labels,
            "daily_chart": self._daily_chart(worklog_entries, report_labels),
            "weekly_chart": self._weekly_chart(worklog_entries, report_labels),
        }

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
            metrics = self.compute_card_metrics(card, rows)
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
        is_sprint_report_card = (
            selected_card is not None
            and selected_card.card_kind == SPRINT_REPORT_CARD_KIND
        )
        sprint_report = (
            self.build_sprint_report(
                rows,
                labels=dict(selected_card.filters_json or {}).get("labels"),
            )
            if is_sprint_report_card
            else None
        )
        return {
            "query_cards": cards,
            "saved_queries": cards,
            "selected_card": selected_card,
            "selected_query": selected_card,
            "query_form": form,
            "query_rows": rows,
            "query_card_metrics": self.compute_card_metrics(selected_card, rows),
            "is_sprint_report_card": is_sprint_report_card,
            "sprint_report": sprint_report,
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

    @staticmethod
    def _raw_fields(row):
        try:
            payload = json.loads(row.raw_json or "{}")
        except (TypeError, ValueError):
            return {}
        fields = payload.get("fields", {})
        return fields if isinstance(fields, dict) else {}

    def _estimated_minutes(self, row, raw_fields):
        seconds = self._first_seconds_value(
            raw_fields,
            (
                "timeoriginalestimate",
                "aggregatetimeoriginalestimate",
                "originalEstimateSeconds",
            ),
        )
        timetracking = raw_fields.get("timetracking")
        if seconds is None and isinstance(timetracking, dict):
            seconds = self._first_seconds_value(
                timetracking,
                ("originalEstimateSeconds",),
            )
        return int((seconds or 0) / 60)

    def _log_minutes(self, row, raw_fields, metric=None):
        if metric is None:
            try:
                metric = row.metrics
            except ObjectDoesNotExist:
                metric = None
        if metric and metric.worklog_minutes is not None:
            return metric.worklog_minutes

        seconds = self._first_seconds_value(
            raw_fields,
            ("timespent", "aggregatetimespent", "timeSpentSeconds"),
        )
        worklog = raw_fields.get("worklog")
        if seconds is None and isinstance(worklog, dict):
            seconds = sum(
                int(item.get("timeSpentSeconds") or 0)
                for item in worklog.get("worklogs", [])
                if isinstance(item, dict)
            )
        return int((seconds or 0) / 60)

    def _row_report_labels(self, row, report_labels):
        row_labels = list(row.labels_json or [])
        matched = [label for label in report_labels if label in row_labels]
        if matched:
            return matched
        if row_labels:
            return [row_labels[0]]
        return [row.sprint or row.project_key or "Sprint"]

    def _worklog_entries(self, row, raw_fields, labels):
        worklog = raw_fields.get("worklog")
        if not isinstance(worklog, dict):
            return []

        label = labels[0] if labels else row.project_key or "Sprint"
        entries = []
        for item in worklog.get("worklogs", []):
            if not isinstance(item, dict):
                continue
            if not self._is_user_worklog(item):
                continue
            try:
                seconds = int(item.get("timeSpentSeconds") or 0)
            except (TypeError, ValueError):
                seconds = 0
            started = self._parse_jira_datetime(item.get("started"))
            if seconds <= 0 or not started:
                continue
            started_date = timezone.localdate(started)
            entries.append(
                {
                    "date": started_date.isoformat(),
                    "week": self._week_start(started_date).isoformat(),
                    "label": label,
                    "minutes": int(seconds / 60),
                }
            )
        return entries

    def _is_user_worklog(self, item):
        author = item.get("author")
        if not isinstance(author, dict):
            return True
        candidates = {
            str(author.get("name") or "").lower(),
            str(author.get("displayName") or "").lower(),
            str(author.get("emailAddress") or "").split("@")[0].lower(),
            str(author.get("accountId") or "").lower(),
        }
        return self.username.lower() in candidates

    def _weekly_stats(self, worklog_entries):
        today = timezone.localdate()
        this_week = self._week_start(today)
        last_week = this_week - timedelta(days=7)
        this_week_by_day = {}
        last_week_by_day = {}
        for entry in worklog_entries:
            entry_date = datetime.fromisoformat(entry["date"]).date()
            if entry_date.weekday() > 4:
                continue
            if entry["week"] == this_week.isoformat():
                this_week_by_day[entry["date"]] = this_week_by_day.get(entry["date"], 0) + entry["minutes"]
            elif entry["week"] == last_week.isoformat():
                last_week_by_day[entry["date"]] = last_week_by_day.get(entry["date"], 0) + entry["minutes"]
        this_week_minutes = sum(this_week_by_day.values())
        last_week_minutes = sum(last_week_by_day.values())
        return {
            "this_week_avg_minutes": int(this_week_minutes / len(this_week_by_day)) if this_week_by_day else 0,
            "last_week_minutes": last_week_minutes,
            "last_week_avg_minutes": int(last_week_minutes / len(last_week_by_day)) if last_week_by_day else 0,
        }

    def _daily_chart(self, worklog_entries, labels):
        dates = sorted({entry["date"] for entry in worklog_entries})
        values = {}
        total_by_date = {}
        for entry in worklog_entries:
            key = (entry["label"], entry["date"])
            values[key] = values.get(key, 0) + entry["minutes"]
            total_by_date[entry["date"]] = total_by_date.get(entry["date"], 0) + entry["minutes"]
        max_hours = max([8] + [minutes / 60 for minutes in total_by_date.values()]) if dates else 8
        max_hours = max(8, int((max_hours + 1.99) / 2) * 2)
        width, height = 400, 200
        ml, mr, mt, mb = 28, 8, 10, 36
        pw, ph = width - ml - mr, height - mt - mb

        def y(hours):
            return round(mt + ph - (hours / max_hours) * ph, 2)

        def x(index):
            if len(dates) <= 1:
                return round(ml + pw / 2, 2)
            return round(ml + (index / (len(dates) - 1)) * pw, 2)

        def build_points(value_map):
            return [
                {
                    "date": date,
                    "x": x(index),
                    "y": y(value_map.get(date, 0) / 60),
                    "hours": self._format_minutes_as_hours(value_map.get(date, 0)),
                }
                for index, date in enumerate(dates)
            ]

        def path(points):
            if not points:
                return ""
            parts = [f"M {points[0]['x']} {points[0]['y']}"]
            for index in range(1, len(points)):
                previous = points[index - 1]
                current = points[index]
                control_x = round((previous["x"] + current["x"]) / 2, 2)
                parts.append(
                    f"C {control_x} {previous['y']} {control_x} {current['y']} {current['x']} {current['y']}"
                )
            return " ".join(parts)

        palette = self._chart_palette()
        series = []
        for index, label in enumerate(labels or ["Sprint"]):
            label_values = {
                date: values.get((label, date), 0)
                for date in dates
            }
            points = build_points(label_values)
            line_path = path(points)
            area_path = (
                f"{line_path} L {points[-1]['x']} {mt + ph} L {points[0]['x']} {mt + ph} Z"
                if points
                else ""
            )
            series.append(
                {
                    "label": label,
                    "short_label": self._short_label(label),
                    "color": palette[index % len(palette)],
                    "points": points,
                    "line_path": line_path,
                    "area_path": area_path,
                }
            )
        total_points = build_points(total_by_date)
        return {
            "width": width,
            "height": height,
            "grid": [
                {"hours": hours, "y": y(hours), "label_y": y(hours) + 4}
                for hours in range(0, max_hours + 1, 2 if max_hours <= 10 else 4)
            ],
            "target_y": y(8),
            "series": series,
            "total_path": path(total_points),
            "total_points": total_points,
            "x_labels": [
                {"date": point["date"], "label": point["date"][5:], "x": point["x"]}
                for point in total_points
            ],
        }

    def _weekly_chart(self, worklog_entries, labels):
        weeks = sorted({entry["week"] for entry in worklog_entries})
        values = {}
        totals = {}
        for entry in worklog_entries:
            key = (entry["label"], entry["week"])
            values[key] = values.get(key, 0) + entry["minutes"]
            totals[entry["week"]] = totals.get(entry["week"], 0) + entry["minutes"]
        max_hours = max([8] + [minutes / 60 for minutes in totals.values()]) if weeks else 8
        max_hours = max(8, int((max_hours + 3.99) / 4) * 4)
        width, height = 340, 200
        ml, mr, mt, mb = 28, 8, 10, 20
        pw, ph = width - ml - mr, height - mt - mb
        chart_labels = labels or ["Sprint"]
        group_width = min((pw / max(len(weeks), 1)) * 0.7, 80)
        group_gap = (pw - group_width * len(weeks)) / (len(weeks) - 1) if len(weeks) > 1 else 0
        bar_width = max(group_width / max(len(chart_labels), 1) - 2, 4)
        palette = self._chart_palette()

        def y(minutes):
            return round(mt + ph - ((minutes / 60) / max_hours) * ph, 2)

        def bar_height(minutes):
            return round(mt + ph - y(minutes), 2)

        def group_x(index):
            if len(weeks) <= 1:
                return round(ml + (pw - group_width) / 2, 2)
            return round(ml + index * (group_width + group_gap), 2)

        bars = []
        for week_index, week in enumerate(weeks):
            base_x = group_x(week_index)
            for label_index, label in enumerate(chart_labels):
                minutes = values.get((label, week), 0)
                offset = (group_width - bar_width * len(chart_labels)) / 2
                bars.append(
                    {
                        "week": week,
                        "week_label": self._short_week_label(week),
                        "label": label,
                        "short_label": self._short_label(label),
                        "x": round(base_x + offset + label_index * bar_width, 2),
                        "y": y(minutes),
                        "width": round(bar_width, 2),
                        "height": bar_height(minutes),
                        "color": palette[label_index % len(palette)],
                    }
                )
        return {
            "width": width,
            "height": height,
            "grid": [
                {"hours": hours, "y": y(hours * 60), "label_y": y(hours * 60) + 4}
                for hours in range(0, max_hours + 1, 4 if max_hours <= 20 else 8)
            ],
            "bars": bars,
            "x_labels": [
                {
                    "week": week,
                    "label": self._short_week_label(week),
                    "x": round(group_x(index) + group_width / 2, 2),
                }
                for index, week in enumerate(weeks)
            ],
            "labels": [
                {
                    "label": label,
                    "short_label": self._short_label(label),
                    "color": palette[index % len(palette)],
                }
                for index, label in enumerate(chart_labels)
            ],
        }

    def _done_label(self, row, raw_fields):
        status = row.status or self._display_value(raw_fields.get("status")) or ""
        if status.lower() not in SPRINT_DONE_STATUSES:
            return ""

        date_value = raw_fields.get("resolutiondate") or raw_fields.get("updated")
        done_at = self._parse_jira_datetime(date_value) or row.updated_at
        if not done_at:
            return ""
        done_date = timezone.localdate(done_at)
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        previous_week_start = week_start - timedelta(days=7)
        if done_date >= week_start:
            return "this week"
        if done_date >= previous_week_start:
            return "last week"
        return done_date.isoformat()

    @staticmethod
    def _week_start(value):
        return value - timedelta(days=value.weekday())

    @staticmethod
    def _short_label(value, limit=16):
        text = str(value or "Sprint")
        return text if len(text) <= limit else f"{text[: limit - 3]}..."

    @staticmethod
    def _short_week_label(value):
        try:
            parsed = datetime.fromisoformat(value).date()
        except (TypeError, ValueError):
            return value
        return parsed.strftime("%b %-d")

    @staticmethod
    def _chart_palette():
        return ["#4f9eff", "#3fb950", "#d29922", "#a371f7", "#db61a2"]

    @staticmethod
    def _first_seconds_value(mapping, keys):
        for key in keys:
            value = mapping.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _display_value(value):
        if isinstance(value, dict):
            return value.get("name") or value.get("displayName") or value.get("value")
        return value

    @staticmethod
    def _parse_jira_datetime(value):
        if not value:
            return None
        if hasattr(value, "date"):
            return value if timezone.is_aware(value) else timezone.make_aware(value)
        normalized = str(value).strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        normalized = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", normalized)
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)

    @staticmethod
    def _format_minutes_as_hours(minutes):
        hours = (minutes or 0) / 60
        if hours.is_integer():
            return f"{int(hours)}h"
        return f"{hours:.1f}h"
