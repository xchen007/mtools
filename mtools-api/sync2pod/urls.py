from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .consumers import Sync2PodTaskLogConsumer

router = DefaultRouter()
router.register(r'tasks', views.Sync2PodTaskViewSet, basename='sync2pod-task')

kube_ctx = views.Sync2PodKubeContextView.as_view({'get': 'list'})
cfg_get  = views.Sync2PodConfigView.as_view({'get': 'list', 'patch': 'partial_update'})

urlpatterns = router.urls + [
    path('kube-context/', kube_ctx, name='sync2pod-kube-context'),
    path('config/',       cfg_get,  name='sync2pod-config'),
]

# WebSocket URL patterns (imported in asgi.py)
websocket_urlpatterns = [
    path('ws/sync2pod/task/<int:task_id>/logs/', Sync2PodTaskLogConsumer.as_asgi()),
]
