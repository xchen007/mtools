"""
ASGI config for config project.
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from bisync.urls import websocket_urlpatterns as bisync_ws
from sync2pod.urls import websocket_urlpatterns as sync2pod_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(bisync_ws + sync2pod_ws)
        )
    ),
})
