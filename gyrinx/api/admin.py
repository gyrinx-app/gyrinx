from django.contrib import admin

from gyrinx.api.models import WebhookRequest


@admin.register(WebhookRequest)
class WebhookRequestAdmin(admin.ModelAdmin):
    search_fields = ["source", "event"]
    list_display = ["source", "event", "created"]
    readonly_fields = ["source", "event", "payload", "signature", "created"]
    list_filter = ["source", "event"]
