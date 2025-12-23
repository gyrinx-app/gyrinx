import logging

from django import forms
from django.contrib import admin, messages
from django.db.models import Exists, OuterRef

from gyrinx.content.models import ContentWeaponProfile
from gyrinx.core.admin.base import BaseAdmin
from gyrinx.core.models.action import ListAction
from gyrinx.forms import group_select
from gyrinx.tracker import track

from ..models.list import (
    List,
    ListAttributeAssignment,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterPsykerPowerAssignment,
)

logger = logging.getLogger(__name__)


@admin.display(description="Cost")
def cost(obj):
    return obj.cost_display()


class ListFighterInline(admin.TabularInline):
    model = ListFighter
    extra = 1
    fields = ["name", "owner", "content_fighter", "cost_override"]
    show_change_link = True


class ListAttributeAssignmentInline(admin.TabularInline):
    model = ListAttributeAssignment
    extra = 1
    fields = ["attribute_value", "archived"]
    show_change_link = True


class ListForm(forms.ModelForm):
    pass


class HasActionTrackingFilter(admin.SimpleListFilter):
    """Filter lists by whether they have action tracking (initial ListAction)."""

    title = "action tracking"
    parameter_name = "has_action_tracking"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Has action tracking"),
            ("no", "Missing action tracking"),
        ]

    def queryset(self, request, queryset):
        # Subquery to check if list has any actions
        has_action = Exists(ListAction.objects.filter(list=OuterRef("pk")))

        if self.value() == "yes":
            return queryset.filter(has_action)
        if self.value() == "no":
            return queryset.filter(~has_action)
        return queryset


@admin.action(description="Initialize action tracking (enqueue background tasks)")
def initialize_action_tracking(modeladmin, request, queryset):
    """
    Enqueue background tasks to backfill initial ListAction for selected lists.

    This action filters to only lists without existing actions and enqueues
    a background task for each one. The task will:
    1. Recalculate cached values via facts_from_db()
    2. Create an initial CREATE action as a snapshot
    """
    from gyrinx.core.tasks import backfill_list_action

    # Filter to only lists without actions (idempotent, but avoids unnecessary tasks)
    list_ids_with_actions = set(
        ListAction.objects.filter(list__in=queryset).values_list("list_id", flat=True)
    )

    # Only fetch IDs to minimize memory usage for large querysets
    lists_to_process = [
        lst_id
        for lst_id in queryset.values_list("id", flat=True)
        if lst_id not in list_ids_with_actions
    ]
    skipped_count = queryset.count() - len(lists_to_process)

    if not lists_to_process:
        modeladmin.message_user(
            request,
            "All selected lists already have action tracking.",
            messages.WARNING,
        )
        return

    # Enqueue tasks
    enqueued_count = 0
    failed_count = 0

    track(
        "admin_initialize_action_tracking_started",
        total_selected=queryset.count(),
        to_process=len(lists_to_process),
        skipped=skipped_count,
        user=request.user.username,
    )

    for lst_id in lists_to_process:
        try:
            backfill_list_action.enqueue(list_id=str(lst_id))
            enqueued_count += 1
        except Exception as e:
            logger.error(f"Failed to enqueue backfill task for list {lst_id}: {e}")
            track(
                "admin_initialize_action_tracking_enqueue_failed",
                list_id=str(lst_id),
                error=str(e),
            )
            failed_count += 1

    track(
        "admin_initialize_action_tracking_completed",
        enqueued=enqueued_count,
        failed=failed_count,
        skipped=skipped_count,
        user=request.user.username,
    )

    # Build message
    msg_parts = [f"Enqueued {enqueued_count} backfill task(s)."]
    if skipped_count:
        msg_parts.append(f"Skipped {skipped_count} (already have actions).")
    if failed_count:
        msg_parts.append(f"Failed to enqueue {failed_count} (check logs).")

    # Determine message level based on outcome
    if enqueued_count == 0 and len(lists_to_process) > 0:
        # All enqueues failed - likely a task backend configuration issue
        level = messages.ERROR
        msg_parts.append("Check task queue configuration.")
    elif failed_count > 0:
        level = messages.WARNING
    else:
        level = messages.SUCCESS
    modeladmin.message_user(request, " ".join(msg_parts), level)


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
    list_filter = ["status", "public", "content_house", HasActionTrackingFilter]
    search_fields = ["name", "content_house__name", "campaign__name"]
    actions = [initialize_action_tracking]

    inlines = [ListFighterInline, ListAttributeAssignmentInline]


class ListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.instance, "list"):
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
