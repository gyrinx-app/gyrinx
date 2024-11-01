from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Build, BuildFighter


class BuildForm(forms.ModelForm):
    pass


@admin.register(Build)
class BuildAdmin(SimpleHistoryAdmin):
    form = BuildForm


class BuildFighterForm(forms.ModelForm):
    pass


@admin.register(BuildFighter)
class BuildFighterAdmin(SimpleHistoryAdmin):
    form = BuildFighterForm
