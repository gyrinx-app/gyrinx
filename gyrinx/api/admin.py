from django.contrib import admin, messages

from gyrinx.api.models import WebhookRequest
from gyrinx.api.patreon import process_patreon_webhook


def payload(key, description=None):
    if description is None:
        description = key

    segments = key.split(".")

    @admin.display(description=description)
    def _payload(obj):
        curr = obj.payload
        for segment in segments:
            if segment not in curr:
                return None

            curr = curr.get(segment, {})
        return curr

    return _payload


@admin.action(description="Match selected Patreon webhooks to users")
def match_patreon_webhooks(modeladmin, request, queryset):
    patreon_webhooks = queryset.filter(source="patreon").order_by("created")
    matched = 0
    unmatched = 0
    for wh in patreon_webhooks:
        result = process_patreon_webhook(wh.payload, wh.event)
        if result and result["matched"]:
            matched += 1
        else:
            unmatched += 1
    modeladmin.message_user(
        request,
        f"Processed {matched + unmatched} Patreon webhooks: {matched} matched, {unmatched} unmatched.",
        messages.SUCCESS if matched else messages.WARNING,
    )


@admin.register(WebhookRequest)
class WebhookRequestAdmin(admin.ModelAdmin):
    actions = [match_patreon_webhooks]
    search_fields = ["source", "event"]
    list_display = ["source", "event", "created"]
    readonly_fields = [
        "source",
        "event",
        payload("data.attributes.email", "Email"),
        payload("data.attributes.full_name", "Name"),
        "payload",
        "signature",
        "created",
    ]
    list_filter = ["source", "event"]
