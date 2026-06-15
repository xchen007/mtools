from django.db.models import Count

from jira_workspace.services.query_service import build_issue_queryset


def build_dashboard_project_groups(*, username, start=None, end=None):
    assigned = (
        build_issue_queryset(username=username, source="assigned", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key", distinct=True))
        .order_by("-issue_count", "project_key")
    )
    created = (
        build_issue_queryset(username=username, source="created", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key", distinct=True))
        .order_by("-issue_count", "project_key")
    )
    return {"assigned": list(assigned), "created": list(created)}


def build_dashboard_summary(*, username, start=None, end=None):
    tracked_queryset = build_issue_queryset(username=username, start=start, end=end)
    assigned_queryset = build_issue_queryset(
        username=username,
        source="assigned",
        start=start,
        end=end,
    )
    created_queryset = build_issue_queryset(
        username=username,
        source="created",
        start=start,
        end=end,
    )
    return [
        {
            "label": "Assigned Issues",
            "value": assigned_queryset.count(),
        },
        {
            "label": "Created Issues",
            "value": created_queryset.count(),
        },
        {
            "label": "Tracked Projects",
            "value": tracked_queryset.values("project_key").distinct().count(),
        },
        {
            "label": "Blocked Issues",
            "value": tracked_queryset.filter(status__iexact="Blocked").count(),
        },
    ]
