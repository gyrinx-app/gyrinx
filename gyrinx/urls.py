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
from django.urls import include, path, re_path

from gyrinx.core.views import debug as debug_views
from gyrinx.pages import views

admin.site.site_header = "Gyrinx Admin"

# Debug URLs - always registered, views check DEBUG and return 404 if disabled.
# This ensures consistent URL routing in parallel test workers where DEBUG
# may be False at import time but True via @override_settings.
_debug_urls = [
    path(
        "_debug/test-plans/",
        debug_views.debug_test_plan_index,
        name="debug_test_plans",
    ),
    path(
        "_debug/test-plans/<str:filename>",
        debug_views.debug_test_plan_detail,
        name="debug_test_plan_detail",
    ),
    path(
        "_debug/list/<uuid:list_id>/actions/",
        debug_views.debug_list_actions,
        name="debug_list_actions",
    ),
]

urlpatterns = (
    debug_toolbar_urls()
    + [
        path("", include("gyrinx.core.urls")),
        path("api/", include("gyrinx.api.urls")),
        path("tasks/", include("gyrinx.tasks.urls")),
        path("accounts/", include("allauth.urls")),
        path("admin/doc/", include("django.contrib.admindocs.urls")),
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
