from django.contrib import admin

from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.action import ListAction


@admin.register(ListAction)
class ListActionAdmin(BaseAdmin):
    list_display = [
        "list__name",
        "action_type",
        "subject_type",
        "description",
        "owner",
        "created",
    ]
    list_select_related = [
        "list",
        "owner",
        "list_fighter",
        "list_fighter_equipment_assignment",
    ]
    search_fields = ["list__name", "owner__username", "description"]
    list_filter = ["action_type", "subject_type", "created"]
    autocomplete_fields = ["list", "list_fighter", "list_fighter_equipment_assignment"]
    fields = [
        "list",
        "action_type",
        "subject_app",
        "subject_type",
        "subject_id",
        "description",
        "rating_delta",
        "stash_delta",
        "credits_delta",
        "rating_before",
        "stash_before",
        "credits_before",
        "list_fighter",
        "list_fighter_equipment_assignment",
    ]
