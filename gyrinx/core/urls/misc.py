from django.urls import path

import gyrinx.core.views

patterns = [
    path("", gyrinx.core.views.index, name="index"),
    path("accounts/", gyrinx.core.views.account_home, name="account_home"),
    path(
        "accounts/change-username/",
        gyrinx.core.views.change_username,
        name="change-username",
    ),
    path(
        "accounts/badge/",
        gyrinx.core.views.badge_settings,
        name="badge-settings",
    ),
    path("dice/", gyrinx.core.views.dice, name="dice"),
    # Users
    path("user/<slug_or_id>", gyrinx.core.views.user, name="user"),
    # Impersonation (superuser only)
    path(
        "impersonate/<int:user_id>/start",
        gyrinx.core.views.start_impersonation,
        name="impersonate-start",
    ),
    path(
        "impersonate/stop",
        gyrinx.core.views.stop_impersonation,
        name="impersonate-stop",
    ),
    # TinyMCE upload
    path(
        "tinymce/upload/",
        gyrinx.core.views.tinymce_upload,
        name="tinymce-upload",
    ),
    # Banner dismissal
    path(
        "banner/dismiss/",
        gyrinx.core.views.dismiss_banner,
        name="dismiss-banner",
    ),
    # Banner click tracking
    path(
        "banner/<id>/click/",
        gyrinx.core.views.track_banner_click,
        name="track-banner-click",
    ),
]
