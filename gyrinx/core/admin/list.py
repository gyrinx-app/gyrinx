from django import forms
from django.contrib import admin, messages
from django.db import transaction

from gyrinx.content.models import ContentWeaponProfile
from gyrinx.core.admin.base import BaseAdmin
from gyrinx.forms import group_select

from ..models.list import (
    List,
    ListAttributeAssignment,
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
    fields = ["name", "owner", "content_fighter", "cost_override"]
    # Without autocomplete, every inline row renders a <select> of all users and
    # all content fighters — and each ContentFighter option label fetches its
    # house, so a single List change page runs thousands of queries.
    autocomplete_fields = ["owner", "content_fighter"]
    show_change_link = True


class ListAttributeAssignmentInline(admin.TabularInline):
    model = ListAttributeAssignment
    extra = 1
    fields = ["attribute_value", "archived"]
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
        "narrative",
        "rating_current",
        "stash_current",
        "credits_current",
    ]
    readonly_fields = ["original_list", "campaign"]
    list_display = ["name", "content_house", "owner", "status", "public"]
    list_filter = ["status", "public", "content_house"]
    search_fields = [
        "name",
        "content_house__name",
        "campaign__name",
        "owner__username",
        "owner__email",
    ]
    autocomplete_fields = ["owner"]

    inlines = [ListFighterInline, ListAttributeAssignmentInline]


class ListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # group_select below iterates every option and renders its label;
        # ContentFighter.__str__ touches house and ContentSkill groups by
        # category, so without select_related each option costs a query.
        for field, related in [
            ("content_fighter", "house"),
            ("legacy_content_fighter", "house"),
            ("skills", "category"),
        ]:
            if field in self.fields:
                self.fields[field].queryset = self.fields[
                    field
                ].queryset.select_related(related)

        if hasattr(self.instance, "list"):
            if "disabled_default_assignments" in self.fields:
                self.fields["disabled_default_assignments"].queryset = self.fields[
                    "disabled_default_assignments"
                ].queryset.filter(fighter=self.instance.content_fighter)

            if "disabled_pskyer_default_powers" in self.fields:
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
    # Avoid rendering a <select> of the entire equipment catalogue per row.
    autocomplete_fields = ["content_equipment"]
    show_change_link = True
    fk_name = "list_fighter"


class ListFighterPsykerPowerAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["psyker_power"].queryset = self.fields[
            "psyker_power"
        ].queryset.select_related("discipline")
        group_select(self, "psyker_power", key=lambda x: x.discipline.name)


class ListFighterPsykerPowerAssignmentInline(admin.TabularInline):
    model = ListFighterPsykerPowerAssignment
    form = ListFighterPsykerPowerAssignmentForm
    extra = 1
    fields = ["psyker_power"]


@admin.action(description="Recompute cached cost/rating from facts (fix drift)")
def recompute_cost_caches(modeladmin, request, queryset):
    """
    Force-recompute the cached cost/rating chain for the selected fighters
    straight from the source-of-truth assignments.

    Fixes cached-value drift (e.g. an inflated stash after a fighter death,
    where a fighter's ``rating_current`` is wrong but ``dirty=False`` so the
    normal lazy "Refresh Cost" recompute trusts the stale value and never
    re-derives it). This rebuilds the whole subtree explicitly:
    assignments -> fighter -> list, ignoring the dirty flags.
    """
    changed = []
    affected_lists = {}
    fighter_count = 0

    with transaction.atomic():
        for fighter in queryset.select_related("list", "content_fighter"):
            fighter_count += 1
            before = fighter.rating_current

            # Rebuild each real assignment's cache from cost_int(). Use
            # with_related_data() to prefetch the equipment/profiles/accessories/
            # upgrades that cost_int() touches and avoid N+1 across fighters.
            assignments = (
                ListFighterEquipmentAssignment.objects.with_related_data().filter(
                    list_fighter=fighter
                )
            )
            for assignment in assignments:
                assignment.facts_from_db(update=True)

            # ...then the fighter's own cache from the (now-correct) assignments.
            after = fighter.facts_from_db(update=True).rating

            affected_lists[fighter.list_id] = fighter.list
            if before != after:
                changed.append((fighter, before, after))

        # Reconcile each affected list's aggregate caches (rating/stash).
        for lst in affected_lists.values():
            lst.facts_from_db(update=True)

    for fighter, before, after in changed:
        messages.success(
            request,
            f"{fighter.name}: rating_current {before} → {after}",
        )

    messages.info(
        request,
        f"Recomputed {fighter_count} fighter(s) across "
        f"{len(affected_lists)} list(s); {len(changed)} had drift corrected.",
    )


@admin.register(ListFighter)
class ListFighterAdmin(BaseAdmin):
    form = ListFighterForm
    actions = [recompute_cost_caches]
    fields = [
        "name",
        "content_fighter",
        "legacy_content_fighter",
        "owner",
        "list",
        "skills",
        "cost_override",
        cost,
        "narrative",
        "disabled_default_assignments",
        "disabled_pskyer_default_powers",
    ]
    readonly_fields = [cost]
    list_display = ["name", "content_fighter", "list"]
    # "=id" allows pasting a fighter UUID into the search box for an exact match.
    search_fields = ["=id", "name", "content_fighter__type", "list__name"]
    autocomplete_fields = ["list", "owner"]

    inlines = [
        ListFighterEquipmentAssignmentInline,
        ListFighterPsykerPowerAssignmentInline,
    ]


class ListFighterEquipmentAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The group_select keys below reach through FKs (fighter's list,
        # equipment's category, profile's equipment) — select_related keeps
        # each grouped dropdown to a single query.
        for field, related in [
            ("list_fighter", "list"),
            ("content_equipment", "category"),
            ("weapon_profiles_field", "equipment"),
        ]:
            if field in self.fields:
                self.fields[field].queryset = self.fields[
                    field
                ].queryset.select_related(related)

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
        "child_fighter",
        "upgrades_field",
        cost,
    ]
    readonly_fields = ["child_fighter", cost]
    list_display = [
        "list_fighter",
        "list_fighter__list__name",
        "content_equipment",
        weapon_profiles_list,
        weapon_accessories_list,
        "child_fighter",
    ]
    search_fields = [
        "list_fighter__name",
        "content_equipment__name",
        "weapon_profiles_field__name",
        "weapon_accessories_field__name",
        "child_fighter__name",
    ]
