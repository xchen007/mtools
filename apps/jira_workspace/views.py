from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from jira_workspace.forms import (
    GlobalSyncPolicyForm,
    JiraConnectionForm,
    JiraIssueFilterForm,
    JiraSavedQueryForm,
    SyncScopeForm,
    Sync2PodProfileForm,
)
from jira_workspace.models import (
    GlobalSyncPolicy,
    IntegrationTool,
    JiraIssue,
    JiraScopeSyncReport,
    OperationLog,
    JiraSavedQuery,
    JiraSyncProfile,
    JiraSyncRun,
    SyncScope,
    Sync2PodWatchEvent,
    Sync2PodProfile,
    Sync2PodRun,
    WorkspaceStar,
)
from jira_workspace.services.integrations_service import IntegrationsService
from jira_workspace.services.jira_connection_service import JiraConnectionService
from jira_workspace.services.operation_log_service import OperationLogService
from jira_workspace.services.query_card_service import QueryCardService
from jira_workspace.services.query_service import (
    active_policy_issue_queryset,
    build_issue_filter_options,
    build_issue_queryset,
    current_global_sync_policy,
    normalize_issue_filters,
)
from jira_workspace.services.stats_service import (
    build_dashboard_project_groups,
    build_dashboard_summary,
)
from jira_workspace.services.star_service import StarService
from jira_workspace.services.sync_service import (
    PRIMARY_GLOBAL_SYNC_POLICY_NAME,
    SyncService,
)
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
LIVE_POLL_INTERVAL_MS = 2500
LIVE_ASSET_SUFFIXES = {".css", ".html", ".js", ".py"}
LIVE_ASSET_ROOTS = (
    "apps/jira_workspace",
    "static/jira_workspace",
    "templates/jira_workspace",
)


def _base_shell_context(
    *,
    title,
    breadcrumb,
    current_route_name,
    quick_action="Quick Action",
    env_label="ENV: LOCAL",
):
    workspace_service = WorkspaceService()
    username = _resolve_username()
    query_card_service = QueryCardService(username=username)
    query_cards = query_card_service.ensure_default_cards()
    query_card_filter_options = build_issue_filter_options(username=username)
    shell_navigation = workspace_service.build_shell_navigation(
        current_route_name=current_route_name
    )
    jira_connection = JiraConnectionService().get_active_connection()
    jira_browse_base_url = _jira_browse_base_url(jira_connection)
    return {
        "shell_title": title,
        "shell_breadcrumb": breadcrumb,
        "shell_quick_action": quick_action,
        "shell_env_label": env_label,
        "shell_user": username,
        "shell_asset_version": _build_asset_version(),
        "shell_rail_sections": workspace_service.build_rail_sections(),
        "shell_tools": shell_navigation["tools"],
        "shell_current_tool": shell_navigation["current_tool"],
        "shell_current_sections": shell_navigation["current_sections"],
        "shell_starred_items": shell_navigation["starred_items"],
        "query_cards": query_cards,
        "query_form": JiraSavedQueryForm(
            username=username,
            filter_options=query_card_filter_options,
        ),
        "query_card_filter_options": query_card_filter_options,
        "query_card_form_action": "create_card",
        "query_card_editor_open": False,
        "connection_form": JiraConnectionForm(instance=jira_connection),
        "jira_connection": jira_connection,
        "jira_browse_base_url": jira_browse_base_url,
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


def _build_policy_status_context():
    policy = current_global_sync_policy()
    if policy is None or policy.current_version_id is None:
        return {
            "sync_policy": None,
            "sync_policy_version": None,
            "sync_policy_scopes": [],
            "sync_required_failures": [],
            "sync_latest_successful_check": None,
        }

    scopes = list(policy.current_version.scopes.order_by("-is_required", "name"))
    failed_statuses = {SyncScope.RunStatus.FAILED, SyncScope.RunStatus.BLOCKED}
    latest_successful_check = None
    for scope in scopes:
        if scope.last_successful_check_at and (
            latest_successful_check is None
            or scope.last_successful_check_at > latest_successful_check
        ):
            latest_successful_check = scope.last_successful_check_at

    return {
        "sync_policy": policy,
        "sync_policy_version": policy.current_version,
        "sync_policy_scopes": scopes,
        "sync_required_failures": [
            scope
            for scope in scopes
            if scope.is_required and scope.last_run_status in failed_statuses
        ],
        "sync_latest_successful_check": latest_successful_check,
    }


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
        "jira_has_cached_data": active_policy_issue_queryset().exists(),
    }
    context.update(_build_policy_status_context())
    context.update(
        _base_shell_context(
            title="Jira Dashboard",
            breadcrumb="Workspace / Jira / Dashboard",
            current_route_name="dashboard",
            quick_action="Refresh Dashboard",
        )
    )
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Jira Dashboard",
        route=reverse("jira_workspace:dashboard"),
        group_key="jira",
        next_url=request.get_full_path(),
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
            "jira_browse_base_url": _jira_browse_base_url(
                JiraConnectionService().get_active_connection()
            ),
            "active_source": request.GET.get("source", "all"),
            "active_project": request.GET.get("project", ""),
            "range_key": range_key,
            "rich_table_id": "jira-dashboard-tickets",
            "rich_table_persist_scope": "/jira/dashboard/",
            "rich_table_row_click": "drawer",
        },
    )


def live_state(request):
    return JsonResponse(
        {
            "asset_version": _build_asset_version(),
            "data_version": _build_data_version(),
            "poll_interval_ms": LIVE_POLL_INTERVAL_MS,
        }
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
            current_route_name="workspace_home",
            quick_action="Open Tool",
        )
    )
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Workspace Home",
        route="/workspace/",
        group_key="workspace",
        next_url=request.get_full_path(),
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
    )[:240]
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
    }
    context.update(
        _base_shell_context(
            title="Jira Issues",
            breadcrumb="Workspace / Jira / Issues",
            current_route_name="issues",
            quick_action="Bulk Action",
        )
    )
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Jira Issues",
        route=reverse("jira_workspace:issues"),
        group_key="jira",
        next_url=request.get_full_path(),
    )
    return render(request, "jira_workspace/issues.html", context)


def sync(request):
    sync_service = SyncService()
    connection_service = JiraConnectionService()
    operation_log_service = OperationLogService()
    jira_connection = connection_service.get_active_connection()
    connection_form = JiraConnectionForm(instance=jira_connection)
    sync_fallback_url = reverse("jira_workspace:sync")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_connection":
            connection_form = JiraConnectionForm(request.POST, instance=jira_connection)
            if connection_form.is_valid():
                jira_connection = connection_form.save()
                return redirect(
                    _safe_next_url(
                        request,
                        request.POST.get("next"),
                        fallback=sync_fallback_url,
                    )
                )
        elif action == "test_connection":
            connection_id = request.POST.get("connection_id")
            if jira_connection and str(jira_connection.id) == str(connection_id):
                try:
                    jira_connection = connection_service.test_connection(jira_connection)
                except Exception:
                    pass
            return redirect(
                _safe_next_url(
                    request,
                    request.POST.get("next"),
                    fallback=sync_fallback_url,
                )
            )
        elif action == "rebuild_policy":
            policy = get_object_or_404(
                GlobalSyncPolicy,
                pk=request.POST.get("policy_id"),
                name=PRIMARY_GLOBAL_SYNC_POLICY_NAME,
            )
            try:
                sync_service.rebuild_policy_version(policy=policy)
            except Exception:
                messages.error(request, "Unable to rebuild the sync policy version.")
            return redirect(reverse("jira_workspace:sync"))
        elif action == "run_scope_incremental":
            policy = sync_service.ensure_global_policy()
            scope = get_object_or_404(
                SyncScope,
                pk=request.POST.get("scope_id"),
                policy_version_id=policy.current_version_id,
            )
            try:
                sync_service.run_scope_incremental(scope)
            except Exception:
                messages.error(request, "Unable to run incremental scope sync.")
            return redirect(reverse("jira_workspace:sync"))
        elif action == "run_scope_full":
            policy = sync_service.ensure_global_policy()
            scope = get_object_or_404(
                SyncScope,
                pk=request.POST.get("scope_id"),
                policy_version_id=policy.current_version_id,
            )
            try:
                sync_service.run_scope_full(scope)
            except Exception:
                messages.error(request, "Unable to run full scope sync.")
            return redirect(reverse("jira_workspace:sync"))
        elif action == "run_due_scopes":
            try:
                sync_service.run_due_scopes()
            except Exception:
                messages.error(request, "Unable to run due scope syncs.")
            return redirect(reverse("jira_workspace:sync"))
        elif action == "save_policy":
            get_object_or_404(
                GlobalSyncPolicy,
                pk=request.POST.get("policy_id"),
                name=PRIMARY_GLOBAL_SYNC_POLICY_NAME,
            )
            return redirect(reverse("jira_workspace:sync"))
        elif action == "add_scope":
            policy = get_object_or_404(
                GlobalSyncPolicy,
                pk=request.POST.get("policy_id"),
                name=PRIMARY_GLOBAL_SYNC_POLICY_NAME,
            )
            scope_form = SyncScopeForm(request.POST)
            if scope_form.is_valid():
                strategy_json = dict(policy.strategy_json or {})
                strategy_json["scopes"] = list(strategy_json.get("scopes") or [])
                strategy_json["scopes"].append(scope_form.to_strategy_scope())
                try:
                    sync_service.apply_policy_strategy(
                        policy=policy,
                        strategy_json=strategy_json,
                    )
                    return redirect(reverse("jira_workspace:sync"))
                except Exception:
                    messages.error(request, "Unable to add sync scope.")

    sync_status = sync_service.build_sync_status()
    has_active_sync = any(
        run.status in {JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING}
        for run in sync_status["recent_runs"]
    )
    has_active_full_sync = any(
        run.run_type == JiraSyncRun.RunType.FULL
        and run.status in {JiraSyncRun.Status.QUEUED, JiraSyncRun.Status.RUNNING}
        for run in sync_status["recent_runs"]
    )
    global_policy = sync_service.ensure_global_policy()
    policy_scopes = []
    scope_sync_reports = JiraScopeSyncReport.objects.none()
    if global_policy and global_policy.current_version_id:
        policy_scopes = list(
            SyncScope.objects.filter(policy_version_id=global_policy.current_version_id)
            .order_by("-is_required", "name")
        )
        scope_sync_reports = (
            JiraScopeSyncReport.objects.select_related("scope", "policy_version")
            .filter(policy_version_id=global_policy.current_version_id)
            .order_by("-started_at", "-id")[:20]
        )
    context = {
        "sync_runs": sync_status["recent_runs"],
        "has_active_sync": has_active_sync,
        "has_active_full_sync": has_active_full_sync,
        "latest_failed_run": sync_status["latest_failure"],
        "jira_blocker_message": sync_status["blocker_message"],
        "has_external_blocker": sync_status["has_external_blocker"],
        "connection_form": connection_form,
        "jira_connection": jira_connection,
        "recent_operation_logs": operation_log_service.recent_logs(
            tool=OperationLog.Tool.JIRA_SYNC,
        ),
        "global_policy": global_policy,
        "policy_scopes": policy_scopes,
        "policy_form": GlobalSyncPolicyForm(instance=global_policy) if global_policy else GlobalSyncPolicyForm(),
        "scope_form": SyncScopeForm(),
        "scope_sync_reports": scope_sync_reports,
    }
    context.update(
        _base_shell_context(
            title="Jira Sync",
            breadcrumb="Workspace / Jira / Sync",
            current_route_name="sync",
            quick_action="Start Sync",
        )
    )
    context["connection_form"] = connection_form
    context["jira_connection"] = jira_connection
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Jira Sync",
        route=reverse("jira_workspace:sync"),
        group_key="jira",
        next_url=request.get_full_path(),
    )
    return render(request, "jira_workspace/sync.html", context)

def query(request):
    username = _resolve_username()
    query_card_service = QueryCardService(username=username)
    operation_log_service = OperationLogService()
    sync_status = SyncService().build_sync_status()
    query_card_service.ensure_default_cards()
    filter_options = build_issue_filter_options(username=username)
    opening_new_editor = request.GET.get("editor") == "new"
    selected_query = query_card_service.resolve_card(
        card_id=request.GET.get("card"),
        legacy_saved_query_id=request.GET.get("saved_query"),
    )
    query_form = (
        JiraSavedQueryForm(username=username, filter_options=filter_options)
        if opening_new_editor
        else JiraSavedQueryForm(
            instance=selected_query,
            username=username,
            filter_options=filter_options,
        ) if selected_query else JiraSavedQueryForm(
            username=username,
            filter_options=filter_options,
        )
    )
    editor_open = opening_new_editor
    form_action = "create_card" if opening_new_editor or not selected_query else "update_card"

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"create_card", "update_card", "save_query"}:
            submitted_card_id = request.POST.get("card_id") or request.POST.get("saved_query_id")
            query_instance = (
                query_card_service.resolve_card(card_id=submitted_card_id)
                if action == "update_card" or submitted_card_id
                else None
            )
            query_form = JiraSavedQueryForm(
                request.POST,
                instance=query_instance,
                username=username,
                filter_options=filter_options,
            )
            if query_form.is_valid():
                saved_query = query_form.save()
                return redirect(f"{reverse('jira_workspace:query')}?card={saved_query.id}")
            selected_query = query_instance or selected_query
            editor_open = True
            form_action = "update_card" if query_instance else "create_card"
        elif action == "duplicate_card":
            query_instance = query_card_service.resolve_card(card_id=request.POST.get("card_id"))
            if query_instance:
                duplicate = query_card_service.duplicate_card(query_instance)
                return redirect(f"{reverse('jira_workspace:query')}?card={duplicate.id}")
            return redirect("jira_workspace:query")
        elif action == "delete_card":
            query_instance = query_card_service.resolve_card(card_id=request.POST.get("card_id"))
            if query_instance:
                fallback = query_card_service.delete_card(query_instance)
                if fallback:
                    return redirect(f"{reverse('jira_workspace:query')}?card={fallback.id}")
            return redirect("jira_workspace:query")
        elif action == "run_card":
            query_instance = query_card_service.resolve_card(card_id=request.POST.get("card_id"))
            if query_instance:
                query_card_service.run_card(query_instance)
                return redirect(f"{reverse('jira_workspace:query')}?card={query_instance.id}")
            return redirect("jira_workspace:query")

    saved_queries = query_card_service.list_cards()
    for saved_query in saved_queries:
        saved_query.result_count = len(query_card_service.evaluate_card(saved_query))
        saved_query.query_preview = saved_query.jql_text or _format_query_filters(
            saved_query.filters_json
        )
        saved_query.star = _star_button_context(
            kind=WorkspaceStar.Kind.SAVED_QUERY,
            label=saved_query.name,
            route=f"{reverse('jira_workspace:query')}?card={saved_query.id}",
            group_key="jira",
            object_id=str(saved_query.id),
            next_url=request.get_full_path(),
        )
        if selected_query and saved_query.id == selected_query.id:
            selected_query.star = saved_query.star
            selected_query.result_count = saved_query.result_count
            selected_query.query_preview = saved_query.query_preview
    context = query_card_service.build_context(
        selected_card=selected_query,
        form=query_form,
        editor_open=editor_open,
        form_action=form_action,
    )
    context["saved_queries"] = saved_queries
    context["query_cards"] = saved_queries
    context["query_card_filter_options"] = filter_options
    selected_filters = (context["selected_query"].filters_json if context["selected_query"] else {}) or {}
    context["selected_query_filters"] = [
        {"label": "Project Filter", "value": ", ".join(selected_filters.get("project", [])) or "Any"},
        {"label": "Status Filter", "value": ", ".join(selected_filters.get("status", [])) or "Any"},
    ]
    selected_log_target_id = str(selected_query.id) if selected_query else ""
    context["recent_operation_logs"] = operation_log_service.recent_logs(
        tool=OperationLog.Tool.JIRA_QUERY,
        target_type="query_card",
        target_id=selected_log_target_id,
    ) if selected_log_target_id else operation_log_service.recent_logs(
        tool=OperationLog.Tool.JIRA_QUERY,
    )
    context["starred_query_ids"] = set(
        WorkspaceStar.objects.filter(
            kind=WorkspaceStar.Kind.SAVED_QUERY
        ).values_list("object_id", flat=True)
    )
    context["jira_blocker_message"] = sync_status["blocker_message"]
    context["jira_latest_failure"] = sync_status["latest_failure"]
    context["has_external_blocker"] = sync_status["has_external_blocker"]
    context["jira_has_cached_data"] = active_policy_issue_queryset().exists()
    context.update(_build_policy_status_context())
    base_context = _base_shell_context(
        title="Jira Dashboard",
        breadcrumb="Workspace / Jira / Dashboard",
        current_route_name="query",
        quick_action="Run Query",
    )
    base_context.update(context)
    context = base_context
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Jira Dashboard",
        route=reverse("jira_workspace:query"),
        group_key="jira",
        next_url=request.get_full_path(),
    )
    return render(request, "jira_workspace/queries.html", context)


def sync2pod(request):
    sync2pod_service = Sync2PodService()
    operation_log_service = OperationLogService()
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

    selected_sync2pod_profile = _resolve_selected_sync2pod_profile(request.GET.get("profile"))
    sync2pod_status = sync2pod_service.build_page_context()
    if selected_sync2pod_profile:
        sync2pod_status["active_profile"] = selected_sync2pod_profile
    sync2pod_profiles = list(sync2pod_status["profiles"])
    for profile in sync2pod_profiles:
        profile.star = _star_button_context(
            kind=WorkspaceStar.Kind.SYNC2POD_PROFILE,
            label=profile.name,
            route=f"/sync2pod/?profile={profile.id}",
            group_key="sync2pod",
            object_id=str(profile.id),
            next_url=request.get_full_path(),
        )
    latest_run = sync2pod_status["latest_run"]
    latest_state = latest_run.status if latest_run else "idle"
    latest_throughput = sync2pod_status["latest_output"] or "No completed runs yet."
    context = {
        "sync2pod_profiles": sync2pod_profiles,
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
        "starred_sync2pod_profile_ids": set(
            WorkspaceStar.objects.filter(
                kind=WorkspaceStar.Kind.SYNC2POD_PROFILE
            ).values_list("object_id", flat=True)
        ),
        "sync2pod_metrics": [
            {"value": sync2pod_status["queue_count"], "label": "Queued Watch Events"},
            {"value": latest_state, "label": "Run State"},
            {"value": latest_throughput, "label": "Last Throughput"},
        ],
        "recent_operation_logs": operation_log_service.recent_logs(
            tool=OperationLog.Tool.SYNC2POD,
            target_type="sync2pod_profile",
            target_id=str(sync2pod_status["active_profile"].id) if sync2pod_status["active_profile"] else "",
        ) if sync2pod_status["active_profile"] else operation_log_service.recent_logs(
            tool=OperationLog.Tool.SYNC2POD,
        ),
    }
    context.update(
        _base_shell_context(
            title="sync2pod",
            breadcrumb="Workspace / sync2pod / Console",
            current_route_name="sync2pod",
            quick_action="Start Sync",
        )
    )
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="sync2pod",
        route="/sync2pod/",
        group_key="sync2pod",
        next_url=request.get_full_path(),
    )
    return render(request, "jira_workspace/sync2pod.html", context)


def integrations(request):
    integrations_service = IntegrationsService()
    operation_log_service = OperationLogService()
    if request.method == "POST" and request.POST.get("action") == "run_scan":
        tool = get_object_or_404(IntegrationTool, pk=request.POST.get("tool_id"))
        integrations_service.run_scan(tool=tool, triggered_by=_resolve_username())
        return redirect("/integrations/")

    catalog = integrations_service.build_catalog(query=request.GET.get("query", ""))
    context = {
        "integration_groups": catalog["groups"],
        "integration_contract_rows": catalog["contract_rows"],
        "integration_recent_runs": catalog["recent_runs"],
        "integration_query": catalog["query"],
        "integration_tools": list(IntegrationTool.objects.order_by("group", "name")),
        "recent_operation_logs": operation_log_service.recent_logs(
            tool=OperationLog.Tool.INTEGRATIONS,
        ),
    }
    context.update(
        _base_shell_context(
            title="Integrations",
            breadcrumb="Workspace / Integrations / Catalog",
            current_route_name="integrations",
            quick_action="Refresh Catalog",
        )
    )
    context["page_star"] = _star_button_context(
        kind=WorkspaceStar.Kind.ROUTE,
        label="Integrations",
        route="/integrations/",
        group_key="integrations",
        next_url=request.get_full_path(),
    )
    return render(request, "jira_workspace/integrations.html", context)


def logs(request):
    operation_log_service = OperationLogService()
    tool = request.GET.get("tool", "")
    status = request.GET.get("status", "")
    action = request.GET.get("action", "")
    context = {
        "operation_logs": operation_log_service.list_logs(
            tool=tool,
            status=status,
            action=action,
        ),
        "log_filter_tool": tool,
        "log_filter_status": status,
        "log_filter_action": action,
        "log_tool_choices": OperationLog.Tool.choices,
        "log_status_choices": OperationLog.Status.choices,
        "log_action_choices": sorted(
            set(OperationLog.objects.order_by().values_list("action", flat=True))
        ),
    }
    context.update(
        _base_shell_context(
            title="Operation Logs",
            breadcrumb="Workspace / Logs",
            current_route_name="logs",
            quick_action="Filter Logs",
        )
    )
    return render(request, "jira_workspace/logs.html", context)


def log_detail(request, log_id):
    log = get_object_or_404(OperationLog, pk=log_id)
    context = {
        "operation_log": log,
    }
    context.update(
        _base_shell_context(
            title="Operation Logs",
            breadcrumb="Workspace / Logs / Detail",
            current_route_name="log_detail",
            quick_action="Back to Logs",
        )
    )
    return render(request, "jira_workspace/log_detail.html", context)


def toggle_star(request):
    if request.method != "POST":
        return redirect("/workspace/")

    next_url = request.POST.get("next") or "/workspace/"
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/workspace/"

    StarService().toggle(
        kind=request.POST.get("kind") or WorkspaceStar.Kind.ROUTE,
        label=request.POST.get("label") or "Untitled",
        route=request.POST.get("route") or next_url,
        group_key=request.POST.get("group_key") or "workspace",
        object_id=request.POST.get("object_id") or "",
    )
    return redirect(next_url)


def _sync_url_for_profile(profile):
    sync_url = reverse("jira_workspace:sync")
    if profile:
        return f"{sync_url}?profile={profile.id}"
    return sync_url


def _safe_next_url(request, next_url, *, fallback):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback


def _jira_browse_base_url(connection=None):
    configured_url = getattr(settings, "JIRA_WEB_BASE_URL", "").strip().rstrip("/")
    if configured_url:
        return configured_url

    base_url = (
        getattr(connection, "base_url", "")
        or getattr(settings, "JIRA_API_BASE_URL", "")
    ).strip().rstrip("/")
    if not base_url:
        return ""

    parsed = urlparse(base_url)
    hostname = parsed.hostname or ""
    if hostname.split(".", 1)[0].endswith("-cli"):
        browse_hostname = hostname.replace("-cli.", ".", 1)
        netloc = browse_hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return parsed._replace(netloc=netloc).geturl().rstrip("/")
    return base_url


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


def _resolve_selected_sync2pod_profile(profile_id):
    if not profile_id:
        return None
    try:
        return Sync2PodProfile.objects.get(pk=profile_id)
    except (Sync2PodProfile.DoesNotExist, ValueError, TypeError):
        return None


def _star_button_context(*, kind, label, route, group_key, next_url, object_id=""):
    return {
        "kind": kind,
        "label": label,
        "route": route,
        "group_key": group_key,
        "object_id": object_id,
        "next": next_url,
        "is_starred": StarService().is_starred(
            kind=kind,
            route=route,
            object_id=object_id,
        ),
    }


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


def _format_query_filters(filters_json):
    filters_json = dict(filters_json or {})
    parts = []

    def _list_value(key):
        value = filters_json.get(key)
        if isinstance(value, (list, tuple)):
            return [item for item in value if item]
        return [value] if value else []

    source = filters_json.get("source")
    if source:
        parts.append(f"source = {source}")
    reporter = filters_json.get("reporter")
    if reporter:
        parts.append(f"reporter = {reporter}")
    assignee = filters_json.get("assignee")
    if assignee:
        parts.append(f"assignee = {assignee}")
    project = _list_value("project")
    if project:
        parts.append(f"project in ({', '.join(project)})")
    status = _list_value("status")
    if status:
        parts.append(f"status in ({', '.join(status)})")
    labels = _list_value("labels")
    if labels:
        parts.append(f"labels include {', '.join(labels)}")
    sprint = filters_json.get("sprint")
    if sprint:
        parts.append(f"sprint = {sprint}")
    issue_type = _list_value("issue_type")
    if issue_type:
        parts.append(f"type in ({', '.join(issue_type)})")
    priority = _list_value("priority")
    if priority:
        parts.append(f"priority in ({', '.join(priority)})")
    search = filters_json.get("search")
    if search:
        parts.append(f"search contains {search}")
    return " and ".join(parts) or "all assigned or reported issues"


def _build_asset_version():
    latest_mtime = 0
    for root in LIVE_ASSET_ROOTS:
        root_path = Path(settings.BASE_DIR / root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix not in LIVE_ASSET_SUFFIXES:
                continue
            latest_mtime = max(latest_mtime, int(path.stat().st_mtime_ns))
    return str(latest_mtime)


def _build_data_version():
    candidates = [
        JiraIssue.objects.aggregate(value=Max("last_seen_at"))["value"],
        JiraIssue.objects.aggregate(value=Max("updated_at"))["value"],
        JiraSyncRun.objects.aggregate(value=Max("started_at"))["value"],
        Sync2PodRun.objects.aggregate(value=Max("started_at"))["value"],
        Sync2PodWatchEvent.objects.aggregate(value=Max("created_at"))["value"],
        Sync2PodWatchEvent.objects.aggregate(value=Max("processed_at"))["value"],
    ]
    latest = max((value for value in candidates if value), default=None)
    if latest is None:
        return "0"
    return str(int(latest.timestamp() * 1000))
