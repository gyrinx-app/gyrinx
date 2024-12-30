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
    path("list/<id>/edit", views.edit_list, name="list-edit"),
    path("list/<id>/fighters/new", views.new_list_fighter, name="list-fighter-new"),
    path(
        "list/<id>/fighter/<fighter_id>",
        views.edit_list_fighter,
        name="list-fighter-edit",
    ),
    path("list/<id>/print", views.ListPrintView.as_view(), name="list-print"),
    path("cookies", views.cookies, name="cookies"),
]
