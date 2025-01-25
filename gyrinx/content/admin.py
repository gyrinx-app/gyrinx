from itertools import groupby

from django import forms
from django.contrib import admin, messages
from django.db import models, transaction
from django.db.models import Case, When
from django.db.models.functions import Cast
from django.shortcuts import render
from django.utils.translation import gettext as _

from gyrinx.content.forms import CopySelectedToFighterForm

from .models import (
    ContentBook,
    ContentEquipment,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentHouse,
    ContentPageRef,
    ContentPolicy,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    ContentWeaponTrait,
)


@admin.action(description="Copy to another Fighter")
def copy_selected_to(self, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        try:
            for fighter_id in request.POST.getlist("to_fighters"):
                for item in queryset:
                    item.pk = None
                    item.fighter_id = fighter_id
                    item.save()
        except Exception as e:
            self.message_user(
                request,
                _("An error occurred while copying: %s") % str(e),
                messages.ERROR,
            )
            return None

        self.message_user(
            request,
            _("The selected items have been copied."),
            messages.SUCCESS,
        )
        return None

    form = CopySelectedToFighterForm(initial={"_selected_action": selected})
    title = _("Copy items to another ContentFighter?")
    subtitle = _(
        "Select one or more ContentFighters to which you want to copy the selected items."
    )

    context = {
        **self.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "form": form,
    }
    request.current_app = self.admin_site.name
    return render(
        request,
        "content/copy_selected_to.html",
        context,
    )


def group_equipment(form, field="equipment"):
    grouped_equipment = groupby(
        ContentEquipment.objects.order_by("category", "name"),
        key=lambda equipment: equipment.cat(),
    )

    choices = [
        (category_name, [(equipment.id, str(equipment)) for equipment in items])
        for category_name, items in grouped_equipment
    ]

    form.fields[field].choices = [
        ("", "---------"),
    ] + choices


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


class ContentWeaponAccessoryInline(ContentTabularInline):
    model = ContentWeaponAccessory


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "category", "contentweaponprofile__name"]

    inlines = [ContentWeaponProfileInline]

    actions = ["clone"]

    @admin.action(description="Clone selected Equipment")
    def clone(self, request, queryset):
        try:
            for item in queryset:
                with transaction.atomic():
                    profiles = ContentWeaponProfile.objects.filter(equipment=item)
                    item.pk = None
                    item.name = f"{item.name} (Clone)"
                    item.save()
                    for profile in profiles:
                        profile.pk = None
                        profile.equipment = item
                        profile.save()

        except Exception as e:
            self.message_user(
                request,
                _("An error occurred while cloning the Equipment: %s") % str(e),
                messages.ERROR,
            )
            return None

        self.message_user(
            request,
            _("The selected Equipment has been cloned."),
            messages.SUCCESS,
        )
        return None


class ContentFighterEquipmentListItemAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        group_equipment(self)

        if self.instance.equipment_id:
            self.fields[
                "weapon_profile"
            ].queryset = ContentWeaponProfile.objects.filter(
                equipment=self.instance.equipment,
            )

        self.fields["weapon_profile"].queryset = self.fields[
            "weapon_profile"
        ].queryset.filter(
            cost__gt=0,
        )


@admin.register(ContentFighterEquipmentListItem)
class ContentFighterEquipmentListItemAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profile__name"]
    form = ContentFighterEquipmentListItemAdminForm

    actions = [copy_selected_to]


@admin.register(ContentFighterEquipmentListWeaponAccessory)
class ContentFighterEquipmentListWeaponAccessoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "weapon_accessory__name"]

    actions = [copy_selected_to]


class ContentFighterDefaultAssignmentAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_equipment(self)
        if self.instance.equipment_id:
            self.fields[
                "weapon_profiles_field"
            ].queryset = ContentWeaponProfile.objects.filter(
                equipment=self.instance.equipment
            )

        self.fields["weapon_profiles_field"].queryset = self.fields[
            "weapon_profiles_field"
        ].queryset.filter(
            cost__gt=0,
        )


@admin.register(ContentFighterDefaultAssignment)
class ContentFighterDefaultAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profiles_field__name"]
    form = ContentFighterDefaultAssignmentAdminForm


class ContentFighterEquipmentInline(ContentTabularInline):
    form = ContentFighterEquipmentListItemAdminForm
    model = ContentFighterEquipmentListItem


class ContentFighterDefaultAssignmentInline(ContentTabularInline):
    form = ContentFighterDefaultAssignmentAdminForm
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
    search_fields = ["name", "category__name"]
    list_display_links = ["name"]


class ContentSkillInline(ContentTabularInline):
    model = ContentSkill


@admin.register(ContentSkillCategory)
class ContentSkillCategoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
    list_display_links = ["name"]
    list_display_fields = ["name", "restricted"]

    inlines = [ContentSkillInline]


@admin.register(ContentWeaponTrait)
class ContentWeaponTraitAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


class ContentWeaponProfileAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_equipment(self, "equipment")


@admin.register(ContentWeaponProfile)
class ContentWeaponProfileAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentWeaponProfileAdminForm
    search_fields = ["name"]
    list_display_links = ["equipment", "name"]


@admin.register(ContentWeaponAccessory)
class ContentWeaponAccessoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


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
