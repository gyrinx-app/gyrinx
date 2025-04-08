from django.urls import path

from . import views

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]

app_name = "core"
urlpatterns = [
    path("", views.index, name="index"),
    path("accounts/", views.account_home, name="account_home"),
    path("content/", views.content, name="content"),
    path("content/gangs", views.GangIndexView.as_view(), name="content-gangs"),
    path(
        "content/equipment",
        views.EquipmentIndexView.as_view(),
        name="content-equipment",
    ),
    path("content/index", views.ContentIndexIndexView.as_view(), name="content-index"),
    path("dice/", views.dice, name="dice"),
    path("lists/", views.ListsListView.as_view(), name="lists"),
    path("lists/new", views.new_list, name="lists-new"),
    path("list/<id>", views.ListDetailView.as_view(), name="list"),
    path("list/<id>/about", views.ListAboutDetailView.as_view(), name="list-about"),
    path("list/<id>/edit", views.edit_list, name="list-edit"),
    path("list/<id>/clone", views.clone_list, name="list-clone"),
    path("list/<id>/fighters/new", views.new_list_fighter, name="list-fighter-new"),
    path(
        "list/<id>/fighters/archived",
        views.ListArchivedFightersView.as_view(),
        name="list-archived-fighters",
    ),
    path(
        "list/<id>/fighter/<fighter_id>",
        views.edit_list_fighter,
        name="list-fighter-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/clone",
        views.clone_list_fighter,
        name="list-fighter-clone",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/skills",
        views.edit_list_fighter_skills,
        name="list-fighter-skills-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/powers",
        views.edit_list_fighter_powers,
        name="list-fighter-powers-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear",
        views.edit_list_fighter_gear,
        name="list-fighter-gear-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/delete",
        views.delete_list_fighter_assign,
        name="list-fighter-gear-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/upgrade/<upgrade_id>/delete",
        views.delete_list_fighter_gear_upgrade,
        name="list-fighter-gear-upgrade-delete",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-upgrade-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/gear/<assign_id>/disable",
        views.disable_list_fighter_default_assign,
        name="list-fighter-gear-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-gear-edit",
            action_name="core:list-fighter-gear-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/disable",
        views.disable_list_fighter_default_assign,
        name="list-fighter-weapons-default-disable",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-disable",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/convert",
        views.convert_list_fighter_default_assign,
        name="list-fighter-weapons-default-convert",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapons-default-convert",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/archive",
        views.archive_list_fighter,
        name="list-fighter-archive",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/delete",
        views.delete_list_fighter,
        name="list-fighter-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons",
        views.edit_list_fighter_weapons,
        name="list-fighter-weapons-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/cost",
        views.edit_list_fighter_assign_cost,
        name="list-fighter-weapon-cost-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-cost-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/delete",
        views.delete_list_fighter_assign,
        name="list-fighter-weapon-delete",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-delete",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessories",
        views.edit_list_fighter_weapon_accessories,
        name="list-fighter-weapon-accessories-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/accessory/<accessory_id>/delete",
        views.delete_list_fighter_weapon_accessory,
        name="list-fighter-weapon-accessory-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/upgrade",
        views.edit_list_fighter_weapon_upgrade,
        name="list-fighter-weapon-upgrade-edit",
        kwargs=dict(
            back_name="core:list-fighter-weapons-edit",
            action_name="core:list-fighter-weapon-upgrade-edit",
        ),
    ),
    path(
        "list/<id>/fighter/<fighter_id>/embed",
        views.embed_list_fighter,
        name="list-fighter-embed",
    ),
    path("list/<id>/print", views.ListPrintView.as_view(), name="list-print"),
    # Users
    path("user/<slug_or_id>", views.user, name="user"),
]
