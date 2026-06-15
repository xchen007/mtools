from django.urls import path

from . import views

app_name = "jira_workspace"

urlpatterns = [
    path("star/toggle/", views.toggle_star, name="toggle_star"),
    path("logs/", views.logs, name="logs"),
    path("logs/<int:log_id>/", views.log_detail, name="log_detail"),
    path("workspace/", views.workspace_home, name="workspace_home"),
    path("live-state/", views.live_state, name="live_state"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/tickets/", views.dashboard_ticket_table, name="dashboard_ticket_table"),
    path("queries/", views.queries, name="queries"),
    path("profiles/", views.profiles, name="profiles"),
    path("query/", views.query, name="query"),
    path("issues/", views.issues, name="issues"),
    path("sync/", views.sync, name="sync"),
    path("sync2pod/", views.sync2pod, name="sync2pod"),
    path("integrations/", views.integrations, name="integrations"),
]
