from django.urls import path

from . import views

app_name = "jira_workspace"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
]
