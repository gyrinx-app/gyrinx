from django.contrib import admin

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.events import Event


@admin.register(Event)
class EventAdmin(BaseAdmin):
    """Admin configuration for Event model."""

    list_display = [
        "created",
        "owner",
        "verb",
        "noun",
        "object_type",
        "object_id",
        "ip_address",
        "session_id",
    ]

    list_filter = [
        "created",
        "noun",
        "verb",
        "object_type",
    ]

    search_fields = [
        "owner__username",
        "owner__email",
        "ip_address",
        "object_id",
        "session_id",
    ]

    readonly_fields = [
        "id",
        "created",
        "modified",
        "object",
    ]

    fieldsets = (
        (
            "Event Information",
            {
                "fields": (
                    "id",
                    "created",
                    "modified",
                    "owner",
                    "noun",
                    "verb",
                )
            },
        ),
        (
            "Object Information",
            {
                "fields": (
                    "object_type",
                    "object_id",
                    "object",
                )
            },
        ),
        (
            "Context",
            {
                "fields": (
                    "ip_address",
                    "session_id",
                    "context",
                )
            },
        ),
    )

    date_hierarchy = "created"
    ordering = ["-created"]

    def has_add_permission(self, request):
        """Events should only be created programmatically."""
        return False

    def has_change_permission(self, request, obj=None):
        """Events should not be editable."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete events."""
        return request.user.is_superuser
