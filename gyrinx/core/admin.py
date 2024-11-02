from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Build, BuildFighter


class BuildForm(forms.ModelForm):
    pass


@admin.display(description="Cost")
def cost(obj):
    return f"{obj.cost()}¢"


@admin.register(Build)
class BuildAdmin(SimpleHistoryAdmin):
    form = BuildForm
    fields = ["name", "content_house", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_house"]
    search_fields = ["name", "content_house__name"]


class BuildFighterForm(forms.ModelForm):
    pass


@admin.register(BuildFighter)
class BuildFighterAdmin(SimpleHistoryAdmin):
    form = BuildFighterForm
    fields = ["name", "content_fighter", "build", cost]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "build"]
    search_fields = ["name", "content_fighter__type", "build__name"]
