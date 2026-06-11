from django.db.models import Q

from jira_workspace.models import JiraIssue


def build_issue_queryset(
    *,
    username,
    source="all",
    project_key=None,
    start=None,
    end=None,
    search=None,
    sort_by="updated_at",
    sort_order="desc",
):
    queryset = JiraIssue.objects.all()

    if source == "assigned":
        queryset = queryset.filter(assignee=username)
    elif source == "created":
        queryset = queryset.filter(reporter=username)
    else:
        queryset = queryset.filter(Q(assignee=username) | Q(reporter=username))

    if project_key:
        queryset = queryset.filter(project_key=project_key)
    if start:
        queryset = queryset.filter(updated_at__gte=start)
    if end:
        queryset = queryset.filter(updated_at__lte=end)
    if search:
        queryset = queryset.filter(
            Q(issue_key__icontains=search) | Q(summary__icontains=search)
        )

    ordering = sort_by if sort_order == "asc" else f"-{sort_by}"
    return queryset.order_by(ordering)
