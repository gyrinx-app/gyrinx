from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.index, name="index"),
    path("content/", views.content, name="content"),
    path("content/gangs", views.content_gangs, name="content-gangs"),
    path("content/equipment", views.content_equipment, name="content-equipment"),
    path("content/index", views.content_index, name="content-index"),
    path("dice/", views.dice, name="dice"),
    path("lists/", views.lists, name="lists"),
    path("list/<id>/print", views.list_print, name="list-print"),
]
