from django.contrib import admin

from .models import Sync2PodTask


@admin.register(Sync2PodTask)
class Sync2PodTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'namespace', 'pod', 'pod_dir', 'status', 'pid', 'created_at']
    list_filter  = ['status', 'namespace']
    search_fields = ['name', 'pod', 'source_dir']
