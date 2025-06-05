from django import forms
from django.contrib import admin

from gyrinx.content.models import ContentWeaponProfile
from gyrinx.core.admin.base import BaseAdmin
from gyrinx.forms import group_select

from ..models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterPsykerPowerAssignment,
)


@admin.display(description="Cost")
def cost(obj):
    return obj.cost_display()


class ListFighterInline(admin.TabularInline):
    model = ListFighter
    extra = 1
    fields = ["name", "owner", "content_fighter", "cost_override", cost]
    readonly_fields = [cost]
    show_change_link = True


class ListForm(forms.ModelForm):
    pass


@admin.register(List)
class ListAdmin(BaseAdmin):
    form = ListForm
    fields = [
        "name",
        "content_house",
        "owner",
        "status",
        "original_list",
        "campaign",
        "public",
        cost,
        "narrative",
    ]
    readonly_fields = [cost, "original_list", "campaign"]
    list_display = ["name", "content_house", "owner", "status", "public", cost]
    list_filter = ["status", "public", "content_house"]
    search_fields = ["name", "content_house__name", "campaign__name"]

    inlines = [ListFighterInline]


class ListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.instance, "list"):
            self.fields["additional_rules"].queryset = self.fields[
                "additional_rules"
            ].queryset.filter(tree__house=self.instance.list.content_house)

            self.fields["disabled_default_assignments"].queryset = self.fields[
                "disabled_default_assignments"
            ].queryset.filter(fighter=self.instance.content_fighter)

            self.fields["disabled_pskyer_default_powers"].queryset = self.fields[
                "disabled_pskyer_default_powers"
            ].queryset.filter(fighter=self.instance.content_fighter)

        if hasattr(self.instance, "content_fighter"):
            if not self.instance.content_fighter.can_take_legacy:
                if "legacy_content_fighter" in self.fields:
                    self.fields["legacy_content_fighter"].disabled = True
                    self.fields[
                        "legacy_content_fighter"
                    ].help_text = "This fighter cannot take a legacy content fighter because the underlying content fighter does not support it."

        group_select(self, "content_fighter", key=lambda x: x.cat())
        group_select(self, "legacy_content_fighter", key=lambda x: x.cat())
        group_select(self, "skills", key=lambda x: x.category.name)
        group_select(self, "additional_rules", key=lambda x: x.tree.name)


@admin.display(description="Weapon Profiles")
def weapon_profiles_list(obj: ListFighterEquipmentAssignment):
    weapon_profiles = obj.weapon_profiles()
    return ", ".join([f"{wp.name}" for wp in weapon_profiles])


@admin.display(description="Weapon Accessories")
def weapon_accessories_list(obj: ListFighterEquipmentAssignment):
    weapon_accessories = obj.weapon_accessories()
    return ", ".join([f"{wa.name}" for wa in weapon_accessories])


class ListFighterEquipmentAssignmentInline(admin.TabularInline):
    model = ListFighterEquipmentAssignment
    extra = 1
    fields = ["content_equipment", weapon_profiles_list, weapon_accessories_list, cost]
    readonly_fields = [weapon_profiles_list, weapon_accessories_list, cost]
    show_change_link = True
    fk_name = "list_fighter"


class ListFighterPsykerPowerAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "psyker_power", key=lambda x: x.discipline.name)


class ListFighterPsykerPowerAssignmentInline(admin.TabularInline):
    model = ListFighterPsykerPowerAssignment
    form = ListFighterPsykerPowerAssignmentForm
    extra = 1
    fields = ["psyker_power"]


@admin.register(ListFighter)
class ListFighterAdmin(BaseAdmin):
    form = ListFighterForm
    fields = [
        "name",
        "content_fighter",
        "legacy_content_fighter",
        "owner",
        "list",
        "skills",
        "additional_rules",
        "cost_override",
        cost,
        "narrative",
        "disabled_default_assignments",
        "disabled_pskyer_default_powers",
    ]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "list"]
    search_fields = ["name", "content_fighter__type", "list__name"]

    inlines = [
        ListFighterEquipmentAssignmentInline,
        ListFighterPsykerPowerAssignmentInline,
    ]


class ListFighterEquipmentAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        exists = ListFighterEquipmentAssignment.objects.filter(
            pk=self.instance.pk
        ).exists()
        if exists:
            # Disable the fighter field if it's already set
            self.fields["list_fighter"].disabled = True
            self.fields["content_equipment"].disabled = True
            # Filter available weapon profiles and upgrade based on the equipment
            if hasattr(self.instance, "content_equipment"):
                self.fields["weapon_profiles_field"].queryset = self.fields[
                    "weapon_profiles_field"
                ].queryset.filter(equipment=self.instance.content_equipment)

                self.fields["upgrades_field"].queryset = self.fields[
                    "upgrades_field"
                ].queryset.filter(equipment=self.instance.content_equipment)

        group_select(self, "list_fighter", key=lambda x: x.list.name)
        group_select(self, "content_equipment", key=lambda x: x.cat())
        group_select(self, "weapon_profiles_field", key=lambda x: x.equipment.name)


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
        "weapon_accessories_field",
        "linked_fighter",
        "upgrades_field",
        cost,
    ]
    readonly_fields = ["linked_fighter", cost]
    list_display = [
        "list_fighter",
        "list_fighter__list__name",
        "content_equipment",
        weapon_profiles_list,
        weapon_accessories_list,
        "linked_fighter",
    ]
    search_fields = [
        "list_fighter__name",
        "content_equipment__name",
        "weapon_profiles_field__name",
        "weapon_accessories_field__name",
        "linked_fighter__name",
    ]
