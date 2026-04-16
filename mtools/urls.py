from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from mtools import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('settings/', core_views.settings_view, name='settings'),
    path('', RedirectView.as_view(url='/bisync/', permanent=False)),
    path('', include('bisync.urls')),
    path('', include('sync2pod.urls')),
]
