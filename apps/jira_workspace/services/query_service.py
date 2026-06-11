from django.db.models import Q

from jira_workspace.models import JiraIssue

VALID_SOURCES = ("all", "assigned", "created")
VALID_SORT_FIELDS = (
    "assignee",
    "created_at",
    "issue_key",
    "priority",
    "project_key",
    "reporter",
    "status",
    "summary",
    "updated_at",
)
VALID_SORT_ORDERS = ("asc", "desc")


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
    if source not in VALID_SOURCES:
        expected_sources = ", ".join(VALID_SOURCES)
        raise ValueError(
            f"Invalid source '{source}'. Expected one of: {expected_sources}."
        )

    if sort_by not in VALID_SORT_FIELDS:
        expected_sort_fields = ", ".join(VALID_SORT_FIELDS)
        raise ValueError(
            f"Invalid sort_by '{sort_by}'. Expected one of: {expected_sort_fields}."
        )

    if sort_order not in VALID_SORT_ORDERS:
        expected_sort_orders = ", ".join(VALID_SORT_ORDERS)
        raise ValueError(
            f"Invalid sort_order '{sort_order}'. Expected one of: {expected_sort_orders}."
        )

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
