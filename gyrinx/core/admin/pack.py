from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.pack import (
    CustomContentPack,
    CustomContentPackItem,
    CustomContentPackPermission,
)

__all__ = [
    "CustomContentPackAdmin",
    "CustomContentPackItemAdmin",
    "CustomContentPackPermissionAdmin",
]


@admin.register(CustomContentPack)
class CustomContentPackAdmin(BaseAdmin):
    list_display = ["name", "listed", "owner", "created"]
    search_fields = ["name", "owner__username"]
    list_filter = ["listed", "created"]
    fields = ["name", "summary", "description", "listed", "owner"]


@admin.register(CustomContentPackItem)
class CustomContentPackItemAdmin(BaseAdmin):
    list_display = ["pack", "content_type", "content_object_link", "owner"]
    search_fields = ["pack__name", "owner__username"]
    list_filter = ["pack", "content_type"]
    fields = ["pack", "content_type", "object_id", "content_object_link", "owner"]
    readonly_fields = ["content_object_link"]

    @admin.display(description="Content Object")
    def content_object_link(self, obj):
        if not obj.content_type_id or not obj.object_id:
            return "-"
        content_object = obj.content_object
        if content_object is None:
            return f"(missing: {obj.object_id})"
        url = reverse(
            f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
            args=[obj.object_id],
        )
        return format_html('<a href="{}">{}</a>', url, content_object)


@admin.register(CustomContentPackPermission)
class CustomContentPackPermissionAdmin(BaseAdmin):
    list_display = ["pack", "user", "role", "created"]
    search_fields = ["pack__name", "user__username"]
    list_filter = ["role"]
    fields = ["pack", "user", "role", "owner"]
