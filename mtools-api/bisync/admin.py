from django.contrib import admin

from .models import BisyncTarget, BisyncTask


@admin.register(BisyncTask)
class BisyncTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_dir', 'interval', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(BisyncTarget)
class BisyncTargetAdmin(admin.ModelAdmin):
    list_display = ['task', 'target_dir', 'status', 'pid', 'created_at']
    list_filter = ['status']
    readonly_fields = ['status', 'pid', 'created_at', 'updated_at']
