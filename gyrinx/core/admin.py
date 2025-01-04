from django import forms
from django.contrib import admin
from django.db import models
from simple_history.admin import SimpleHistoryAdmin
from tinymce.widgets import TinyMCE

from gyrinx.content.models import ContentWeaponProfile

from .models import List, ListFighter, ListFighterEquipmentAssignment


class BaseAdmin(SimpleHistoryAdmin):
    formfield_overrides = {
        models.TextField: {"widget": TinyMCE},
    }


@admin.display(description="Cost")
def cost(obj):
    return obj.cost_display()


class ListFighterInline(admin.TabularInline):
    model = ListFighter
    extra = 1
    fields = ["name", "owner", "content_fighter", cost]
    readonly_fields = [cost]
    show_change_link = True


class ListForm(forms.ModelForm):
    pass


@admin.register(List)
class ListAdmin(BaseAdmin):
    form = ListForm
    fields = ["name", "content_house", "owner", "public", cost, "narrative"]
    readonly_fields = [cost]
    list_display = ["name", "content_house", "owner", "public", cost]
    search_fields = ["name", "content_house__name"]

    inlines = [ListFighterInline]


class ListFighterForm(forms.ModelForm):
    pass


@admin.display(description="Weapon Profiles")
def weapon_profiles_list(obj: ListFighterEquipmentAssignment):
    weapon_profiles = obj.weapon_profiles()
    return ", ".join([f"{wp.name}" for wp in weapon_profiles])


class ListFighterEquipmentAssignmentInline(admin.TabularInline):
    model = ListFighterEquipmentAssignment
    extra = 1
    fields = ["content_equipment", weapon_profiles_list, cost]
    readonly_fields = [weapon_profiles_list, cost]
    show_change_link = True


@admin.register(ListFighter)
class ListFighterAdmin(BaseAdmin):
    form = ListFighterForm
    fields = ["name", "content_fighter", "owner", "list", "skills", cost, "narrative"]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "list"]
    search_fields = ["name", "content_fighter__type", "list__name"]

    inlines = [ListFighterEquipmentAssignmentInline]


class ListFighterEquipmentAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            # Disable the fighter field if it's already set
            self.fields["list_fighter"].disabled = True
            self.fields["content_equipment"].disabled = True
            # Filter available weapon profiles based on the equipment
            if self.instance.content_equipment:
                self.fields["weapon_profiles_field"].queryset = self.fields[
                    "weapon_profiles_field"
                ].queryset.filter(equipment=self.instance.content_equipment)


@admin.register(ListFighterEquipmentAssignment)
class ListFighterEquipmentAssignmentAdmin(BaseAdmin):
    form = ListFighterEquipmentAssignmentForm

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Only show weapon profiles that have a cost
        if db_field.name == "weapon_profiles_field":
            kwargs["queryset"] = ContentWeaponProfile.objects.filter(cost__gt=0)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    fields = [
        "list_fighter",
        "content_equipment",
        "weapon_profiles_field",
        cost,
    ]
    readonly_fields = [cost]
    list_display = [
        "list_fighter",
        "content_equipment",
        weapon_profiles_list,
    ]
    search_fields = [
        "list_fighter__name",
        "content_equipment__name",
        weapon_profiles_list,
    ]
