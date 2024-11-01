from django import forms
from django.contrib import admin

from .models import Build, BuildFighter


class BuildForm(forms.ModelForm):
    pass


@admin.register(Build)
class BuildAdmin(admin.ModelAdmin):
    form = BuildForm


class BuildFighterForm(forms.ModelForm):
    pass


@admin.register(BuildFighter)
class BuildFighterAdmin(admin.ModelAdmin):
    form = BuildFighterForm
