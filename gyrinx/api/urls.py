from django.urls import path

from gyrinx.api import views

app_name = "api"
urlpatterns = [
    path("v1/hooks/patreon.json", views.hook_patreon, name="hook_patreon"),
    path(
        "v1/discord/interactions",
        views.discord_interactions,
        name="discord_interactions",
    ),
]
