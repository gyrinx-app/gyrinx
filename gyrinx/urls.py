"""Platform routes, edition mounts and the flatpage fallback."""

from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.admindocs import urls as admindocs_urls
from django.urls import include, path, re_path

from gyrinx import views_debug
from gyrinx.accounts import views as account_views
from gyrinx.accounts.public_profiles import user_profile
from gyrinx.admin_site import admin_gated_patterns
from gyrinx.pages import views

admin.site.site_header = "Gyrinx Admin"

# Register debug routes regardless of import-time DEBUG. Their views return
# 404 when disabled, including in tests that change settings after import.
_debug_urls = [
    path(
        "_debug/login/",
        views_debug.debug_agent_login,
        name="debug_agent_login",
    ),
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
        # The slash distinguishes this from legacy usernames beginning with "@".
        path("user/@<str:username>/", user_profile, name="user-profile"),
        path(
            "accounts/settings/",
            account_views.SettingsView.as_view(),
            name="account-settings",
        ),
        path("accounts/security/", account_views.security, name="account-security"),
        path("accounts/email/", account_views.legacy_email),
        path("accounts/password/change/", account_views.legacy_password),
        path("accounts/password/set/", account_views.CombinedPasswordSetView.as_view()),
        path("accounts/2fa/", account_views.legacy_security),
        path("accounts/sessions/", account_views.legacy_sessions),
        path("", include("n23.core.urls")),
        path("n26/", include("n26.urls")),
        path("api/", include("gyrinx.api.urls")),
        path("tasks/", include("gyrinx.tasks.urls")),
        path("accounts/", include("allauth.urls")),
        # Apply the admin MFA gate because admindocs checks only staff membership.
        # Keep its names unnamespaced for admin template links.
        path("admin/doc/", include(admin_gated_patterns(admindocs_urls.urlpatterns))),
        path("400/", views.error_400, name="error_400"),
        path("403/", views.error_403, name="error_403"),
        path("404/", views.error_404, name="error_404"),
        path("500/", views.error_500, name="error_500"),
        path("admin/", admin.site.urls),
        path("tinymce/", include("tinymce.urls")),
        # Resolve changelog routes before the flatpage catch-all.
        path("changelog/", include("n26.core.changelog_urls")),
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
