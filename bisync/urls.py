from django.urls import path

from . import views

urlpatterns = [
    path('bisync/', views.bisync_list, name='bisync_list'),
    path('bisync/open/', views.bisync_open_path, name='bisync_open_path'),
    path('bisync/status/', views.bisync_status_all, name='bisync_status_all'),
    path('bisync/create/', views.bisync_create, name='bisync_create'),
    path('bisync/<int:task_id>/', views.bisync_detail, name='bisync_detail'),
    path('bisync/<int:task_id>/edit/',   views.bisync_edit_task,   name='bisync_edit_task'),
    path('bisync/<int:task_id>/delete/', views.bisync_delete_task, name='bisync_delete_task'),
    path('bisync/<int:task_id>/add-target/', views.bisync_add_target, name='bisync_add_target'),
    path('bisync/<int:task_id>/start-all/', views.bisync_start_all, name='bisync_start_all'),
    path('bisync/<int:task_id>/stop-all/',  views.bisync_stop_all,  name='bisync_stop_all'),
    # target-level operations
    path('bisync/target/<int:target_id>/start/',  views.target_start,    name='target_start'),
    path('bisync/target/<int:target_id>/stop/',   views.target_stop,     name='target_stop'),
    path('bisync/target/<int:target_id>/delete/', views.target_delete,   name='target_delete'),
    path('bisync/target/<int:target_id>/reset/',  views.target_reset,    name='target_reset'),
    path('bisync/target/<int:target_id>/',        views.target_log_page, name='target_log_page'),
    path('bisync/target/<int:target_id>/logs/',   views.target_logs_json, name='target_logs_json'),
]
