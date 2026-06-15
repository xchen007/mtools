from django.db.models import Count, Q

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
)

VALID_SOURCES = ("all", "assigned", "created")
VALID_SORT_FIELDS = (
    "assignee",
    "created_at",
    "issue_key",
    "issue_type",
    "priority",
    "project_key",
    "reporter",
    "status",
    "summary",
    "updated_at",
)
VALID_SORT_ORDERS = ("asc", "desc")
PRIMARY_GLOBAL_SYNC_POLICY_NAME = "Primary Jira Policy"


def normalize_issue_filters(
    *,
    username,
    source="all",
    project_key=None,
    projects=None,
    status=None,
    statuses=None,
    reporter=None,
    assignee=None,
    labels=None,
    sprint=None,
    issue_types=None,
    priorities=None,
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
        "projects": _normalize_list(projects),
        "status": (status or "").strip(),
        "statuses": _normalize_list(statuses),
        "reporter": None if reporter is None else reporter.strip(),
        "assignee": None if assignee is None else assignee.strip(),
        "labels": _normalize_list(labels),
        "sprint": (sprint or "").strip(),
        "issue_types": _normalize_list(issue_types),
        "priorities": _normalize_list(priorities),
        "search": (search or "").strip(),
        "sort_by": normalized_sort_by,
        "sort_order": normalized_sort_order,
    }


def build_issue_queryset(
    *,
    username,
    source="all",
    project_key=None,
    projects=None,
    status=None,
    statuses=None,
    reporter=None,
    assignee=None,
    labels=None,
    sprint=None,
    issue_type=None,
    issue_types=None,
    priority=None,
    priorities=None,
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

    queryset = active_policy_issue_queryset()

    explicit_people = reporter is not None or assignee is not None
    reporter = (reporter or "").strip() if reporter is not None else ""
    assignee = (assignee or "").strip() if assignee is not None else ""

    if explicit_people:
        people_query = Q()
        if assignee:
            people_query |= Q(assignee=assignee)
        if reporter:
            people_query |= Q(reporter=reporter)
        if people_query:
            queryset = queryset.filter(people_query)
    elif source == "assigned":
        queryset = queryset.filter(assignee=username)
    elif source == "created":
        queryset = queryset.filter(reporter=username)
    else:
        queryset = queryset.filter(Q(assignee=username) | Q(reporter=username))

    project_values = _normalize_list(projects)
    if project_key:
        project_values.append(project_key)
    if project_key:
        queryset = queryset.filter(project_key__in=project_values)
    elif project_values:
        queryset = queryset.filter(project_key__in=project_values)
    status_values = _normalize_list(statuses)
    if status:
        status_values.append(status)
    if status:
        queryset = queryset.filter(status__in=status_values)
    elif status_values:
        queryset = queryset.filter(status__in=status_values)
    label_values = _normalize_list(labels)
    if label_values:
        matching_keys = [
            issue.issue_key
            for issue in queryset.only("issue_key", "labels_json")
            if set(label_values).issubset(set(issue.labels_json or []))
        ]
        queryset = queryset.filter(issue_key__in=matching_keys)
    if sprint:
        queryset = queryset.filter(sprint__icontains=sprint)
    issue_type_values = _normalize_list(issue_types)
    if issue_type:
        issue_type_values.append(issue_type)
    if issue_type_values:
        queryset = queryset.filter(issue_type__in=issue_type_values)
    priority_values = _normalize_list(priorities)
    if priority:
        priority_values.append(priority)
    if priority_values:
        queryset = queryset.filter(priority__in=priority_values)
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
    active_queryset = active_policy_issue_queryset()
    base_queryset = active_queryset.filter(Q(assignee=username) | Q(reporter=username))
    project_options = list(
        base_queryset.values("project_key")
        .annotate(issue_count=Count("issue_key", distinct=True))
        .order_by("-issue_count", "project_key")
        .values_list("project_key", flat=True)
    )
    status_options = list(
        base_queryset.order_by("status").values_list("status", flat=True).distinct()
    )
    assignee_options = list(
        active_queryset.exclude(assignee__isnull=True)
        .exclude(assignee="")
        .order_by("assignee")
        .values_list("assignee", flat=True)
        .distinct()
    )
    reporter_options = list(
        active_queryset.exclude(reporter__isnull=True)
        .exclude(reporter="")
        .order_by("reporter")
        .values_list("reporter", flat=True)
        .distinct()
    )
    priority_options = list(
        active_queryset.exclude(priority__isnull=True)
        .exclude(priority="")
        .order_by("priority")
        .values_list("priority", flat=True)
        .distinct()
    )
    sprint_options = list(
        active_queryset.exclude(sprint__isnull=True)
        .exclude(sprint="")
        .order_by("sprint")
        .values_list("sprint", flat=True)
        .distinct()
    )
    issue_type_options = list(
        active_queryset.exclude(issue_type="")
        .order_by("issue_type")
        .values_list("issue_type", flat=True)
        .distinct()
    )
    label_options = sorted(
        {
            label
            for labels in active_queryset.values_list("labels_json", flat=True)
            for label in (labels or [])
            if label
        }
    )
    return {
        "source_options": VALID_SOURCES,
        "project_options": project_options,
        "status_options": status_options,
        "assignee_options": assignee_options,
        "reporter_options": reporter_options,
        "priority_options": priority_options,
        "sprint_options": sprint_options,
        "issue_type_options": issue_type_options,
        "label_options": label_options,
        "sort_field_options": VALID_SORT_FIELDS,
        "sort_order_options": VALID_SORT_ORDERS,
    }


def active_policy_issue_queryset():
    version = serving_global_sync_policy_version()
    if version is None:
        return JiraIssue.objects.none()
    return JiraIssue.objects.filter(
        is_active_in_current_policy=True,
        sync_memberships__policy_version_id=version.id,
        sync_memberships__is_active=True,
    ).distinct()


def serving_global_sync_policy_version():
    policy = current_global_sync_policy()
    if policy is None or policy.current_version_id is None:
        return None
    if (
        policy.current_version.status == GlobalSyncPolicyVersion.Status.READY
        and not policy.current_version.full_sync_required
    ):
        return policy.current_version
    return None


def current_policy_issue_queryset():
    policy = current_global_sync_policy()
    if policy is None or policy.current_version_id is None:
        return JiraIssue.objects.none()
    return JiraIssue.objects.filter(
        is_active_in_current_policy=True,
        sync_memberships__policy_version_id=policy.current_version_id,
        sync_memberships__is_active=True,
    ).distinct()


def current_global_sync_policy():
    queryset = (
        GlobalSyncPolicy.objects.select_related("current_version")
        .filter(current_version__isnull=False)
    )
    primary_policy = queryset.filter(name=PRIMARY_GLOBAL_SYNC_POLICY_NAME).first()
    if primary_policy is not None:
        return primary_policy
    return queryset.order_by("id").first()


def _normalize_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]
