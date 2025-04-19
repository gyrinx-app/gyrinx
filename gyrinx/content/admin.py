from django import forms
from django.contrib import admin, messages
from django.db import models, transaction
from django.db.models import Case, When
from django.db.models.functions import Cast
from django.utils.translation import gettext as _
from polymorphic.admin import (
    PolymorphicChildModelAdmin,
    PolymorphicChildModelFilter,
    PolymorphicParentModelAdmin,
    StackedPolymorphicInline,
)

from gyrinx.content.actions import copy_selected_to_fighter, copy_selected_to_house
from gyrinx.forms import group_select
from gyrinx.models import equipment_category_choices

from .models import (
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterHouseOverride,
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentHouseAdditionalRule,
    ContentHouseAdditionalRuleTree,
    ContentMod,
    ContentModFighterRule,
    ContentModFighterStat,
    ContentModStat,
    ContentModTrait,
    ContentPageRef,
    ContentPolicy,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
    ContentWeaponAccessory,
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


class ContentStackedPolymorphicInline(
    StackedPolymorphicInline, ContentStackedInline
): ...


@admin.register(ContentEquipmentCategory)
class ContentEquipmentCategoryAdmin(ContentAdmin):
    search_fields = ["name", "group"]
    list_display_links = ["name"]
    list_display_fields = ["name"]
    list_filter = ["group"]


class ContentWeaponProfileInline(ContentStackedInline):
    model = ContentWeaponProfile
    extra = 0


class ContentWeaponAccessoryInline(ContentTabularInline):
    model = ContentWeaponAccessory
    extra = 0


class ContentEquipmentFighterProfileInline(ContentTabularInline):
    model = ContentEquipmentFighterProfile
    extra = 0


class ContentEquipmentUpgradeInline(ContentTabularInline):
    model = ContentEquipmentUpgrade
    extra = 0


class ContentEquipmentAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = self.fields["category"].queryset.order_by(
            Case(
                *[
                    When(
                        group=group,
                        then=i,
                    )
                    for i, group in enumerate(equipment_category_choices.keys())
                ],
                default=99,
            ),
            "name",
        )
        # Filter the queryset for modifiers to only include those that change things
        # on the fighter.
        mod_qs = self.fields["modifiers"].queryset
        self.fields["modifiers"].queryset = mod_qs.instance_of(
            ContentModFighterStat,
        ) | mod_qs.instance_of(
            ContentModFighterRule,
        )

        group_select(self, "category", key=lambda x: x.group)


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentEquipmentAdminForm

    search_fields = ["name", "category__name", "contentweaponprofile__name"]
    list_filter = ["category"]

    inlines = [
        ContentWeaponProfileInline,
        ContentEquipmentFighterProfileInline,
        ContentEquipmentUpgradeInline,
    ]

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

        group_select(self, "fighter", key=lambda x: x.house.name)
        group_select(self, "equipment", key=lambda x: x.cat())
        group_select(self, "weapon_profile", key=lambda x: x.equipment.name)


@admin.register(ContentFighterEquipmentListItem)
class ContentFighterEquipmentListItemAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profile__name"]
    form = ContentFighterEquipmentListItemAdminForm

    actions = [copy_selected_to_fighter]


class ContentFighterEquipmentListWeaponAccessoryAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        group_select(self, "fighter", key=lambda x: x.house.name)


@admin.register(ContentFighterEquipmentListWeaponAccessory)
class ContentFighterEquipmentListWeaponAccessoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "weapon_accessory__name"]
    form = ContentFighterEquipmentListWeaponAccessoryAdminForm

    actions = [copy_selected_to_fighter]


class ContentFighterDefaultAssignmentAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

        group_select(self, "fighter", key=lambda x: x.house.name)
        group_select(self, "equipment", key=lambda x: x.cat())
        group_select(self, "weapon_profiles_field", key=lambda x: x.equipment.name)


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


class ContentFighterHouseOverrideInline(ContentTabularInline):
    model = ContentFighterHouseOverride


class ContentFighterPsykerDisciplineAssignmentInline(ContentTabularInline):
    model = ContentFighterPsykerDisciplineAssignment
    extra = 0


class ContentFighterPsykerPowerDefaultAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "psyker_power", key=lambda x: x.discipline.name)


class ContentFighterPsykerPowerDefaultAssignmentInline(ContentTabularInline):
    model = ContentFighterPsykerPowerDefaultAssignment
    extra = 0
    form = ContentFighterPsykerPowerDefaultAssignmentForm


class ContentFighterForm(forms.ModelForm):
    pass


@admin.register(ContentFighter)
class ContentFighterAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentFighterForm
    search_fields = ["type", "category", "house__name"]
    list_filter = ["category", "house", "psyker_disciplines__discipline"]
    inlines = [
        ContentFighterHouseOverrideInline,
        ContentFighterEquipmentInline,
        ContentFighterDefaultAssignmentInline,
        ContentFighterPsykerDisciplineAssignmentInline,
        ContentFighterPsykerPowerDefaultAssignmentInline,
    ]
    actions = [copy_selected_to_house]


@admin.register(ContentFighterHouseOverride)
class ContentFighterHouseOverrideAdmin(ContentAdmin):
    search_fields = ["fighter__type", "house__name"]
    list_filter = ["fighter__type", "house"]


@admin.register(ContentPolicy)
class ContentPolicyAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentSkill)
class ContentSkillAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "category__name"]
    list_display_links = ["name"]
    list_filter = ["category"]


class ContentSkillInline(ContentTabularInline):
    model = ContentSkill


@admin.register(ContentSkillCategory)
class ContentSkillCategoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
    list_display_links = ["name"]
    list_display_fields = ["name", "restricted"]

    inlines = [ContentSkillInline]


@admin.register(ContentHouseAdditionalRule)
class ContentHouseAdditionalRuleAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["tree__name", "name"]


class ContentHouseAdditionalRuleInline(ContentTabularInline):
    model = ContentHouseAdditionalRule
    extra = 0


@admin.register(ContentHouseAdditionalRuleTree)
class ContentHouseAdditionalRuleTreeAdmin(ContentAdmin, admin.ModelAdmin):
    list_display_links = ["name"]
    list_display_fields = ["house", "name"]
    search_fields = ["house__name", "name"]
    inlines = [ContentHouseAdditionalRuleInline]


def rules(obj):
    return ", ".join([rule.name for rule in obj.rules.all()])


class ContentHouseAdditionalRuleTreeInline(ContentTabularInline):
    model = ContentHouseAdditionalRuleTree
    extra = 0
    fields = ["name", rules]
    readonly_fields = [rules]


class ContentPsykerPowerInline(ContentTabularInline):
    model = ContentPsykerPower
    extra = 0


@admin.register(ContentPsykerDiscipline)
class ContentPsykerDisciplineAdmin(ContentAdmin):
    search_fields = ["name"]
    list_filter = ["generic"]

    inlines = [ContentPsykerPowerInline]


class ContentFighterPsykerPowerDefaultAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "fighter", key=lambda x: x.house.name)
        group_select(self, "psyker_power", key=lambda x: x.discipline.name)


@admin.register(ContentFighterPsykerPowerDefaultAssignment)
class ContentFighterPsykerPowerDefaultAssignmentAdmin(ContentAdmin):
    search_fields = ["fighter__type", "psyker_power__name"]
    list_filter = ["fighter__type", "psyker_power__discipline"]
    form = ContentFighterPsykerPowerDefaultAssignmentForm


class ContentFighterInline(ContentTabularInline):
    model = ContentFighter


@admin.register(ContentHouse)
class ContentHouseAdmin(ContentAdmin, admin.ModelAdmin):
    list_display_links = ["name"]
    search_fields = ["name"]
    inlines = [ContentFighterInline, ContentHouseAdditionalRuleTreeInline]


@admin.register(ContentWeaponTrait)
class ContentWeaponTraitAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


class ContentEquipmentFighterProfileAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "equipment", key=lambda x: x.cat())
        group_select(self, "content_fighter", key=lambda x: x.house.name)


@admin.register(ContentEquipmentFighterProfile)
class ContentEquipmentFighterProfileAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentEquipmentFighterProfileAdminForm
    search_fields = ["equipment__name", "content_fighter__type"]


class ContentWeaponProfileAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "equipment", key=lambda x: x.cat())


@admin.register(ContentWeaponProfile)
class ContentWeaponProfileAdmin(ContentAdmin):
    form = ContentWeaponProfileAdminForm
    search_fields = ["name"]
    list_display_links = ["equipment", "name"]


def mods(obj):
    return ", ".join([mod.name for mod in obj.modifiers.all()])


@admin.register(ContentWeaponAccessory)
class ContentWeaponAccessoryAdmin(ContentAdmin):
    search_fields = ["name"]


class ContentModChildAdmin(PolymorphicChildModelAdmin):
    """Base admin class for all child models"""

    base_model = ContentMod


@admin.register(ContentModStat)
class ContentModStatAdmin(ContentModChildAdmin):
    base_model = ContentModStat


@admin.register(ContentModFighterStat)
class ContentModFighterStatAdmin(ContentModChildAdmin):
    base_model = ContentModFighterStat


@admin.register(ContentModTrait)
class ContentModTraitAdmin(ContentModChildAdmin):
    base_model = ContentModTrait


@admin.register(ContentModFighterRule)
class ContentModFighterRuleAdmin(ContentModChildAdmin):
    base_model = ContentModFighterRule


@admin.register(ContentMod)
class ContentModAdmin(PolymorphicParentModelAdmin, ContentAdmin):
    base_model = ContentMod
    child_models = (
        ContentModStat,
        ContentModFighterStat,
        ContentModTrait,
        ContentModFighterRule,
    )
    list_filter = (PolymorphicChildModelFilter,)


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
