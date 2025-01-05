from django.urls import path

from . import views

app_name = "feedback"
urlpatterns = [path("", views.form, name="form")]
