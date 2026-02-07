from django.contrib import admin

from gyrinx.admin import GyTabularInline
from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignListAttributeAssignment,
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


class CampaignAttributeValueInline(GyTabularInline):
    model = CampaignAttributeValue
    extra = 0
    fields = ["name", "description", "colour", "owner"]


@admin.register(CampaignAttributeType)
class CampaignAttributeTypeAdmin(BaseAdmin):
    list_display = ["name", "campaign", "is_single_select", "description"]
    search_fields = ["name", "campaign__name"]
    list_filter = ["campaign", "is_single_select"]
    fields = ["name", "campaign", "description", "is_single_select", "owner"]

    inlines = [CampaignAttributeValueInline]


class CampaignListAttributeAssignmentInline(GyTabularInline):
    model = CampaignListAttributeAssignment
    extra = 0
    fields = ["campaign", "attribute_value", "list", "owner"]


@admin.register(CampaignAttributeValue)
class CampaignAttributeValueAdmin(BaseAdmin):
    list_display = ["name", "attribute_type", "colour", "description"]
    search_fields = ["name", "attribute_type__name"]
    list_filter = ["attribute_type__campaign"]
    fields = ["name", "attribute_type", "description", "colour", "owner"]

    inlines = [CampaignListAttributeAssignmentInline]
