"""
URL configuration for gyrinx project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from debug_toolbar.toolbar import debug_toolbar_urls
from django.contrib import admin
from django.urls import include, path, re_path

from gyrinx.pages import views

urlpatterns = debug_toolbar_urls() + [
    path("", include("gyrinx.core.urls")),
    path("api/", include("gyrinx.api.urls")),
    path("accounts/", include("allauth.urls")),
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path(
        "join-the-waiting-list/",
        views.join_the_waiting_list,
        name="join_the_waiting_list",
    ),
    path(
        "join-the-waiting-list/success/",
        views.join_the_waiting_list_success,
        name="join_the_waiting_list_success",
    ),
    path("admin/", admin.site.urls),
    path("tinymce/", include("tinymce.urls")),
    re_path(r"^(?P<url>.*/)$", views.flatpage),
]
