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
    path("gangs/<str:pk>/delete/", views.delete_gang, name="n26-delete-gang"),
    # The slot's own address. It names the card, the assignment carrying
    # the offer and the offer itself, so one route answers a fighter's
    # choice and the gang's alike — see n26.core.views.choose.
    path("gangs/<str:pk>/choose/<str:slot>/", views.choose, name="n26-choose"),
    path("fighters/<str:pk>/equip/", views.equip, name="n26-equip"),
    # Addressed by fighter, not by slot: what they may learn is their
    # grid rather than a question anybody asked — see n26.core.views.learn.
    path("fighters/<str:pk>/skills/", views.learn, name="n26-learn"),
    # What a gang already owns, addressed by the assignment rather than by
    # whoever is carrying it: the same four acts serve a fighter's card, a
    # weapon's ammo and the stash, and every screen that grows them later
    # reuses these — see n26.core.views.owned.
    path(
        "assignments/<str:pk>/sell/",
        views.sell_assignment,
        name="n26-sell",
    ),
    path(
        "assignments/<str:pk>/reassign/",
        views.reassign_assignment,
        name="n26-reassign",
    ),
    path(
        "assignments/<str:pk>/refund/",
        views.refund_assignment,
        name="n26-refund",
    ),
    path(
        "assignments/<str:pk>/remove/",
        views.remove_assignment,
        name="n26-remove",
    ),
    path("gangs/<str:pk>/print/setup/", views.print_setup, name="n26-print-setup"),
    path("gangs/<str:pk>/print/", views.print_gang, name="n26-print"),
    path("design/", include("n26.designsystem.urls")),
    path("authoring/", authoring_views.index, name="authoring-index"),
    path(
        "authoring/modifiers/",
        authoring_views.modifiers,
        name="authoring-modifiers",
    ),
    # A modifier is not one of the authored kinds — it has no create
    # verb of its own — so its pages hang off the modifiers listing
    # rather than the kind/pk routes below.
    #
    # Before the pk route: "new" is a perfectly good primary key as far
    # as the pattern is concerned, and the first match wins.
    path(
        "authoring/modifiers/new/",
        authoring_views.modifier_create,
        name="authoring-modifier-create",
    ),
    path(
        "authoring/modifiers/<str:pk>/",
        authoring_views.modifier_page,
        name="authoring-modifier",
    ),
    path(
        "authoring/modifiers/<str:pk>/delete/",
        authoring_views.modifier_delete,
        name="authoring-modifier-delete",
    ),
    # A built-in is a row of a set of defaults, not one of the authored
    # kinds, so taking one off has an address of its own rather than
    # riding the kind/pk routes below.
    path(
        "authoring/built-ins/<str:pk>/remove/",
        authoring_views.built_in_remove,
        name="authoring-built-in-remove",
    ),
    # An option and a set of options belong to the thing offering them
    # rather than being authored kinds of their own, so withdrawing
    # either has an address here instead of riding the kind/pk routes.
    path(
        "authoring/options/<str:pk>/add/",
        authoring_views.option_add,
        name="authoring-option-add",
    ),
    path(
        "authoring/options/<str:pk>/remove/",
        authoring_views.option_remove,
        name="authoring-option-remove",
    ),
    path(
        "authoring/option-sets/<str:pk>/remove/",
        authoring_views.option_set_remove,
        name="authoring-option-set-remove",
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
