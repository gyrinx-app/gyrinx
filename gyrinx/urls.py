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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.admindocs import urls as admindocs_urls
from django.urls import include, path, re_path

from gyrinx import views_debug
from gyrinx.admin_site import admin_gated_patterns
from gyrinx.pages import views

admin.site.site_header = "Gyrinx Admin"

# Platform debug URLs — always registered; the views themselves check DEBUG and
# 404 when it is off, so routing stays identical in parallel test workers where
# DEBUG may be False at import time but True via @override_settings.
# The edition's debug routes (balance sheet, list actions, print lab) live under
# /n23/_debug/ with the rest of the edition.
_debug_urls = [
    path(
        "_debug/test-plans/",
        views_debug.debug_test_plan_index,
        name="debug_test_plans",
    ),
    path(
        "_debug/test-plans/<str:filename>",
        views_debug.debug_test_plan_detail,
        name="debug_test_plan_detail",
    ),
    path(
        "_debug/design-system/",
        views_debug.debug_design_system,
        name="debug_design_system",
    ),
]

urlpatterns = (
    debug_toolbar_urls()
    + [
        path("robots.txt", views.robots_txt, name="robots_txt"),
        path("", include("n23.core.urls")),
        path("api/", include("gyrinx.api.urls")),
        path("tasks/", include("gyrinx.tasks.urls")),
        path("accounts/", include("allauth.urls")),
        # admindocs decorates its views with staff_member_required, which knows
        # nothing about the admin's 2FA gate — route it through the same check.
        # A bare list keeps admindocs' URL names unnamespaced, as base_site.html
        # expects.
        path("admin/doc/", include(admin_gated_patterns(admindocs_urls.urlpatterns))),
        path("400/", views.error_400, name="error_400"),
        path("403/", views.error_403, name="error_403"),
        path("404/", views.error_404, name="error_404"),
        path("500/", views.error_500, name="error_500"),
        path("admin/", admin.site.urls),
        path("tinymce/", include("tinymce.urls")),
    ]
    + _debug_urls
    + [
        re_path(r"^(?P<url>.*/)$", views.flatpage),
    ]
)

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers
handler400 = "gyrinx.pages.views.error_400"
handler403 = "gyrinx.pages.views.error_403"
handler404 = "gyrinx.pages.views.error_404"
handler500 = "gyrinx.pages.views.error_500"
