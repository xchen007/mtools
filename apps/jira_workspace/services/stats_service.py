from django.db.models import Count

from jira_workspace.services.query_service import build_issue_queryset


def build_dashboard_project_groups(*, username, start=None, end=None):
    assigned = (
        build_issue_queryset(username=username, source="assigned", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key"))
        .order_by("-issue_count", "project_key")
    )
    created = (
        build_issue_queryset(username=username, source="created", start=start, end=end)
        .values("project_key")
        .annotate(issue_count=Count("issue_key"))
        .order_by("-issue_count", "project_key")
    )
    return {"assigned": list(assigned), "created": list(created)}
