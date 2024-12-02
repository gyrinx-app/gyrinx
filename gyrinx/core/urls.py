from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.index, name="index"),
    path("content/", views.content, name="content"),
    path("lists/", views.lists, name="lists"),
    path("list/<id>/print", views.list_print, name="list-print"),
]
