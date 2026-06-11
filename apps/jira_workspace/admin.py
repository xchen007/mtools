from django.contrib import admin

from .models import JiraIssue, JiraIssueMetric, JiraSavedQuery, JiraSyncProfile, JiraSyncRun

admin.site.register(JiraIssue)
admin.site.register(JiraIssueMetric)
admin.site.register(JiraSyncProfile)
admin.site.register(JiraSyncRun)
admin.site.register(JiraSavedQuery)
