"""N26 URL routes, mounted by the platform under /n26/. Keep paths relative to the mount
point.
"""

from django.urls import include, path

from n26.core import views
from n26.library import action_builder_views
from n26.library import views as authoring_views

urlpatterns = [
    path("", views.dashboard, name="n26-dashboard"),
    path("users/@<str:username>/", views.user_profile, name="n26-user-profile"),
    path("users/@<str:username>/invite/", views.invite_user, name="n26-invite-user"),
    # Resolve numeric legacy profile links as account IDs, before matching unprefixed
    # usernames.
    path("users/<int:pk>/", views.user_profile_by_id, name="n26-user-profile-by-id"),
    path(
        "users/<int:pk>/invite/", views.invite_user_by_id, name="n26-invite-user-by-id"
    ),
    path("users/<str:username>/", views.user_profile),
    path("users/<str:username>/invite/", views.invite_user),
    # Keep edition changelog links redirecting to the shared changelog filtered to N26.
    path("changelog/", views.n26_changelog, name="n26-changelog"),
    path(
        "changelog/<uuid:pk>/",
        views.n26_changelog_entry,
        name="n26-changelog-entry",
    ),
    path("scenario/", views.generate_scenario, name="n26-generate-scenario"),
    path(
        "scenario/save/",
        views.save_scenario_to_campaign,
        name="n26-generate-scenario-save",
    ),
    path(
        "scenario/record/",
        views.record_scenario_battle,
        name="n26-generate-scenario-record",
    ),
    path("scenario/print/", views.print_scenario, name="n26-scenario-print"),
    path("campaigns/", views.campaigns, name="n26-campaigns"),
    path("campaigns/new/", views.create_campaign, name="n26-create-campaign"),
    # Match the literal new route before the string primary-key route.
    path("campaigns/<str:pk>/", views.campaign, name="n26-campaign"),
    path(
        "campaigns/<str:pk>/rolls/new/",
        views.record_campaign_roll,
        name="n26-campaign-record-roll",
    ),
    path(
        "campaigns/<str:pk>/rolls/<str:roll_pk>/",
        views.campaign_roll,
        name="n26-campaign-roll",
    ),
    path("campaigns/<str:pk>/log/", views.campaign_log, name="n26-campaign-log"),
    path(
        "campaigns/<str:pk>/scenario/",
        views.scenario_generator,
        name="n26-scenario-generator",
    ),
    path(
        "campaigns/<str:pk>/scenario/save/",
        views.save_scenario,
        name="n26-save-scenario",
    ),
    path(
        "campaigns/<str:pk>/scenario/print/",
        views.campaign_print_scenario,
        name="n26-campaign-scenario-print",
    ),
    path(
        "campaigns/<str:pk>/edit/",
        views.edit_campaign,
        name="n26-edit-campaign",
    ),
    path(
        "campaigns/<str:pk>/grouping/",
        views.campaign_grouping,
        name="n26-campaign-grouping",
    ),
    path(
        "campaigns/<str:pk>/archive/",
        views.archive_campaign,
        name="n26-archive-campaign",
    ),
    path(
        "campaigns/<str:pk>/leave/",
        views.leave_campaign,
        name="n26-leave-campaign",
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
        "campaigns/<str:pk>/players/add/",
        views.add_player,
        name="n26-campaign-add-player",
    ),
    path(
        "campaigns/<str:pk>/players/<int:user_pk>/remove/",
        views.remove_player,
        name="n26-campaign-remove-player",
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
        "campaigns/<str:pk>/battles/",
        views.campaign_battles,
        name="n26-campaign-battles",
    ),
    path(
        "campaigns/<str:pk>/battles/archived/",
        views.archived_battles,
        name="n26-campaign-archived-battles",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/",
        views.battle,
        name="n26-battle",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/edit/",
        views.edit_battle,
        name="n26-campaign-edit-battle",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/outcome/",
        views.record_battle_outcome,
        name="n26-campaign-battle-outcome",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/gangs/<str:gang_pk>/crew/",
        views.edit_crew,
        name="n26-battle-crew",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/gangs/<str:gang_pk>/crew/cards/",
        views.crew_sheet,
        name="n26-battle-crew-sheet",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/gangs/<str:gang_pk>/results/",
        views.battle_report,
        name="n26-battle-report",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/restore/",
        views.restore_battle,
        name="n26-campaign-restore-battle",
    ),
    path(
        "campaigns/<str:pk>/battles/<str:battle_pk>/remove/",
        views.remove_battle,
        name="n26-campaign-remove-battle",
    ),
    path(
        "campaigns/<str:pk>/assets/add/",
        views.add_asset,
        name="n26-campaign-add-asset",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/edit/",
        views.edit_asset,
        name="n26-campaign-asset-edit",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/edit/change/",
        views.edit_asset_command,
        name="n26-campaign-asset-edit-command",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/assign/",
        views.assign_asset,
        name="n26-campaign-asset-assign",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/unassign/",
        views.unassign_asset,
        name="n26-campaign-asset-unassign",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/remove/",
        views.remove_asset,
        name="n26-campaign-asset-remove",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/transfer/",
        views.transfer_asset,
        name="n26-campaign-asset-transfer",
    ),
    path(
        "campaigns/<str:pk>/assets/types/add/",
        views.add_asset_type,
        name="n26-campaign-add-asset-type",
    ),
    path(
        "campaigns/<str:pk>/assets/types/<str:asset_type_pk>/edit/",
        views.edit_asset_type,
        name="n26-campaign-edit-asset-type",
    ),
    path(
        "campaigns/<str:pk>/assets/types/<str:asset_type_pk>/edit/change/",
        views.edit_asset_type_command,
        name="n26-campaign-edit-asset-type-command",
    ),
    path(
        "campaigns/<str:pk>/assets/new/",
        views.new_asset,
        name="n26-campaign-new-asset",
    ),
    path(
        "campaigns/<str:pk>/counters/add/",
        views.add_counter,
        name="n26-campaign-add-counter",
    ),
    path(
        "campaigns/<str:pk>/labels/add/",
        views.add_label,
        name="n26-campaign-add-label",
    ),
    path(
        "campaigns/<str:pk>/counters/<str:member_pk>/archive/",
        views.archive_addition,
        {"kind": "counter"},
        name="n26-campaign-archive-counter",
    ),
    path(
        "campaigns/<str:pk>/labels/<str:member_pk>/archive/",
        views.archive_addition,
        {"kind": "label"},
        name="n26-campaign-archive-label",
    ),
    path(
        "campaigns/<str:pk>/counters/<str:member_pk>/unarchive/",
        views.unarchive_addition,
        {"kind": "counter"},
        name="n26-campaign-unarchive-counter",
    ),
    path(
        "campaigns/<str:pk>/labels/<str:member_pk>/unarchive/",
        views.unarchive_addition,
        {"kind": "label"},
        name="n26-campaign-unarchive-label",
    ),
    path(
        "campaigns/<str:pk>/assets/roll/preview/",
        views.preview_pool_roll,
        name="n26-campaign-preview-pool-roll",
    ),
    path(
        "campaigns/<str:pk>/assets/roll/",
        views.roll_asset,
        name="n26-campaign-roll-asset",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/boons/",
        views.save_asset_boons,
        name="n26-campaign-asset-boons",
    ),
    path(
        "campaigns/<str:pk>/assets/<str:asset_pk>/",
        views.asset_detail,
        name="n26-campaign-asset",
    ),
    path(
        "campaigns/<str:pk>/gangs/<str:gang_pk>/roll/",
        views.roll_starting_asset,
        name="n26-campaign-roll-starting",
    ),
    path(
        "campaigns/<str:pk>/tables/",
        views.campaign_tables,
        name="n26-campaign-tables",
    ),
    path(
        "campaigns/<str:pk>/tables/new/",
        views.new_table,
        name="n26-campaign-new-table",
    ),
    path(
        "campaigns/<str:pk>/tables/<str:table_pk>/",
        views.campaign_table,
        name="n26-campaign-table",
    ),
    path(
        "campaigns/<str:pk>/tables/<str:table_pk>/entries/<str:entry_pk>/remove/",
        views.remove_table_entry,
        name="n26-campaign-table-entry-remove",
    ),
    path("gangs/", views.gangs, name="n26-gangs"),
    path("gangs/new/", views.create_gang, name="n26-create-gang"),
    # Match the literal new route before the string primary-key route.
    path("gangs/<str:pk>/", views.gang_sheet, name="n26-gang"),
    path("gangs/<str:pk>/hire/", views.hire_fighter, name="n26-hire-fighter"),
    path("gangs/<str:pk>/equip/", views.equip_gang, name="n26-equip-gang"),
    # Load preview cards on demand; the initial hire list contains priced rows only.
    path(
        "gangs/<str:pk>/hire/card/<str:profile>/",
        views.hire_card,
        name="n26-hire-card",
    ),
    path(
        "gangs/<str:pk>/budget/campaign/",
        views.use_campaign_budget,
        name="n26-use-campaign-budget",
    ),
    path(
        "gangs/<str:pk>/budget/dismiss/",
        views.dismiss_campaign_budget,
        name="n26-dismiss-campaign-budget",
    ),
    path("gangs/<str:pk>/edit/", views.edit_gang, name="n26-edit-gang"),
    path("gangs/<str:pk>/clone/", views.clone_gang, name="n26-clone-gang"),
    path("gangs/<str:pk>/history/", views.gang_history, name="n26-gang-history"),
    path("gangs/<str:pk>/credits/", views.gang_credits, name="n26-gang-credits"),
    path(
        "gangs/<str:pk>/credits/change/",
        views.gang_credits_command,
        name="n26-gang-credits-command",
    ),
    path("gangs/<str:pk>/lore/", views.gang_lore, name="n26-gang-lore"),
    path("gangs/<str:pk>/notes/", views.gang_notes, name="n26-gang-notes"),
    # Trade points belong to a trading-post visit rather than the gang edit form.
    path(
        "gangs/<str:pk>/trade-points/",
        views.gang_trade_points,
        name="n26-gang-trade-points",
    ),
    path(
        "gangs/<str:pk>/actions/founding/",
        views.gang_founding_action,
        name="n26-gang-founding-action",
    ),
    path(
        "fighters/<str:pk>/actions/hire-time-tp/",
        views.fighter_hire_time_action,
        name="n26-fighter-hire-time-action",
    ),
    path("gangs/<str:pk>/delete/", views.delete_gang, name="n26-delete-gang"),
    # The encoded slot identifies the carrier assignment and offer for both gang and
    # fighter choices; see n26.core.views.choose.
    path("gangs/<str:pk>/choose/<str:slot>/", views.choose, name="n26-choose"),
    # Interstitial choices and the continuation target stay in the URL; see
    # n26.core.views.arrivals.
    path("gangs/<str:pk>/next/", views.gang_next, name="n26-next"),
    # Dismissal and restoration are POST-only actions using the same encoded slot
    # address.
    path(
        "gangs/<str:pk>/offers/<str:slot>/dismiss/",
        views.dismiss_offer,
        name="n26-dismiss-offer",
    ),
    path(
        "gangs/<str:pk>/offers/<str:slot>/restore/",
        views.restore_offer,
        name="n26-restore-offer",
    ),
    path("fighters/<str:pk>/edit/", views.edit_fighter, name="n26-edit-fighter"),
    path("fighters/<str:pk>/rating/", views.base_rating, name="n26-base-rating"),
    path(
        "fighters/<str:pk>/actions/<str:action_id>/",
        views.action_start,
        name="n26-action-start",
    ),
    path(
        "fighters/<str:pk>/actions/<str:action_id>/by-hand/",
        views.action_by_hand,
        name="n26-action-by-hand",
    ),
    path(
        "fighters/<str:pk>/action-uses/<str:record_id>/<str:step>/",
        views.action_flow,
        name="n26-action-flow",
    ),
    path(
        "fighters/<str:pk>/clone/",
        views.clone_fighter,
        name="n26-clone-fighter",
    ),
    path(
        "fighters/<str:pk>/options/",
        views.fighter_options,
        name="n26-fighter-options",
    ),
    path("fighters/<str:pk>/rename/", views.rename_fighter, name="n26-rename-fighter"),
    path("fighters/<str:pk>/status/", views.mark_fighter, name="n26-mark-fighter"),
    path("fighters/<str:pk>/ransom/", views.pay_ransom, name="n26-pay-ransom"),
    path("gangs/<str:pk>/clean-house/", views.clean_house, name="n26-clean-house"),
    path("fighters/<str:pk>/delete/", views.delete_fighter, name="n26-delete-fighter"),
    path("fighters/<str:pk>/refund/", views.refund_fighter, name="n26-refund-fighter"),
    path("fighters/<str:pk>/equip/", views.equip, name="n26-equip"),
    path("fighters/<str:pk>/skills/", views.skills, name="n26-skills"),
    # Address owned equipment by assignment so the same endpoints work for fighters,
    # weapon ammunition and the stash.
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
    path(
        "assignments/<str:pk>/tally/",
        views.tally_counter,
        name="n26-tally",
    ),
    path("gangs/<str:pk>/print/setup/", views.print_setup, name="n26-print-setup"),
    path("gangs/<str:pk>/print/", views.print_gang, name="n26-print"),
    path(
        "gangs/<str:pk>/post-battle/",
        views.gang_post_battle,
        name="n26-gang-post-battle",
    ),
    path(
        "post-battle/<str:pk>/", views.post_battle_editor, name="n26-post-battle-editor"
    ),
    path(
        "post-battle/<str:pk>/receipt/",
        views.post_battle_receipt,
        name="n26-post-battle-receipt",
    ),
    path(
        "post-battle/<str:pk>/receipt/<int:sequence>/",
        views.post_battle_receipt,
        name="n26-post-battle-revision",
    ),
    path(
        "post-battle/<str:pk>/correct/",
        views.correct_post_battle,
        name="n26-post-battle-correct",
    ),
    path(
        "gangs/<str:pk>/models/<str:miniature_pk>/cards/",
        views.model_cards,
        name="n26-model-cards",
    ),
    path(
        "gangs/<str:pk>/models/<str:miniature_pk>/cards/new/",
        views.edit_model_card,
        name="n26-model-card-create",
    ),
    path(
        "gangs/<str:pk>/models/<str:miniature_pk>/cards/<str:set_pk>/edit/",
        views.edit_model_card,
        name="n26-model-card-edit",
    ),
    path(
        "gangs/<str:pk>/models/<str:miniature_pk>/cards/<str:set_pk>/remove/",
        views.remove_model_card,
        name="n26-model-card-remove",
    ),
    path("design/", include("n26.designsystem.urls")),
    path("authoring/", authoring_views.index, name="authoring-index"),
    path(
        "authoring/built-in-actions/trading-post-visit/",
        authoring_views.trading_post_visit_settings,
        name="authoring-trading-post-visit",
    ),
    path(
        "gangs/<str:pk>/other-actions/",
        views.gang_other_actions,
        name="n26-gang-other-actions",
    ),
    path(
        "authoring/action/<str:pk>/grant/",
        action_builder_views.grant_action,
        name="authoring-action-grant",
    ),
    # Match literal authoring routes before the generic kind routes.
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
    # Keep the cookbook alias redirecting to the documentation page.
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
    # Modifiers have dedicated routes because they are not authored kinds. Match new
    # before the string primary-key route.
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
    path(
        "authoring/built-ins/<str:pk>/remove/",
        authoring_views.built_in_remove,
        name="authoring-built-in-remove",
    ),
    # Identify the built-in member because a set can grant the same weapon more than
    # once, with different profiles.
    path(
        "authoring/built-ins/<str:pk>/profiles/",
        authoring_views.built_in_profiles,
        name="authoring-built-in-profiles",
    ),
    # The option set selects profiles for an existing built-in weapon; its ID is carried
    # in the request.
    path(
        "authoring/sets/<str:pk>/profiles/",
        authoring_views.set_profiles,
        name="authoring-set-profiles",
    ),
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
        "authoring/entries/<str:pk>/edit/",
        authoring_views.entry_edit,
        name="authoring-entry-edit",
    ),
    path(
        "authoring/entries/<str:pk>/remove/",
        authoring_views.entry_remove,
        name="authoring-entry-remove",
    ),
    path(
        "authoring/picklist-members/<str:pk>/remove/",
        authoring_views.picklist_member_remove,
        name="authoring-picklist-member-remove",
    ),
    path(
        "authoring/interstitial-attachments/<str:pk>/remove/",
        authoring_views.interstitial_detach,
        name="authoring-interstitial-detach",
    ),
    path(
        "authoring/asset-table-entries/<str:pk>/remove/",
        authoring_views.asset_table_entry_remove,
        name="authoring-asset-table-entry-remove",
    ),
    path(
        "authoring/asset-types/<str:pk>/remove/",
        authoring_views.asset_type_remove,
        name="authoring-asset-type-remove",
    ),
    path(
        "authoring/picklists/<str:pk>/clone/",
        authoring_views.picklist_clone,
        name="authoring-picklist-clone",
    ),
    path(
        "authoring/picklists/<str:pk>/table/",
        authoring_views.picklist_table,
        name="authoring-picklist-table",
    ),
    # Weapon profiles are authored through their weapon, rather than as a standalone
    # content kind.
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
    path("authoring/staged/", authoring_views.staged, name="authoring-staged"),
    path(
        "authoring/staged/put-live/",
        authoring_views.staged_put_live,
        name="authoring-staged-put-live",
    ),
    path(
        "authoring/staged/delete/",
        authoring_views.staged_delete,
        name="authoring-staged-delete",
    ),
    # Deleting content with test gangs runs in the background; this route shows the
    # recorded outcome.
    path(
        "authoring/deletions/<uuid:pk>/",
        authoring_views.deletion,
        name="authoring-deletion",
    ),
    path("authoring/ingest/", authoring_views.ingest, name="authoring-ingest"),
    path(
        "authoring/ingest/preview/",
        authoring_views.ingest_preview,
        name="authoring-ingest-preview",
    ),
    path(
        "authoring/ingest/sheet/<slug:sheet>/",
        authoring_views.ingest_sheet,
        name="authoring-ingest-sheet",
    ),
    path("authoring/<slug:kind>/", authoring_views.leaf, name="authoring-leaf"),
    # Match new before the string primary-key route.
    path(
        "authoring/<slug:kind>/new/",
        authoring_views.create,
        name="authoring-create",
    ),
    # Match attach-modifier before the string primary-key route.
    path(
        "authoring/<slug:kind>/attach-modifier/",
        authoring_views.attach_modifier,
        name="authoring-attach-modifier",
    ),
    path(
        "authoring/<slug:kind>/<str:pk>/delete/",
        authoring_views.thing_delete,
        name="authoring-thing-delete",
    ),
    path(
        "authoring/<slug:kind>/<str:pk>/merge/",
        authoring_views.thing_merge,
        name="authoring-thing-merge",
    ),
    path(
        "authoring/<slug:kind>/<str:pk>/",
        authoring_views.detail,
        name="authoring-detail",
    ),
    path("preview/", views.preview_view, name="preview"),
    path("switcher/<slug:source>/", views.switcher_page, name="n26-switcher-rows"),
]
