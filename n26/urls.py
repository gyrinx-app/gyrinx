"""The n26 edition's URL surface, mounted by the platform under /n26/.

Everything the edition serves hangs off one include, the way n23's
does — the platform's urls.py names the mount point, and nothing in
here assumes where that is.
"""

from django.urls import include, path

from n26.core import views
from n26.library import views as authoring_views

urlpatterns = [
    path("", views.dashboard, name="n26-dashboard"),
    path("gangs/new/", views.create_gang, name="n26-create-gang"),
    path("design/", include("n26.designsystem.urls")),
    path("authoring/", authoring_views.index, name="authoring-index"),
    path(
        "authoring/foundations/",
        authoring_views.foundations,
        name="authoring-foundations",
    ),
    path("authoring/<slug:kind>/", authoring_views.leaf, name="authoring-leaf"),
    path(
        "authoring/<slug:kind>/<str:pk>/",
        authoring_views.detail,
        name="authoring-detail",
    ),
    path("preview/", views.preview_view, name="preview"),
]
