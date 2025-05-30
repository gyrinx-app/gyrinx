from django.contrib import admin

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.campaign import Campaign, CampaignAction


@admin.register(Campaign)
class CampaignAdmin(BaseAdmin):
    list_display = ["name", "public"]
    search_fields = ["name"]
    list_filter = ["public"]
    fields = ["name", "owner", "public", "summary", "narrative"]


@admin.register(CampaignAction)
class CampaignActionAdmin(BaseAdmin):
    list_display = ["campaign", "user", "description", "dice_count", "created"]
    search_fields = ["campaign__name", "user__username", "description"]
    list_filter = ["campaign", "created"]
    readonly_fields = ["dice_results", "dice_total"]
    fields = [
        "campaign",
        "user",
        "description",
        "dice_count",
        "dice_results",
        "dice_total",
        "outcome",
    ]
