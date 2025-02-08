from django.contrib import admin

from gyrinx.api.models import WebhookRequest


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


@admin.register(WebhookRequest)
class WebhookRequestAdmin(admin.ModelAdmin):
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
