from django.contrib import admin

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.campaign import Campaign


@admin.register(Campaign)
class CampaignAdmin(BaseAdmin):
    list_display = ["name", "public"]
    search_fields = ["name"]
    list_filter = ["public"]
    fields = ["name", "owner", "public", "summary", "narrative"]
