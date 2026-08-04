from django.urls import path

import n23.core.views

patterns = [
    path("", n23.core.views.index, name="index"),
    path("accounts/", n23.core.views.account_home, name="account_home"),
    path(
        "accounts/change-username/",
        n23.core.views.change_username,
        name="change-username",
    ),
    path(
        "accounts/badge/",
        n23.core.views.badge_settings,
        name="badge-settings",
    ),
    path("dice/", n23.core.views.dice, name="dice"),
    # Users
    path("user/<slug_or_id>", n23.core.views.user, name="user"),
    # Impersonation (superuser only)
    path(
        "impersonate/<int:user_id>/start",
        n23.core.views.start_impersonation,
        name="impersonate-start",
    ),
    path(
        "impersonate/stop",
        n23.core.views.stop_impersonation,
        name="impersonate-stop",
    ),
    # TinyMCE upload
    path(
        "tinymce/upload/",
        n23.core.views.tinymce_upload,
        name="tinymce-upload",
    ),
    # Banner dismissal
    path(
        "banner/dismiss/",
        n23.core.views.dismiss_banner,
        name="dismiss-banner",
    ),
    # Banner click tracking
    path(
        "banner/<id>/click/",
        n23.core.views.track_banner_click,
        name="track-banner-click",
    ),
]
