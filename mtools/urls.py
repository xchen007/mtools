"""mtools URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from jira_workspace import views as jira_workspace_views
urlpatterns = [
    path('', lambda request: redirect('/workspace/', permanent=False)),
    path('admin/', admin.site.urls),
    path('jira/', include('jira_workspace.urls', namespace='jira_workspace')),
    path('workspace/', jira_workspace_views.workspace_home),
    path('sync2pod/', jira_workspace_views.sync2pod),
    path('integrations/', jira_workspace_views.integrations),

]
