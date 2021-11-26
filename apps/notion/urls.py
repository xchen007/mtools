from django.urls import path
from . import views
from django.views.decorators.csrf import csrf_exempt

app_name = "notion"

urlpatterns = [
    path(r'test/',views.NotionTest.as_view())
]
