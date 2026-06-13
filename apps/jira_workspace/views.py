from datetime import timedelta

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from jira_workspace.forms import (
    JiraIssueFilterForm,
    JiraSavedQueryForm,
    JiraSyncProfileForm,
    Sync2PodProfileForm,
)
from jira_workspace.models import JiraIssue, JiraSavedQuery, JiraSyncProfile, JiraSyncRun, Sync2PodProfile, Sync2PodRun
from jira_workspace.services.integrations_service import IntegrationsService
from jira_workspace.services.query_service import (
    build_issue_filter_options,
    build_issue_queryset,
    normalize_issue_filters,
)
from jira_workspace.services.stats_service import (
    build_dashboard_project_groups,
    build_dashboard_summary,
)
from jira_workspace.services.sync_service import SyncService
from jira_workspace.services.sync2pod_service import Sync2PodService
from jira_workspace.services.workspace_service import WorkspaceService

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
    workspace_service = WorkspaceService()
    return {
        "shell_title": title,
        "shell_breadcrumb": breadcrumb,
        "shell_quick_action": quick_action,
        "shell_env_label": env_label,
        "shell_user": _resolve_username(),
        "shell_rail_sections": workspace_service.build_rail_sections(),
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
    sync_status = SyncService().build_sync_status()
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
        "dashboard_metrics": build_dashboard_summary(
            username=username,
            start=start,
            end=end,
        ),
        "jira_blocker_message": sync_status["blocker_message"],
        "jira_latest_failure": sync_status["latest_failure"],
        "has_external_blocker": sync_status["has_external_blocker"],
        "jira_has_cached_data": ticket_queryset.exists(),
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
    return redirect("jira_workspace:query")


def profiles(request):
    return redirect("jira_workspace:sync")


def workspace_home(request):
    workspace_service = WorkspaceService()
    context = workspace_service.build_home_context()
    context["workspace_cards"] = [
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
    ]
    context.update(
        _base_shell_context(
            title="Workspace",
            breadcrumb="Workspace / Home",
            quick_action="Open Tool",
        )
    )
    return render(request, "jira_workspace/workspace_home.html", context)


def issues(request):
    username = _resolve_username()
    filter_options = build_issue_filter_options(username=username)
    normalized_filters = normalize_issue_filters(
        username=username,
        source=request.GET.get("source", "all"),
        project_key=request.GET.get("project"),
        status=request.GET.get("status"),
        search=request.GET.get("query"),
        sort_by=request.GET.get("sort_by", "updated_at"),
        sort_order=request.GET.get("sort_order", "desc"),
    )
    ticket_rows = build_issue_queryset(
        **normalized_filters,
    )[:20]
    selected_issue = None
    selected_issue_key = (request.GET.get("issue") or "").strip()
    if selected_issue_key:
        selected_issue = JiraIssue.objects.filter(issue_key=selected_issue_key).first()
    if selected_issue is None:
        selected_issue = ticket_rows[0] if ticket_rows else None
    context = {
        "ticket_rows": ticket_rows,
        "saved_queries": JiraSavedQuery.objects.select_related("profile").order_by(
            "-is_pinned", "-is_starred", "name"
        )[:6],
        "issue_filter_options": filter_options,
        "issue_filter_form": JiraIssueFilterForm(
            initial={
                "source": normalized_filters["source"],
                "project": normalized_filters["project_key"],
                "status": normalized_filters["status"],
                "sort_by": normalized_filters["sort_by"],
                "sort_order": normalized_filters["sort_order"],
                "query": normalized_filters["search"],
            },
            filter_options=filter_options,
        ),
        "issue_filters": {
            "search": normalized_filters["search"],
            "project": normalized_filters["project_key"],
            "status": normalized_filters["status"],
            "source": normalized_filters["source"],
        },
        "selected_issue": selected_issue,
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
    sync_service = SyncService()
    selected_profile = _resolve_selected_profile(request.GET.get("profile"))
    profile_form = JiraSyncProfileForm(instance=selected_profile) if selected_profile else JiraSyncProfileForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_profile":
            profile_instance = _resolve_selected_profile(request.POST.get("profile_id"))
            profile_form = JiraSyncProfileForm(request.POST, instance=profile_instance)
            if profile_form.is_valid():
                profile = profile_form.save(commit=False)
                if profile.is_default:
                    JiraSyncProfile.objects.filter(is_default=True).exclude(pk=profile.pk).update(is_default=False)
                profile.save()
                return redirect(f"{reverse('jira_workspace:sync')}?profile={profile.id}")
        elif action == "run_sync":
            profile = get_object_or_404(JiraSyncProfile, pk=request.POST.get("profile_id"))
            run_type = request.POST.get("run_type")
            try:
                if run_type == JiraSyncRun.RunType.FULL:
                    sync_service.full_sync(profile)
                else:
                    sync_service.incremental_sync(profile)
            except Exception:
                pass
            return redirect(f"{reverse('jira_workspace:sync')}?profile={profile.id}")

    profiles_qs = JiraSyncProfile.objects.order_by("-is_default", "name")
    if selected_profile is None:
        selected_profile = profiles_qs.first()
        if not profile_form.is_bound:
            profile_form = JiraSyncProfileForm(instance=selected_profile) if selected_profile else JiraSyncProfileForm()

    sync_status = sync_service.build_sync_status()
    context = {
        "profiles": profiles_qs,
        "sync_runs": sync_status["recent_runs"],
        "latest_failed_run": sync_status["latest_failure"],
        "jira_blocker_message": sync_status["blocker_message"],
        "has_external_blocker": sync_status["has_external_blocker"],
        "profile_form": profile_form,
        "selected_profile": selected_profile,
    }
    context.update(
        _base_shell_context(
            title="Jira Sync",
            breadcrumb="Workspace / Jira / Sync",
            quick_action="Start Sync",
        )
    )
    return render(request, "jira_workspace/sync.html", context)


def query(request):
    saved_queries = JiraSavedQuery.objects.select_related("profile").order_by(
        "-is_pinned", "-is_starred", "name"
    )
    selected_query = _resolve_selected_query(request.GET.get("saved_query"), saved_queries)
    query_form = JiraSavedQueryForm(instance=selected_query) if selected_query else JiraSavedQueryForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_query":
            query_instance = _resolve_selected_query(
                request.POST.get("saved_query_id"),
                saved_queries,
            )
            query_form = JiraSavedQueryForm(request.POST, instance=query_instance)
            if query_form.is_valid():
                saved_query = query_form.save()
                return redirect(f"{reverse('jira_workspace:query')}?saved_query={saved_query.id}")
            selected_query = query_instance or selected_query

    selected_filters = (selected_query.filters_json if selected_query else {}) or {}
    query_rows = _build_saved_query_results(selected_query)
    context = {
        "saved_queries": saved_queries,
        "selected_query": selected_query,
        "selected_query_filters": [
            {"label": "Project Filter", "value": ", ".join(selected_filters.get("project", [])) or "Any"},
            {"label": "Status Filter", "value": ", ".join(selected_filters.get("status", [])) or "Any"},
        ],
        "query_form": query_form,
        "query_rows": query_rows,
    }
    context.update(
        _base_shell_context(
            title="Jira Query",
            breadcrumb="Workspace / Jira / Query",
            quick_action="Run Query",
        )
    )
    return render(request, "jira_workspace/queries.html", context)


def sync2pod(request):
    sync2pod_service = Sync2PodService()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_profile":
            sync2pod_service.upsert_profile(request.POST)
            return redirect("jira_workspace:sync2pod")
        if action == "start_sync":
            profile = get_object_or_404(Sync2PodProfile, pk=request.POST.get("profile_id"))
            sync2pod_service.create_run(
                profile=profile,
                trigger=Sync2PodRun.Trigger.MANUAL,
            )
            return redirect("jira_workspace:sync2pod")

    sync2pod_status = sync2pod_service.build_page_context()
    latest_run = sync2pod_status["latest_run"]
    latest_state = latest_run.status if latest_run else "idle"
    latest_throughput = sync2pod_status["latest_output"] or "No completed runs yet."
    context = {
        "sync2pod_profiles": sync2pod_status["profiles"],
        "sync2pod_runs": sync2pod_status["runs"],
        "sync2pod_queued_events": sync2pod_status["queued_events"],
        "sync2pod_latest_failure": sync2pod_status["latest_failure"],
        "sync2pod_capability": sync2pod_status["capability"],
        "sync2pod_error_messages": sync2pod_status["error_messages"],
        "sync2pod_profile_form": Sync2PodProfileForm(instance=sync2pod_status["active_profile"]),
        "sync2pod_active_profile": sync2pod_status["active_profile"],
        "sync2pod_latest_run": latest_run,
        "sync2pod_strategy_items": sync2pod_status["strategy_items"],
        "sync2pod_archive_items": sync2pod_status["archive_items"],
        "sync2pod_safety_items": sync2pod_status["safety_items"],
        "sync2pod_metrics": [
            {"value": sync2pod_status["queue_count"], "label": "Queued Watch Events"},
            {"value": latest_state, "label": "Run State"},
            {"value": latest_throughput, "label": "Last Throughput"},
        ],
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
    catalog = IntegrationsService().build_catalog(query=request.GET.get("query", ""))
    context = {
        "integration_groups": catalog["groups"],
        "integration_contract_rows": catalog["contract_rows"],
        "integration_recent_runs": catalog["recent_runs"],
        "integration_query": catalog["query"],
    }
    context.update(
        _base_shell_context(
            title="Integrations",
            breadcrumb="Workspace / Integrations / Catalog",
            quick_action="Refresh Catalog",
        )
    )
    return render(request, "jira_workspace/integrations.html", context)


def _resolve_selected_query(query_id, queryset):
    if not query_id:
        return queryset.first()
    try:
        return queryset.get(pk=query_id)
    except (JiraSavedQuery.DoesNotExist, ValueError, TypeError):
        return queryset.first()


def _resolve_selected_profile(profile_id):
    if not profile_id:
        return None
    try:
        return JiraSyncProfile.objects.get(pk=profile_id)
    except (JiraSyncProfile.DoesNotExist, ValueError, TypeError):
        return None


def _build_saved_query_results(saved_query):
    if not saved_query:
        return []

    username = _resolve_username()
    filters_json = dict(saved_query.filters_json or {})
    normalized_filters = normalize_issue_filters(
        username=username,
        source="all",
        project_key=(filters_json.get("project") or [""])[0],
        status=(filters_json.get("status") or [""])[0],
        search="",
        sort_by=saved_query.sort_by,
        sort_order=saved_query.sort_order,
    )
    return list(build_issue_queryset(**normalized_filters)[:20])
