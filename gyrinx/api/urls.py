from django.urls import path

from gyrinx.api import views

app_name = "api"
urlpatterns = [
    path("v1/hooks/patreon.json", views.hook_patreon, name="hook_patreon"),
]
