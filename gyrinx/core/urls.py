from django.urls import path

import gyrinx.core.views

from .views import campaign, list

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]

app_name = "core"
urlpatterns = [
    path("", gyrinx.core.views.index, name="index"),
    path("accounts/", gyrinx.core.views.account_home, name="account_home"),
    path("dice/", gyrinx.core.views.dice, name="dice"),
    path("lists/", list.ListsListView.as_view(), name="lists"),
    path("lists/new", list.new_list, name="lists-new"),
    path("list/<id>", list.ListDetailView.as_view(), name="list"),
    path("list/<id>/about", list.ListAboutDetailView.as_view(), name="list-about"),
    path("list/<id>/edit", list.edit_list, name="list-edit"),
    path("list/<id>/clone", list.clone_list, name="list-clone"),
    path("list/<id>/fighters/new", list.new_list_fighter, name="list-fighter-new"),
    path(
        "list/<id>/fighters/archived",
        list.ListArchivedFightersView.as_view(),
        name="list-archived-fighters",
    ),
    path(
        "list/<id>/fighter/<fighter_id>",
        list.edit_list_fighter,
        name="list-fighter-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/clone",
        list.clone_list_fighter,
        name="list-fighter-clone",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills",
        list.edit_list_fighter_skills,
        name="list-fighter-skills-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/powers",
        list.edit_list_fighter_powers,
        name="list-fighter-powers-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear",
        list.edit_list_fighter_equipment,
        name="list-fighter-gear-edit",
        kwargs=dict(
            is_weapon=False,
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/delete",
        list.delete_list_fighter_assign,
        name="list-fighter-gear-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/upgrade/<upgrade_id>/delete",
        list.delete_list_fighter_gear_upgrade,
        name="list-fighter-gear-upgrade-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-upgrade-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/disable",
        list.disable_list_fighter_default_assign,
        name="list-fighter-gear-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/disable",
        list.disable_list_fighter_default_assign,
        name="list-fighter-weapons-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/convert",
        list.convert_list_fighter_default_assign,
        name="list-fighter-weapons-default-convert",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-convert",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/archive",
        list.archive_list_fighter,
        name="list-fighter-archive",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/delete",
        list.delete_list_fighter,
        name="list-fighter-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons",
        list.edit_list_fighter_equipment,
        name="list-fighter-weapons-edit",
        kwargs=dict(
            is_weapon=True,
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/cost",
        list.edit_list_fighter_assign_cost,
        name="list-fighter-weapon-cost-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-cost-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/delete",
        list.delete_list_fighter_assign,
        name="list-fighter-weapon-delete",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessories",
        list.edit_list_fighter_weapon_accessories,
        name="list-fighter-weapon-accessories-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessory/<accessory_id>/delete",
        list.delete_list_fighter_weapon_accessory,
        name="list-fighter-weapon-accessory-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/upgrade",
        list.edit_list_fighter_weapon_upgrade,
        name="list-fighter-weapon-upgrade-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-upgrade-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/embed",
        list.embed_list_fighter,
        name="list-fighter-embed",
    ),
    path("list/<id>/print", list.ListPrintView.as_view(), name="list-print"),
    # Users
    path("user/<slug_or_id>", gyrinx.core.views.user, name="user"),
    # Campaigns
    path("campaigns/", campaign.Campaigns.as_view(), name="campaigns"),
    path("campaigns/new/", campaign.new_campaign, name="campaigns-new"),
    path("campaign/<id>", campaign.CampaignDetailView.as_view(), name="campaign"),
    path("campaign/<id>/edit/", campaign.edit_campaign, name="campaign-edit"),
    path(
        "campaign/<id>/lists/add",
        campaign.campaign_add_lists,
        name="campaign-add-lists",
    ),
]
