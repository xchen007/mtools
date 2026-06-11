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


def normalize_issue_filters(
    *,
    username,
    source="all",
    project_key=None,
    status=None,
    search=None,
    sort_by="updated_at",
    sort_order="desc",
):
    normalized_source = source if source in VALID_SOURCES else "all"
    normalized_sort_by = sort_by if sort_by in VALID_SORT_FIELDS else "updated_at"
    normalized_sort_order = sort_order if sort_order in VALID_SORT_ORDERS else "desc"

    return {
        "username": username,
        "source": normalized_source,
        "project_key": (project_key or "").strip(),
        "status": (status or "").strip(),
        "search": (search or "").strip(),
        "sort_by": normalized_sort_by,
        "sort_order": normalized_sort_order,
    }


def build_issue_queryset(
    *,
    username,
    source="all",
    project_key=None,
    status=None,
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
    if status:
        queryset = queryset.filter(status__iexact=status)
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


def build_issue_filter_options(*, username):
    base_queryset = build_issue_queryset(username=username)
    project_options = list(
        base_queryset.order_by("project_key")
        .values_list("project_key", flat=True)
        .distinct()
    )
    status_options = list(
        base_queryset.order_by("status").values_list("status", flat=True).distinct()
    )
    assignee_options = list(
        JiraIssue.objects.exclude(assignee__isnull=True)
        .exclude(assignee="")
        .order_by("assignee")
        .values_list("assignee", flat=True)
        .distinct()
    )
    priority_options = list(
        JiraIssue.objects.exclude(priority__isnull=True)
        .exclude(priority="")
        .order_by("priority")
        .values_list("priority", flat=True)
        .distinct()
    )
    return {
        "source_options": VALID_SOURCES,
        "project_options": project_options,
        "status_options": status_options,
        "assignee_options": assignee_options,
        "priority_options": priority_options,
        "sort_field_options": VALID_SORT_FIELDS,
        "sort_order_options": VALID_SORT_ORDERS,
    }
