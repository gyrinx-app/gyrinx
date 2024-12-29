from django.urls import path

from . import views

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
    path("list/<id>/print", views.ListPrintView.as_view(), name="list-print"),
    path("cookies", views.cookies, name="cookies"),
]
