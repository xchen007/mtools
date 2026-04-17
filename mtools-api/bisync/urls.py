from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .consumers import BisyncTargetLogConsumer

router = DefaultRouter()
router.register(r'tasks', views.BisyncTaskViewSet, basename='bisync-task')

# Target-level routes handled via custom ViewSet
target_vs = views.BisyncTargetViewSet.as_view({
    'get': 'retrieve',
    'delete': 'destroy',
})
target_start = views.BisyncTargetViewSet.as_view({'post': 'start'})
target_stop  = views.BisyncTargetViewSet.as_view({'post': 'stop'})
target_reset = views.BisyncTargetViewSet.as_view({'post': 'reset'})
target_logs  = views.BisyncTargetViewSet.as_view({'get': 'logs'})

urlpatterns = router.urls + [
    path('targets/<int:pk>/',        target_vs,    name='bisync-target-detail'),
    path('targets/<int:pk>/start/',  target_start, name='bisync-target-start'),
    path('targets/<int:pk>/stop/',   target_stop,  name='bisync-target-stop'),
    path('targets/<int:pk>/reset/',  target_reset, name='bisync-target-reset'),
    path('targets/<int:pk>/logs/',   target_logs,  name='bisync-target-logs'),
]

# WebSocket URL patterns (imported in asgi.py)
websocket_urlpatterns = [
    path('ws/bisync/target/<int:target_id>/logs/', BisyncTargetLogConsumer.as_asgi()),
]
