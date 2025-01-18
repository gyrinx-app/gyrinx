from django.urls import path

from . import views

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]

app_name = "core"
urlpatterns = [
    path("", views.index, name="index"),
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
        "list/<id>/fighter/<fighter_id>/gear",
        views.edit_list_fighter_gear,
        name="list-fighter-gear-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/archive",
        views.archive_list_fighter,
        name="list-fighter-archive",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons",
        views.edit_list_fighter_weapons,
        name="list-fighter-weapons-edit",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/weapons/<assign_id>/delete",
        views.delete_list_fighter_weapon,
        name="list-fighter-weapon-delete",
    ),
    path(
        "list/<id>/fighter/<fighter_id>/embed",
        views.embed_list_fighter,
        name="list-fighter-embed",
    ),
    path("list/<id>/print", views.ListPrintView.as_view(), name="list-print"),
]
