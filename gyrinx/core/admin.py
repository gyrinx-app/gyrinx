from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import List, ListFighter, ListFighterEquipmentAssignment


class ListForm(forms.ModelForm):
    pass


@admin.display(description="Cost")
def cost(obj):
    return f"{obj.cost_int()}¢"


class ListFighterInline(admin.TabularInline):
    model = ListFighter
    extra = 1
    fields = ["name", "content_fighter"]
    show_change_link = True


@admin.register(List)
class ListAdmin(SimpleHistoryAdmin):
    form = ListForm
    fields = ["name", "content_house", "owner", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_house"]
    search_fields = ["name", "content_house__name"]

    inlines = [ListFighterInline]


class ListFighterForm(forms.ModelForm):
    pass


@admin.register(ListFighter)
class ListFighterAdmin(SimpleHistoryAdmin):
    form = ListFighterForm
    fields = ["name", "content_fighter", "owner", "list", "skills", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "list"]
    search_fields = ["name", "content_fighter__type", "list__name"]

    class ListFighterEquipmentAssignmentInline(admin.TabularInline):
        model = ListFighterEquipmentAssignment
        extra = 1
        fields = ["content_equipment", "weapon_profile"]

    inlines = [ListFighterEquipmentAssignmentInline]


@admin.register(ListFighterEquipmentAssignment)
class ListFighterEquipmentAssignmentAdmin(SimpleHistoryAdmin):
    fields = ["list_fighter", "content_equipment", "weapon_profile"]
    list_display = ["list_fighter", "content_equipment", "weapon_profile"]
    search_fields = [
        "list_fighter__name",
        "content_equipment__name",
        "weapon_profile__name",
    ]
