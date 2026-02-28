from django.urls import path

import gyrinx.core.views

from .views import battle, print_config, vehicle
from .views.campaign import actions as campaign_actions
from .views.campaign import assets as campaign_assets
from .views.campaign import attributes as campaign_attributes
from .views.campaign import battles as campaign_battles
from .views.campaign import captured as campaign_captured
from .views.campaign import copy as campaign_copy
from .views.campaign import packs as campaign_packs
from .views.campaign import crud as campaign_crud
from .views.campaign import lifecycle as campaign_lifecycle
from .views.campaign import lists as campaign_lists
from .views.campaign import resources as campaign_resources
from .views.campaign import sub_assets as campaign_sub_assets
from .views.campaign import views as campaign_views
from .views.fighter import advancements as fighter_advancements
from .views.fighter import counters as fighter_counters
from .views.fighter import crud as fighter_crud
from .views.fighter import equipment as fighter_equipment
from .views.fighter import narrative as fighter_narrative
from .views.fighter import powers as fighter_powers
from .views.fighter import rules as fighter_rules
from .views.fighter import skills as fighter_skills
from .views.fighter import state as fighter_state
from .views.fighter import stats as fighter_stats
from .views.fighter import xp as fighter_xp
from .views.list import attributes as list_attributes
from .views.list import invitations as list_invitations
from .views.list import views as list_views
from .views import pack as pack_views

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]

app_name = "core"
urlpatterns = [
    path("", gyrinx.core.views.index, name="index"),
    path("accounts/", gyrinx.core.views.account_home, name="account_home"),
    path(
        "accounts/change-username/",
        gyrinx.core.views.change_username,
        name="change-username",
    ),
    path("dice/", gyrinx.core.views.dice, name="dice"),
    path("lists/", list_views.ListsListView.as_view(), name="lists"),
    path("lists/new/packs", list_views.new_list_packs, name="lists-new-packs"),
    path("lists/new", list_views.new_list, name="lists-new"),
    path("list/<id>", list_views.ListDetailView.as_view(), name="list"),
    path(
        "list/<id>/perf",
        list_views.ListPerformanceView.as_view(),
        name="list-performance",
    ),
    path(
        "list/<id>/about", list_views.ListAboutDetailView.as_view(), name="list-about"
    ),
    path(
        "list/<id>/notes", list_views.ListNotesDetailView.as_view(), name="list-notes"
    ),
    path("list/<id>/archive", list_views.archive_list, name="list-archive"),
    path("list/<id>/show-stash", list_views.show_stash, name="list-show-stash"),
    path(
        "list/<id>/refresh-cost", list_views.refresh_list_cost, name="list-refresh-cost"
    ),
    path("list/<id>/edit", list_views.edit_list, name="list-edit"),
    path("list/<id>/packs", pack_views.list_packs_manage, name="list-packs"),
    path("list/<id>/credits", list_views.edit_list_credits, name="list-credits-edit"),
    path("list/<id>/clone", list_views.clone_list, name="list-clone"),
    path(
        "list/<id>/invitations",
        list_invitations.list_invitations,
        name="list-invitations",
    ),
    path(
        "list/<id>/invitations/<invitation_id>/accept",
        list_invitations.accept_invitation,
        name="invitation-accept",
    ),
    path(
        "list/<id>/invitations/<invitation_id>/decline",
        list_invitations.decline_invitation,
        name="invitation-decline",
    ),
    path(
        "list/<id>/fighters/new", fighter_crud.new_list_fighter, name="list-fighter-new"
    ),
    path("list/<id>/vehicles/new", vehicle.new_vehicle, name="list-vehicle-new"),
    path(
        "list/<id>/vehicles/new/select",
        vehicle.vehicle_select,
        name="list-vehicle-select",
    ),
    path("list/<id>/vehicles/new/crew", vehicle.vehicle_crew, name="list-vehicle-crew"),
    path(
        "list/<id>/vehicles/new/confirm",
        vehicle.vehicle_confirm,
        name="list-vehicle-confirm",
    ),
    path(
        "list/<id>/fighters/archived",
        fighter_crud.ListArchivedFightersView.as_view(),
        name="list-archived-fighters",
    ),
    path(
        "list/<id>/fighter/<fighter_id>",
        fighter_crud.edit_list_fighter,
        name="list-fighter-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/clone",
        fighter_crud.clone_list_fighter,
        name="list-fighter-clone",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills",
        fighter_skills.edit_list_fighter_skills,
        name="list-fighter-skills-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills/<skill_id>/toggle",
        fighter_skills.toggle_list_fighter_skill,
        name="list-fighter-skill-toggle",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills/add",
        fighter_skills.add_list_fighter_skill,
        name="list-fighter-skill-add",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills/<skill_id>/remove",
        fighter_skills.remove_list_fighter_skill,
        name="list-fighter-skill-remove",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/rules",
        fighter_rules.edit_list_fighter_rules,
        name="list-fighter-rules-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/rules/<rule_id>/toggle",
        fighter_rules.toggle_list_fighter_rule,
        name="list-fighter-rule-toggle",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/rules/add",
        fighter_rules.add_list_fighter_rule,
        name="list-fighter-rule-add",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/rules/<rule_id>/remove",
        fighter_rules.remove_list_fighter_rule,
        name="list-fighter-rule-remove",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/powers",
        fighter_powers.edit_list_fighter_powers,
        name="list-fighter-powers-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/narrative",
        fighter_narrative.edit_list_fighter_narrative,
        name="list-fighter-narrative-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/info",
        fighter_narrative.edit_list_fighter_info,
        name="list-fighter-info-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/notes",
        fighter_narrative.edit_list_fighter_notes,
        name="list-fighter-notes-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/stats",
        fighter_stats.list_fighter_stats_edit,
        name="list-fighter-stats-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear",
        fighter_equipment.edit_list_fighter_equipment,
        name="list-fighter-gear-edit",
        kwargs=dict(
            is_weapon=False,
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/cost",
        fighter_equipment.edit_list_fighter_assign_cost,
        name="list-fighter-gear-cost-edit",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-cost-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/delete",
        fighter_equipment.delete_list_fighter_assign,
        name="list-fighter-gear-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/reassign",
        fighter_equipment.reassign_list_fighter_equipment,
        name="list-fighter-gear-reassign",
        kwargs=dict(
            is_weapon=False,
            back_name="core:list-fighter-gear-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/sell",
        fighter_equipment.sell_list_fighter_equipment,
        name="list-fighter-equipment-sell",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/upgrade",
        fighter_equipment.edit_list_fighter_weapon_upgrade,
        name="list-fighter-gear-upgrade-edit",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-upgrade-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/upgrade/<upgrade_id>/delete",
        fighter_equipment.delete_list_fighter_gear_upgrade,
        name="list-fighter-gear-upgrade-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-upgrade-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/disable",
        fighter_equipment.disable_list_fighter_default_assign,
        name="list-fighter-gear-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/convert",
        fighter_equipment.convert_list_fighter_default_assign,
        name="list-fighter-gear-default-convert",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-default-convert",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/disable",
        fighter_equipment.disable_list_fighter_default_assign,
        name="list-fighter-weapons-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/convert",
        fighter_equipment.convert_list_fighter_default_assign,
        name="list-fighter-weapons-default-convert",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-convert",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/archive",
        fighter_crud.archive_list_fighter,
        name="list-fighter-archive",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/restore",
        fighter_crud.restore_list_fighter,
        name="list-fighter-restore",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/kill",
        fighter_crud.kill_list_fighter,
        name="list-fighter-kill",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/resurrect",
        fighter_crud.resurrect_list_fighter,
        name="list-fighter-resurrect",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/delete",
        fighter_crud.delete_list_fighter,
        name="list-fighter-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons",
        fighter_equipment.edit_list_fighter_equipment,
        name="list-fighter-weapons-edit",
        kwargs=dict(
            is_weapon=True,
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/cost",
        fighter_equipment.edit_list_fighter_assign_cost,
        name="list-fighter-weapon-cost-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-cost-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/delete",
        fighter_equipment.delete_list_fighter_assign,
        name="list-fighter-weapon-delete",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/reassign",
        fighter_equipment.reassign_list_fighter_equipment,
        name="list-fighter-weapon-reassign",
        kwargs=dict(
            is_weapon=True,
            back_name="core:list-fighter-weapons-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessories",
        fighter_equipment.edit_list_fighter_weapon_accessories,
        name="list-fighter-weapon-accessories-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/edit",
        fighter_equipment.edit_single_weapon,
        name="list-fighter-weapon-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/profile/<profile_id>/delete",
        fighter_equipment.delete_list_fighter_weapon_profile,
        name="list-fighter-weapon-profile-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessory/<accessory_id>/delete",
        fighter_equipment.delete_list_fighter_weapon_accessory,
        name="list-fighter-weapon-accessory-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/upgrade",
        fighter_equipment.edit_list_fighter_weapon_upgrade,
        name="list-fighter-weapon-upgrade-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-upgrade-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/injuries",
        fighter_state.list_fighter_injuries_edit,
        name="list-fighter-injuries-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/xp",
        fighter_xp.edit_list_fighter_xp,
        name="list-fighter-xp-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/counter/<counter_id>",
        fighter_counters.edit_list_fighter_counter,
        name="list-fighter-counter-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/mark-captured",
        fighter_state.mark_fighter_captured,
        name="list-fighter-mark-captured",
    ),
    # Fighter advancements
    path(
        "list/<id>/fighter/<fighter_id>/advancements/",
        fighter_advancements.list_fighter_advancements,
        name="list-fighter-advancements",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new",
        fighter_advancements.list_fighter_advancement_start,
        name="list-fighter-advancement-start",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new/dice",
        fighter_advancements.list_fighter_advancement_dice_choice,
        name="list-fighter-advancement-dice-choice",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new/type",
        fighter_advancements.list_fighter_advancement_type,
        name="list-fighter-advancement-type",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new/select",
        fighter_advancements.list_fighter_advancement_select,
        name="list-fighter-advancement-select",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new/other",
        fighter_advancements.list_fighter_advancement_other,
        name="list-fighter-advancement-other",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/new/confirm",
        fighter_advancements.list_fighter_advancement_confirm,
        name="list-fighter-advancement-confirm",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/advancements/<advancement_id>/delete",
        fighter_advancements.delete_list_fighter_advancement,
        name="list-fighter-advancement-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/state/edit",
        fighter_state.list_fighter_state_edit,
        name="list-fighter-state-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/injury/add",
        fighter_state.list_fighter_add_injury,
        name="list-fighter-injury-add",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/injury/<injury_id>/remove",
        fighter_state.list_fighter_remove_injury,
        name="list-fighter-injury-remove",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/embed",
        fighter_crud.embed_list_fighter,
        name="list-fighter-embed",
    ),
    path("list/<id>/print", list_views.ListPrintView.as_view(), name="list-print"),
    path(
        "list/<list_id>/print-configs",
        print_config.PrintConfigIndexView.as_view(),
        name="print-config-index",
    ),
    path(
        "list/<list_id>/print-configs/new",
        print_config.print_config_create,
        name="print-config-create",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/edit",
        print_config.print_config_edit,
        name="print-config-edit",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/delete",
        print_config.print_config_delete,
        name="print-config-delete",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/print",
        print_config.print_config_print,
        name="print-config-print",
    ),
    path(
        "list/<id>/attribute/<attribute_id>/edit",
        list_attributes.edit_list_attribute,
        name="list-attribute-edit",
    ),
    path(
        "list/<id>/campaign-clones",
        list_views.ListCampaignClonesView.as_view(),
        name="list-campaign-clones",
    ),
    # Users
    path("user/<slug_or_id>", gyrinx.core.views.user, name="user"),
    # Campaigns
    path("campaigns/", campaign_views.Campaigns.as_view(), name="campaigns"),
    path("campaigns/new/", campaign_crud.new_campaign, name="campaigns-new"),
    path("campaign/<id>", campaign_views.CampaignDetailView.as_view(), name="campaign"),
    path("campaign/<id>/edit/", campaign_crud.edit_campaign, name="campaign-edit"),
    path(
        "campaign/<id>/lists/add",
        campaign_lists.campaign_add_lists,
        name="campaign-add-lists",
    ),
    path(
        "campaign/<id>/list/<list_id>/remove",
        campaign_lists.campaign_remove_list,
        name="campaign-remove-list",
    ),
    path(
        "campaign/<id>/action/new",
        campaign_actions.campaign_log_action,
        name="campaign-action-new",
    ),
    path(
        "campaign/<id>/action/<action_id>/outcome",
        campaign_actions.campaign_action_outcome,
        name="campaign-action-outcome",
    ),
    path(
        "campaign/<id>/actions",
        campaign_actions.CampaignActionList.as_view(),
        name="campaign-actions",
    ),
    path(
        "campaign/<id>/start",
        campaign_lifecycle.start_campaign,
        name="campaign-start",
    ),
    path(
        "campaign/<id>/end",
        campaign_lifecycle.end_campaign,
        name="campaign-end",
    ),
    path(
        "campaign/<id>/reopen",
        campaign_lifecycle.reopen_campaign,
        name="campaign-reopen",
    ),
    path(
        "campaign/<id>/archive",
        campaign_lifecycle.archive_campaign,
        name="campaign-archive",
    ),
    # Campaign Copy
    path(
        "campaign/<id>/copy-in",
        campaign_copy.campaign_copy_from,
        name="campaign-copy-in",
    ),
    path(
        "campaign/<id>/copy-out",
        campaign_copy.campaign_copy_to,
        name="campaign-copy-out",
    ),
    # Campaign Assets
    path(
        "campaign/<id>/assets",
        campaign_assets.campaign_assets,
        name="campaign-assets",
    ),
    path(
        "campaign/<id>/assets/type/new",
        campaign_assets.campaign_asset_type_new,
        name="campaign-asset-type-new",
    ),
    path(
        "campaign/<id>/assets/type/<type_id>/edit",
        campaign_assets.campaign_asset_type_edit,
        name="campaign-asset-type-edit",
    ),
    path(
        "campaign/<id>/assets/type/<type_id>/remove",
        campaign_assets.campaign_asset_type_remove,
        name="campaign-asset-type-remove",
    ),
    path(
        "campaign/<id>/assets/type/<type_id>/new",
        campaign_assets.campaign_asset_new,
        name="campaign-asset-new",
    ),
    path(
        "campaign/<id>/assets/<asset_id>/edit",
        campaign_assets.campaign_asset_edit,
        name="campaign-asset-edit",
    ),
    path(
        "campaign/<id>/assets/<asset_id>/transfer",
        campaign_assets.campaign_asset_transfer,
        name="campaign-asset-transfer",
    ),
    path(
        "campaign/<id>/assets/<asset_id>/remove",
        campaign_assets.campaign_asset_remove,
        name="campaign-asset-remove",
    ),
    # Campaign Sub-Assets
    path(
        "campaign/<id>/assets/<asset_id>/sub-asset/<sub_asset_type>/new",
        campaign_sub_assets.campaign_sub_asset_new,
        name="campaign-sub-asset-new",
    ),
    path(
        "campaign/<id>/assets/<asset_id>/sub-asset/<sub_asset_id>/edit",
        campaign_sub_assets.campaign_sub_asset_edit,
        name="campaign-sub-asset-edit",
    ),
    path(
        "campaign/<id>/assets/<asset_id>/sub-asset/<sub_asset_id>/remove",
        campaign_sub_assets.campaign_sub_asset_remove,
        name="campaign-sub-asset-remove",
    ),
    # Campaign Resources
    path(
        "campaign/<id>/resources",
        campaign_resources.campaign_resources,
        name="campaign-resources",
    ),
    path(
        "campaign/<id>/resources/type/new",
        campaign_resources.campaign_resource_type_new,
        name="campaign-resource-type-new",
    ),
    path(
        "campaign/<id>/resources/type/<type_id>/edit",
        campaign_resources.campaign_resource_type_edit,
        name="campaign-resource-type-edit",
    ),
    path(
        "campaign/<id>/resources/type/<type_id>/remove",
        campaign_resources.campaign_resource_type_remove,
        name="campaign-resource-type-remove",
    ),
    path(
        "campaign/<id>/resources/<resource_id>/modify",
        campaign_resources.campaign_resource_modify,
        name="campaign-resource-modify",
    ),
    # Campaign Attributes
    path(
        "campaign/<id>/attributes",
        campaign_attributes.campaign_attributes,
        name="campaign-attributes",
    ),
    path(
        "campaign/<id>/attributes/type/new",
        campaign_attributes.campaign_attribute_type_new,
        name="campaign-attribute-type-new",
    ),
    path(
        "campaign/<id>/attributes/type/<type_id>/edit",
        campaign_attributes.campaign_attribute_type_edit,
        name="campaign-attribute-type-edit",
    ),
    path(
        "campaign/<id>/attributes/type/<type_id>/remove",
        campaign_attributes.campaign_attribute_type_remove,
        name="campaign-attribute-type-remove",
    ),
    path(
        "campaign/<id>/attributes/set-group",
        campaign_attributes.campaign_set_group_attribute,
        name="campaign-set-group-attribute",
    ),
    path(
        "campaign/<id>/attributes/type/<type_id>/value/new",
        campaign_attributes.campaign_attribute_value_new,
        name="campaign-attribute-value-new",
    ),
    path(
        "campaign/<id>/attributes/value/<value_id>/edit",
        campaign_attributes.campaign_attribute_value_edit,
        name="campaign-attribute-value-edit",
    ),
    path(
        "campaign/<id>/attributes/value/<value_id>/remove",
        campaign_attributes.campaign_attribute_value_remove,
        name="campaign-attribute-value-remove",
    ),
    path(
        "campaign/<id>/list/<list_id>/attribute/<type_id>/assign",
        campaign_attributes.campaign_list_attribute_assign,
        name="campaign-list-attribute-assign",
    ),
    # Campaign Packs
    path(
        "campaign/<id>/packs",
        campaign_packs.campaign_packs,
        name="campaign-packs",
    ),
    path(
        "campaign/<id>/packs/<pack_id>/add",
        campaign_packs.campaign_pack_add,
        name="campaign-pack-add",
    ),
    path(
        "campaign/<id>/packs/<pack_id>/remove",
        campaign_packs.campaign_pack_remove,
        name="campaign-pack-remove",
    ),
    # Battles
    path(
        "campaign/<id>/battles",
        campaign_battles.campaign_battles,
        name="campaign-battles",
    ),
    path(
        "battle/<id>",
        battle.BattleDetailView.as_view(),
        name="battle",
    ),
    path(
        "campaign/<campaign_id>/battles/new",
        battle.new_battle,
        name="battle-new",
    ),
    path(
        "battle/<id>/edit",
        battle.edit_battle,
        name="battle-edit",
    ),
    path(
        "battle/<battle_id>/notes/add",
        battle.add_battle_note,
        name="battle-note-add",
    ),
    # Captured fighters
    path(
        "campaign/<id>/captured-fighters",
        campaign_captured.campaign_captured_fighters,
        name="campaign-captured-fighters",
    ),
    path(
        "campaign/<id>/fighter/<fighter_id>/sell-to-guilders",
        campaign_captured.fighter_sell_to_guilders,
        name="fighter-sell-to-guilders",
    ),
    path(
        "campaign/<id>/fighter/<fighter_id>/return-to-owner",
        campaign_captured.fighter_return_to_owner,
        name="fighter-return-to-owner",
    ),
    path(
        "campaign/<id>/fighter/<fighter_id>/release",
        campaign_captured.fighter_release,
        name="fighter-release",
    ),
    # Packs (Customisation)
    path("packs/", pack_views.PacksView.as_view(), name="packs"),
    path("packs/new/", pack_views.new_pack, name="packs-new"),
    path("pack/<id>", pack_views.PackDetailView.as_view(), name="pack"),
    path("pack/<id>/edit/", pack_views.edit_pack, name="pack-edit"),
    path(
        "pack/<id>/permissions/",
        pack_views.pack_permissions,
        name="pack-permissions",
    ),
    path("pack/<id>/lists/", pack_views.PackListsView.as_view(), name="pack-lists"),
    path("pack/<id>/campaigns/", pack_views.pack_campaigns, name="pack-campaigns"),
    path("pack/<id>/subscribe/", pack_views.subscribe_pack, name="pack-subscribe"),
    path(
        "pack/<id>/unsubscribe/", pack_views.unsubscribe_pack, name="pack-unsubscribe"
    ),
    path(
        "pack/<id>/campaign-subscribe/",
        pack_views.subscribe_pack_campaign,
        name="pack-campaign-subscribe",
    ),
    path(
        "pack/<id>/campaign-unsubscribe/",
        pack_views.unsubscribe_pack_campaign,
        name="pack-campaign-unsubscribe",
    ),
    path(
        "pack/<id>/activity/",
        pack_views.PackActivityView.as_view(),
        name="pack-activity",
    ),
    path(
        "pack/<id>/add/<content_type_slug>/",
        pack_views.add_pack_item,
        name="pack-add-item",
    ),
    path(
        "pack/<id>/item/<item_id>/edit/",
        pack_views.edit_pack_item,
        name="pack-edit-item",
    ),
    path(
        "pack/<id>/item/<item_id>/delete/",
        pack_views.delete_pack_item,
        name="pack-delete-item",
    ),
    path(
        "pack/<id>/item/<item_id>/restore/",
        pack_views.restore_pack_item,
        name="pack-restore-item",
    ),
    path(
        "pack/<id>/archived/<content_type_slug>/",
        pack_views.PackArchivedItemsView.as_view(),
        name="pack-archived-items",
    ),
    path(
        "pack/<id>/item/<item_id>/profile/add/",
        pack_views.add_weapon_profile,
        name="pack-add-weapon-profile",
    ),
    path(
        "pack/<id>/item/<item_id>/profile/<profile_id>/edit/",
        pack_views.edit_weapon_profile,
        name="pack-edit-weapon-profile",
    ),
    path(
        "pack/<id>/item/<item_id>/profile/<profile_id>/delete/",
        pack_views.delete_weapon_profile,
        name="pack-delete-weapon-profile",
    ),
    # TinyMCE upload
    path(
        "tinymce/upload/",
        gyrinx.core.views.tinymce_upload,
        name="tinymce-upload",
    ),
    # Banner dismissal
    path(
        "banner/dismiss/",
        gyrinx.core.views.dismiss_banner,
        name="dismiss-banner",
    ),
    # Banner click tracking
    path(
        "banner/<id>/click/",
        gyrinx.core.views.track_banner_click,
        name="track-banner-click",
    ),
]
