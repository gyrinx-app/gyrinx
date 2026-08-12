from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html

from gyrinx.analytics.models import Event, EventVerb
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.site.models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = [
        "get_banner_preview",
        "colour",
        "live_n23",
        "live_n26",
        "get_click_count",
        "created",
        "modified",
    ]
    list_filter = ["live_n23", "live_n26", "colour", "created"]
    search_fields = ["text", "cta_text"]
    readonly_fields = ["created", "modified", "get_click_count"]

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
                "fields": ("live_n23", "live_n26", "get_click_count"),
                "description": (
                    "Each side of the site shows at most one live banner; "
                    "tick both to show this one everywhere"
                ),
            },
        ),
        (
            "Metadata",
            {"fields": ("created", "modified"), "classes": ("collapse",)},
        ),
    )

    def get_banner_preview(self, obj):
        """Show a preview of the banner text (truncated)."""
        live = [name for name, flag in obj.LIVE_FLAGS.items() if getattr(obj, flag)]
        status = f"🟢 LIVE {'+'.join(live)}" if live else "⚪ Draft"
        text_preview = obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
        return format_html(
            "<strong>{}</strong><br><small>{}</small>", status, text_preview
        )

    get_banner_preview.short_description = "Banner"

    def get_click_count(self, obj):
        """Count the number of click events for this banner."""
        content_type = ContentType.objects.get_for_model(Banner)
        count = Event.objects.filter(
            noun=PlatformNoun.BANNER,
            verb=EventVerb.CLICK,
            object_id=obj.id,
            object_type=content_type,
        ).count()
        return count

    get_click_count.short_description = "Banner Clicks"

    def save_model(self, request, obj, form, change):
        """Override to ensure owner is set on new banners."""
        if not change:  # New object
            obj.owner = request.user
        super().save_model(request, obj, form, change)
