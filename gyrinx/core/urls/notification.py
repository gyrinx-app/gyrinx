"""Notification inbox URL patterns."""

from django.urls import path

from ..views import notification as v

patterns = [
    path("notifications/", v.NotificationInboxView.as_view(), name="notifications"),
    path("notifications/bulk", v.notifications_bulk, name="notifications-bulk"),
    path("notification/<uuid:id>/read", v.notification_read, name="notification-read"),
    path(
        "notification/<uuid:id>/unread",
        v.notification_unread,
        name="notification-unread",
    ),
    path(
        "notification/<uuid:id>/archive",
        v.notification_archive,
        name="notification-archive",
    ),
    path(
        "notification/<uuid:id>/unarchive",
        v.notification_unarchive,
        name="notification-unarchive",
    ),
    path(
        "notification/<uuid:id>/delete",
        v.notification_delete,
        name="notification-delete",
    ),
    path(
        "notification/<uuid:id>/dismiss-banner",
        v.notification_dismiss_banner,
        name="notification-dismiss-banner",
    ),
]
