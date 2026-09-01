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
    path("changelog/", views.changelog, name="n26-changelog"),
    path(
        "changelog/<uuid:pk>/",
        views.changelog_entry,
        name="n26-changelog-entry",
    ),
    # Every campaign route is gated by the campaigns feature flag, so all
    # of them answer 404 to a reader who is not let in.
    path("campaigns/", views.campaigns, name="n26-campaigns"),
    path("campaigns/new/", views.create_campaign, name="n26-create-campaign"),
    # After campaigns/new/, which would otherwise resolve "new" as an id.
    path("campaigns/<str:pk>/", views.campaign, name="n26-campaign"),
    path(
        "campaigns/<str:pk>/edit/",
        views.edit_campaign,
        name="n26-edit-campaign",
    ),
    path(
        "campaigns/<str:pk>/archive/",
        views.archive_campaign,
        name="n26-archive-campaign",
    ),
    path(
        "campaigns/<str:pk>/gangs/add/",
        views.add_gang,
        name="n26-campaign-add-gang",
    ),
    path(
        "campaigns/<str:pk>/gangs/<str:gang_pk>/remove/",
        views.remove_gang,
        name="n26-campaign-remove-gang",
    ),
    path(
        "campaigns/<str:pk>/participants/add/",
        views.add_participant,
        name="n26-campaign-add-participant",
    ),
    path(
        "campaigns/<str:pk>/participants/<int:user_pk>/remove/",
        views.remove_participant,
        name="n26-campaign-remove-participant",
    ),
    path(
        "campaigns/<str:pk>/invitation/",
        views.answer_invitation,
        name="n26-campaign-answer-invitation",
    ),
    path(
        "campaigns/<str:pk>/battles/new/",
        views.add_battle,
        name="n26-campaign-add-battle",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/remove/",
        views.remove_battle,
        name="n26-campaign-remove-battle",
    ),
    path("gangs/", views.gangs, name="n26-gangs"),
    path("gangs/new/", views.create_gang, name="n26-create-gang"),
    # After gangs/new/, which would otherwise resolve "new" as an id.
    path("gangs/<str:pk>/", views.gang_sheet, name="n26-gang"),
    path("gangs/<str:pk>/hire/", views.hire_fighter, name="n26-hire-fighter"),
    # The gang's own equip page: what is bought here goes to the stash,
    # where a fighter's equip page buys onto the fighter.
    path("gangs/<str:pk>/equip/", views.equip_gang, name="n26-equip-gang"),
    # One option's preview card, fetched when its row is first opened —
    # the hire list ships priced rows and no cards.
    path(
        "gangs/<str:pk>/hire/card/<str:profile>/",
        views.hire_card,
        name="n26-hire-card",
    ),
    path("gangs/<str:pk>/edit/", views.edit_gang, name="n26-edit-gang"),
    path("gangs/<str:pk>/history/", views.gang_history, name="n26-gang-history"),
    path("gangs/<str:pk>/lore/", views.gang_lore, name="n26-gang-lore"),
    path("gangs/<str:pk>/notes/", views.gang_notes, name="n26-gang-notes"),
    # What the gang takes to a trading post. Its own page rather than a
    # field on the edit form: the allowance is minted for a trip and
    # spent within it, which is a different act from settling the gang's
    # standing facts.
    path(
        "gangs/<str:pk>/trade-points/",
        views.gang_trade_points,
        name="n26-gang-trade-points",
    ),
    path("gangs/<str:pk>/delete/", views.delete_gang, name="n26-delete-gang"),
    # The slot's own address. It names the card, the assignment carrying
    # the offer and the offer itself, so one route serves a fighter's
    # choice and the gang's alike — see n26.core.views.choose.
    path("gangs/<str:pk>/choose/<str:slot>/", views.choose, name="n26-choose"),
    # The acts behind the gang sheet's dialogs; GET just reopens each one.
    # The model's own page: the card with its edit affordances and the
    # owner's notes. Equip is the same header's second tab.
    path("fighters/<str:pk>/edit/", views.edit_fighter, name="n26-edit-fighter"),
    # The options the model was hired with, reopened — the third of the
    # model's own tabs.
    path(
        "fighters/<str:pk>/options/",
        views.fighter_options,
        name="n26-fighter-options",
    ),
    path("fighters/<str:pk>/rename/", views.rename_fighter, name="n26-rename-fighter"),
    path("fighters/<str:pk>/delete/", views.delete_fighter, name="n26-delete-fighter"),
    path("fighters/<str:pk>/refund/", views.refund_fighter, name="n26-refund-fighter"),
    path("fighters/<str:pk>/equip/", views.equip, name="n26-equip"),
    # Addressed by fighter, not by slot: what they may select is their
    # grid rather than a question anybody asked — see n26.core.views.select.
    path("fighters/<str:pk>/skills/", views.select, name="n26-select"),
    # What a gang already owns, addressed by the assignment rather than by
    # whoever is carrying it: the same acts serve a fighter's card, a
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
    path(
        "assignments/<str:pk>/accessorise/",
        views.accessorise_assignment,
        name="n26-accessorise",
    ),
    path(
        "assignments/<str:pk>/rechoose/",
        views.rechoose_assignment,
        name="n26-rechoose",
    ),
    # A counter moved by hand. Addressed by the assignment like the acts
    # above, so one route serves a model's tallies and the gang's.
    path(
        "assignments/<str:pk>/tally/",
        views.tally_counter,
        name="n26-tally",
    ),
    path("gangs/<str:pk>/print/setup/", views.print_setup, name="n26-print-setup"),
    path("gangs/<str:pk>/print/", views.print_gang, name="n26-print"),
    path("design/", include("n26.designsystem.urls")),
    path("authoring/", authoring_views.index, name="authoring-index"),
    # Before the kind routes: "docs" and "recipes" would read as kind slugs.
    path(
        "authoring/docs/",
        authoring_views.docs,
        name="authoring-docs",
    ),
    path(
        "authoring/docs/<str:slug>/",
        authoring_views.doc,
        name="authoring-doc",
    ),
    # A second address for the cookbook, kept because links to it are
    # out in the world: it redirects to the documentation page.
    path(
        "authoring/recipes/",
        authoring_views.recipes,
        name="authoring-recipes",
    ),
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
    # A gun member's own lines are built in from the gun's row — the
    # address names the member, because a set may bring the same gun
    # twice and which of them a line rides is the whole question.
    path(
        "authoring/built-ins/<str:pk>/profiles/",
        authoring_views.built_in_profiles,
        name="authoring-built-in-profiles",
    ),
    # The same act for a set that does not bring the gun — an option
    # set arming a weapon the built-ins bring. The weapon is picked
    # first and carried in the address.
    path(
        "authoring/sets/<str:pk>/profiles/",
        authoring_views.set_profiles,
        name="authoring-set-profiles",
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
    # A listing row belongs to its collection the way an option belongs
    # to the thing offering it, so withdrawing one has an address here.
    path(
        "authoring/entries/<str:pk>/remove/",
        authoring_views.entry_remove,
        name="authoring-entry-remove",
    ),
    # A pickable's place on a picklist belongs to that list, the same way,
    # so taking it off has an address here.
    path(
        "authoring/picklist-members/<str:pk>/remove/",
        authoring_views.picklist_member_remove,
        name="authoring-picklist-member-remove",
    ),
    # A literal address, so it matches ahead of the kind catch-all: a
    # roll table's gaps and overlaps are facts about the whole list, and
    # the picklist's own page shows only one row at a time.
    path(
        "authoring/picklists/<str:pk>/table/",
        authoring_views.picklist_table,
        name="authoring-picklist-table",
    ),
    # A firing line belongs to its weapon rather than being an authored
    # kind of its own — there is no listing of every profile in the
    # library, and no making one apart from the weapon it fires — so
    # correcting one has an address here, by the line's own pk.
    path(
        "authoring/weapon-profiles/<str:pk>/",
        authoring_views.weapon_profile,
        name="authoring-weapon-profile",
    ),
    path(
        "authoring/weapon-profiles/<str:pk>/delete/",
        authoring_views.weapon_profile_delete,
        name="authoring-weapon-profile-delete",
    ),
    # Adding one is addressed by the weapon, the way a second item
    # inside an option is addressed by the option: there is no line yet
    # to name, and the parent is what the act is about.
    path(
        "authoring/weapons/<str:pk>/add-profile/",
        authoring_views.weapon_profile_add,
        name="authoring-weapon-profile-add",
    ),
    path(
        "authoring/foundations/",
        authoring_views.foundations,
        name="authoring-foundations",
    ),
    path("authoring/ingest/", authoring_views.ingest, name="authoring-ingest"),
    path(
        "authoring/ingest/preview/",
        authoring_views.ingest_preview,
        name="authoring-ingest-preview",
    ),
    path(
        "authoring/ingest/clear/",
        authoring_views.ingest_clear,
        name="authoring-ingest-clear",
    ),
    path(
        "authoring/ingest/sheet/<slug:sheet>/",
        authoring_views.ingest_sheet,
        name="authoring-ingest-sheet",
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
        "authoring/<slug:kind>/<str:pk>/delete/",
        authoring_views.thing_delete,
        name="authoring-thing-delete",
    ),
    path(
        "authoring/<slug:kind>/<str:pk>/",
        authoring_views.detail,
        name="authoring-detail",
    ),
    path("preview/", views.preview_view, name="preview"),
]
