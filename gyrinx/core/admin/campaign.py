from django.contrib import admin

from gyrinx.admin import GyTabularInline
from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignListResource,
    CampaignResourceType,
)


@admin.register(Campaign)
class CampaignAdmin(BaseAdmin):
    list_display = ["name", "status", "public", "template", "owner", "created"]
    search_fields = ["name", "owner__username"]
    list_filter = ["status", "public", "template", "created"]
    fields = ["name", "owner", "status", "public", "template", "summary", "narrative"]


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


class CampaignAssetInline(GyTabularInline):
    model = CampaignAsset
    extra = 0
    fields = ["name", "description", "holder", "owner"]


@admin.register(CampaignAssetType)
class CampaignAssetTypeAdmin(BaseAdmin):
    list_display = ["name_singular", "campaign", "description"]
    search_fields = ["name_singular", "campaign__name"]
    list_filter = ["campaign"]
    fields = ["name_singular", "campaign", "description", "owner"]

    inlines = [CampaignAssetInline]


class CampaignListResourceInline(GyTabularInline):
    model = CampaignListResource
    extra = 0
    fields = ["list", "campaign", "resource_type", "amount", "owner"]


@admin.register(CampaignResourceType)
class CampaignResourceTypeAdmin(BaseAdmin):
    list_display = ["name", "campaign", "description"]
    search_fields = ["name", "campaign__name"]
    list_filter = ["campaign"]
    fields = ["name", "campaign", "description", "owner"]

    inlines = [CampaignListResourceInline]
