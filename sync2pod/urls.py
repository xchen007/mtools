from django.urls import path

from . import views

urlpatterns = [
    path('sync2pod/', views.sync2pod_list, name='sync2pod_list'),
    path('sync2pod/settings/', views.sync2pod_settings, name='sync2pod_settings'),
    path('sync2pod/status/', views.sync2pod_status_all, name='sync2pod_status_all'),
    path('sync2pod/create/', views.sync2pod_create, name='sync2pod_create'),
    path('sync2pod/kube-context/', views.sync2pod_kube_context, name='sync2pod_kube_context'),
    path('sync2pod/<int:task_id>/', views.sync2pod_detail, name='sync2pod_detail'),
    path('sync2pod/<int:task_id>/edit/', views.sync2pod_edit, name='sync2pod_edit'),
    path('sync2pod/<int:task_id>/start/', views.sync2pod_start, name='sync2pod_start'),
    path('sync2pod/<int:task_id>/stop/', views.sync2pod_stop, name='sync2pod_stop'),
    path('sync2pod/<int:task_id>/delete/', views.sync2pod_delete, name='sync2pod_delete'),
    path('sync2pod/<int:task_id>/logs/', views.sync2pod_logs, name='sync2pod_logs'),
]
