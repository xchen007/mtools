from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from jira_workspace.forms import JiraSavedQueryForm, JiraSyncProfileForm
from jira_workspace.models import JiraSavedQuery, JiraSyncProfile, JiraSyncRun
from jira_workspace.services.query_service import build_issue_queryset
from jira_workspace.services.stats_service import build_dashboard_project_groups

DEFAULT_RANGE_KEY = "15d"
DEFAULT_USERNAME = "xchen17"
RANGE_DAYS = {
    "7d": 7,
    "15d": 15,
    "30d": 30,
    "90d": 90,
    "1y": 365,
}
RANGE_OPTIONS = ("7d", "15d", "30d", "90d", "1y", "all")


def _base_shell_context(*, title, breadcrumb, quick_action="Quick Action", env_label="ENV: LOCAL"):
    return {
        "shell_title": title,
        "shell_breadcrumb": breadcrumb,
        "shell_quick_action": quick_action,
        "shell_env_label": env_label,
        "shell_user": _resolve_username(),
    }


def _resolve_username():
    profile = (
        JiraSyncProfile.objects.filter(
            profile_type=JiraSyncProfile.ProfileType.MY_ISSUES,
            params_json__username__isnull=False,
        )
        .order_by("-is_default", "-updated_at")
        .first()
    )
    if profile:
        username = (profile.params_json or {}).get("username")
        if username:
            return username
    return DEFAULT_USERNAME


def _resolve_date_range(range_key):
    end = timezone.now()
    normalized = (range_key or DEFAULT_RANGE_KEY).lower()
    if normalized == "all":
        return normalized, None, end
    days = RANGE_DAYS.get(normalized, RANGE_DAYS[DEFAULT_RANGE_KEY])
    return normalized, end - timedelta(days=days), end


def dashboard(request):
    username = _resolve_username()
    range_key, start, end = _resolve_date_range(request.GET.get("range"))
    ticket_queryset = build_issue_queryset(
        username=username,
        start=start,
        end=end,
    )
    context = {
        "range_key": range_key,
        "range_options": RANGE_OPTIONS,
        "start": start.date() if start else None,
        "end": end.date(),
        "project_groups": build_dashboard_project_groups(
            username=username,
            start=start,
            end=end,
        ),
        "recent_issues": ticket_queryset[:5],
        "ticket_rows": ticket_queryset[:20],
        "active_source": "all",
        "active_project": "",
        "username": username,
    }
    context.update(
        _base_shell_context(
            title="Jira Dashboard",
            breadcrumb="Workspace / Jira / Dashboard",
            quick_action="Refresh Dashboard",
        )
    )
    return render(request, "jira_workspace/dashboard.html", context)


def dashboard_ticket_table(request):
    username = _resolve_username()
    range_key, start, end = _resolve_date_range(request.GET.get("range"))
    queryset = build_issue_queryset(
        username=username,
        source=request.GET.get("source", "all"),
        project_key=request.GET.get("project") or None,
        start=start,
        end=end,
    )
    return render(
        request,
        "jira_workspace/partials/ticket_table.html",
        {
            "ticket_rows": queryset[:30],
            "active_source": request.GET.get("source", "all"),
            "active_project": request.GET.get("project", ""),
            "range_key": range_key,
        },
    )


def queries(request):
    saved_queries = JiraSavedQuery.objects.select_related("profile").order_by(
        "-is_pinned", "-is_starred", "name"
    )
    context = {
        "saved_queries": saved_queries,
        "query_form": JiraSavedQueryForm(),
    }
    context.update(
        _base_shell_context(
            title="Jira Query",
            breadcrumb="Workspace / Jira / Query",
            quick_action="Run Query",
        )
    )
    return render(request, "jira_workspace/queries.html", context)


def profiles(request):
    profiles_qs = JiraSyncProfile.objects.order_by("-is_default", "name")
    sync_runs = JiraSyncRun.objects.select_related("profile").order_by("-started_at")[:20]
    context = {
        "profiles": profiles_qs,
        "sync_runs": sync_runs,
        "profile_form": JiraSyncProfileForm(),
    }
    context.update(
        _base_shell_context(
            title="Jira Sync",
            breadcrumb="Workspace / Jira / Sync",
            quick_action="Start Sync",
        )
    )
    return render(request, "jira_workspace/profiles.html", context)


def workspace_home(request):
    sync_runs = JiraSyncRun.objects.select_related("profile").order_by("-started_at")[:6]
    context = {
        "recent_runs": sync_runs,
        "workspace_cards": [
            {
                "title": "Jira Dashboard",
                "description": "Personal issue health, projects, and recent updates.",
                "href": "/jira/dashboard/",
            },
            {
                "title": "Jira Query",
                "description": "Saved filters, reusable views, and investigation flows.",
                "href": "/jira/query/",
            },
            {
                "title": "sync2pod",
                "description": "Profiles, execution state, and watch queue visibility.",
                "href": "/sync2pod/",
            },
            {
                "title": "Integrations",
                "description": "Catalog, contracts, readiness, and scan history.",
                "href": "/integrations/",
            },
        ],
    }
    context.update(
        _base_shell_context(
            title="Workspace",
            breadcrumb="Workspace / Home",
            quick_action="Open Tool",
        )
    )
    return render(request, "jira_workspace/workspace_home.html", context)


def issues(request):
    ticket_rows = build_issue_queryset(username=_resolve_username())[:20]
    context = {
        "ticket_rows": ticket_rows,
    }
    context.update(
        _base_shell_context(
            title="Jira Issues",
            breadcrumb="Workspace / Jira / Issues",
            quick_action="Bulk Action",
        )
    )
    return render(request, "jira_workspace/issues.html", context)


def sync(request):
    return profiles(request)


def query(request):
    return queries(request)


def sync2pod(request):
    context = {
        "sync2pod_metrics": [
            {"value": "0", "label": "Queued events"},
            {"value": "idle", "label": "Run state"},
            {"value": "n/a", "label": "Last throughput"},
        ]
    }
    context.update(
        _base_shell_context(
            title="sync2pod",
            breadcrumb="Workspace / sync2pod / Console",
            quick_action="Start Sync",
        )
    )
    return render(request, "jira_workspace/sync2pod.html", context)


def integrations(request):
    context = {
        "integration_groups": [
            {
                "name": "Issue Ops",
                "items": [
                    {"name": "Jira Issues", "status": "ready"},
                    {"name": "Jira Sync", "status": "ready"},
                ],
            },
            {
                "name": "Sync Ops",
                "items": [
                    {"name": "sync2pod", "status": "pending"},
                ],
            },
        ]
    }
    context.update(
        _base_shell_context(
            title="Integrations",
            breadcrumb="Workspace / Integrations / Catalog",
            quick_action="Refresh Catalog",
        )
    )
    return render(request, "jira_workspace/integrations.html", context)
