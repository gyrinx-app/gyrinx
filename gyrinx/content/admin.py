from django import forms
from django.contrib import admin
from django.db import models
from django.db.models import Case, When
from django.db.models.functions import Cast

from .models import (
    ContentBook,
    ContentEquipment,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentHouse,
    ContentPageRef,
    ContentPolicy,
    ContentRule,
    ContentSkill,
    ContentWeaponProfile,
    ContentWeaponTrait,
)


class ContentAdmin(admin.ModelAdmin):
    def __init__(self, model, admin_site):
        self.list_display = [
            f.name
            for f in model._meta.fields
            if f.name not in ["created", "modified", "id"]
        ]
        self.list_display += ["id"]
        self.initial_list_display = self.list_display.copy()
        super().__init__(model, admin_site)


class ContentTabularInline(admin.TabularInline):
    show_change_link = True

    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


class ContentStackedInline(admin.StackedInline):
    show_change_link = True

    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


class ContentWeaponProfileInline(ContentTabularInline):
    model = ContentWeaponProfile


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "category__name"]

    inlines = [ContentWeaponProfileInline]


class ContentFighterEquipmentListItemAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.equipment_id:
            self.fields[
                "weapon_profile"
            ].queryset = ContentWeaponProfile.objects.filter(
                equipment=self.instance.equipment
            )


@admin.register(ContentFighterEquipmentListItem)
class ContentFighterEquipmentListItemAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profile__name"]
    form = ContentFighterEquipmentListItemAdminForm


class ContentFighterDefaultAssignmentAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.equipment_id:
            self.fields[
                "weapon_profiles_field"
            ].queryset = ContentWeaponProfile.objects.filter(
                equipment=self.instance.equipment
            )


@admin.register(ContentFighterDefaultAssignment)
class ContentFighterDefaultAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profiles_field__name"]
    form = ContentFighterDefaultAssignmentAdminForm


class ContentFighterEquipmentInline(ContentTabularInline):
    model = ContentFighterEquipmentListItem


class ContentFighterDefaultAssignmentInline(ContentTabularInline):
    model = ContentFighterDefaultAssignment


class ContentFighterForm(forms.ModelForm):
    pass


@admin.register(ContentFighter)
class ContentFighterAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentFighterForm
    search_fields = ["type", "category", "house__name"]
    inlines = [ContentFighterEquipmentInline, ContentFighterDefaultAssignmentInline]


class ContentFighterInline(ContentTabularInline):
    model = ContentFighter


@admin.register(ContentHouse)
class ContentHouseAdmin(ContentAdmin, admin.ModelAdmin):
    list_display_links = ["name"]
    search_fields = ["name"]
    inlines = [ContentFighterInline]


@admin.register(ContentPolicy)
class ContentPolicyAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentSkill)
class ContentSkillAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentWeaponTrait)
class ContentWeaponTraitAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentWeaponProfile)
class ContentWeaponProfileAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
    list_display_links = ["equipment", "name"]


class ContentPageRefInline(ContentTabularInline):
    model = ContentPageRef
    extra = 0
    fields = ["title", "book", "page", "category", "description"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            page_int=Case(
                When(
                    page="",
                    then=0,
                ),
                default=Cast("page", models.IntegerField()),
            )
        ).order_by("page_int")


@admin.register(ContentBook)
class ContentBookAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["title", "shortname", "description"]

    inlines = [ContentPageRefInline]


@admin.register(ContentPageRef)
class ContentPageRefAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["title", "page", "description"]

    inlines = [ContentPageRefInline]


@admin.register(ContentRule)
class ContentRuleAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
