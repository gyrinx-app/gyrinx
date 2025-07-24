from django.contrib import admin
from django.utils.html import format_html

from gyrinx.core.models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = [
        "get_banner_preview",
        "colour",
        "is_live",
        "created",
        "modified",
    ]
    list_filter = ["is_live", "colour", "created"]
    search_fields = ["text", "cta_text"]
    readonly_fields = ["created", "modified"]

    fieldsets = (
        ("Banner Content", {"fields": ("text", "icon", "colour")}),
        (
            "Call to Action",
            {
                "fields": ("cta_text", "cta_url"),
                "description": "Optional call-to-action button",
            },
        ),
        (
            "Status",
            {
                "fields": ("is_live",),
                "description": "Only one banner can be live at a time",
            },
        ),
        (
            "Metadata",
            {"fields": ("created", "modified"), "classes": ("collapse",)},
        ),
    )

    def get_banner_preview(self, obj):
        """Show a preview of the banner text (truncated)."""
        status = "🟢 LIVE" if obj.is_live else "⚪ Draft"
        text_preview = obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
        return format_html(
            "<strong>{}</strong><br><small>{}</small>", status, text_preview
        )

    get_banner_preview.short_description = "Banner"

    def save_model(self, request, obj, form, change):
        """Override to ensure owner is set on new banners."""
        if not change:  # New object
            obj.owner = request.user
        super().save_model(request, obj, form, change)
