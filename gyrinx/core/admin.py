from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import List, ListFighter, ListFighterEquipmentAssignment


class ListForm(forms.ModelForm):
    pass


@admin.display(description="Cost")
def cost(obj):
    return f"{obj.cost()}¢"


@admin.register(List)
class ListAdmin(SimpleHistoryAdmin):
    form = ListForm
    fields = ["name", "content_house", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_house"]
    search_fields = ["name", "content_house__name"]


class ListFighterForm(forms.ModelForm):
    pass


@admin.register(ListFighter)
class ListFighterAdmin(SimpleHistoryAdmin):
    form = ListFighterForm
    fields = ["name", "content_fighter", "list", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "list"]
    search_fields = ["name", "content_fighter__type", "list__name"]


@admin.register(ListFighterEquipmentAssignment)
class ListFighterEquipmentAssignmentAdmin(SimpleHistoryAdmin):
    fields = ["list_fighter", "content_equipment"]
    list_display = ["list_fighter", "content_equipment"]
    search_fields = ["list_fighter__name", "content_equipment__name"]
