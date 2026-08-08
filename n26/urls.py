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
    path("gangs/", views.gangs, name="n26-gangs"),
    path("gangs/new/", views.create_gang, name="n26-create-gang"),
    # After gangs/new/, which would otherwise resolve "new" as an id.
    path("gangs/<str:pk>/", views.gang_sheet, name="n26-gang"),
    path("gangs/<str:pk>/hire/", views.hire_fighter, name="n26-hire-fighter"),
    path("fighters/<str:pk>/equip/", views.equip, name="n26-equip"),
    path("gangs/<str:pk>/print/setup/", views.print_setup, name="n26-print-setup"),
    path("gangs/<str:pk>/print/", views.print_gang, name="n26-print"),
    path("design/", include("n26.designsystem.urls")),
    path("authoring/", authoring_views.index, name="authoring-index"),
    path(
        "authoring/modifiers/",
        authoring_views.modifiers,
        name="authoring-modifiers",
    ),
    path(
        "authoring/foundations/",
        authoring_views.foundations,
        name="authoring-foundations",
    ),
    path("authoring/ingest/", authoring_views.ingest, name="authoring-ingest"),
    path(
        "authoring/ingest/clear/",
        authoring_views.ingest_clear,
        name="authoring-ingest-clear",
    ),
    path("authoring/<slug:kind>/", authoring_views.leaf, name="authoring-leaf"),
    # Before the pk route: "new" is a perfectly good primary key as far
    # as the pattern is concerned, and the first match wins.
    path(
        "authoring/<slug:kind>/new/",
        authoring_views.create,
        name="authoring-create",
    ),
    path(
        "authoring/<slug:kind>/<str:pk>/",
        authoring_views.detail,
        name="authoring-detail",
    ),
    path("preview/", views.preview_view, name="preview"),
]
