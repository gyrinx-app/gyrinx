from django.contrib import admin
from django.utils.html import format_html

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models import UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(BaseAdmin):
    list_display = (
        "thumbnail",
        "original_filename",
        "owner",
        "file_size_display",
        "uploaded_at",
        "access_count",
    )
    list_filter = ("content_type", "uploaded_at")
    search_fields = ("original_filename", "owner__username", "owner__email")
    readonly_fields = (
        "file",
        "file_url",
        "original_filename",
        "file_size",
        "file_size_mb",
        "content_type",
        "uploaded_at",
        "last_accessed",
        "access_count",
        "owner",
    )
    date_hierarchy = "uploaded_at"
    ordering = ("-uploaded_at",)

    def thumbnail(self, obj):
        """Display a thumbnail for image files."""
        if obj.content_type and obj.content_type.startswith("image/"):
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px;" />',
                obj.file_url,
            )
        return "-"

    thumbnail.short_description = "Preview"

    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return f"{obj.file_size_mb:.2f} MB"

    file_size_display.short_description = "Size"
    file_size_display.admin_order_field = "file_size"

    def has_add_permission(self, request):
        """Disable manual file uploads through admin."""
        return False
