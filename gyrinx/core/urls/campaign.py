from django.urls import path

from ..views import battle
from ..views.campaign import actions as campaign_actions
from ..views.campaign import assets as campaign_assets
from ..views.campaign import attributes as campaign_attributes
from ..views.campaign import battles as campaign_battles
from ..views.campaign import captured as campaign_captured
from ..views.campaign import copy as campaign_copy
from ..views.campaign import crud as campaign_crud
from ..views.campaign import lifecycle as campaign_lifecycle
from ..views.campaign import lists as campaign_lists
from ..views.campaign import packs as campaign_packs
from ..views.campaign import resources as campaign_resources
from ..views.campaign import sub_assets as campaign_sub_assets
from ..views.campaign import views as campaign_views

patterns = [
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
    path(
        "campaign/<id>/pin",
        campaign_lifecycle.toggle_campaign_pin,
        name="campaign-pin",
    ),
    path(
        "campaign/<id>/star",
        campaign_lifecycle.toggle_campaign_star,
        name="campaign-star",
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
    path(
        "campaign/<id>/packs/<pack_id>/required",
        campaign_packs.campaign_pack_set_required,
        name="campaign-pack-set-required",
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
]
