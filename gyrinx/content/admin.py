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
    ContentAttribute,
    ContentAttributeValue,
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRule,
    ContentEquipmentListExpansionRuleByAttribute,
    ContentEquipmentListExpansionRuleByFighterCategory,
    ContentEquipmentListExpansionRuleByHouse,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentCategoryLimit,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterHouseOverride,
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentInjury,
    ContentInjuryGroup,
    ContentMod,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModPsykerDisciplineAccess,
    ContentModSkillTreeAccess,
    ContentModStat,
    ContentModTrait,
    ContentPageRef,
    ContentPolicy,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
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


class ContentEquipmentCategoryFighterRestrictionInline(ContentTabularInline):
    model = ContentEquipmentCategoryFighterRestriction
    extra = 0
    verbose_name = "Fighter Category Restriction"
    verbose_name_plural = "Fighter Category Restrictions"


class ContentFighterEquipmentCategoryLimitForm(forms.ModelForm):
    def init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )

    class Meta:
        model = ContentFighterEquipmentCategoryLimit
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        equipment_category = cleaned_data.get("equipment_category")

        # Check if we have an equipment_category and this is an inline form
        if equipment_category and hasattr(self, "parent_instance"):
            # The parent_instance is the ContentEquipmentCategory being edited
            equipment_category = self.parent_instance

            # Check if this category has fighter restrictions
            if not ContentEquipmentCategoryFighterRestriction.objects.filter(
                equipment_category=equipment_category
            ).exists():
                raise forms.ValidationError(
                    "Fighter equipment category limits can only be set for categories that have fighter restrictions."
                )

        return cleaned_data


class ContentFighterEquipmentCategoryLimitInline(ContentTabularInline):
    model = ContentFighterEquipmentCategoryLimit
    form = ContentFighterEquipmentCategoryLimitForm
    extra = 0
    verbose_name = "Fighter Equipment Category Limit"
    verbose_name_plural = "Fighter Equipment Category Limits"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            # Pass the parent instance to the form class
            original_form = formset.form

            class FormWithParentInstance(original_form):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.parent_instance = obj
                    group_select(
                        self,
                        "fighter",
                        key=lambda x: x.house.name if x.house else "No House",
                    )

            formset.form = FormWithParentInstance
        return formset


@admin.register(ContentEquipmentCategory)
class ContentEquipmentCategoryAdmin(ContentAdmin):
    search_fields = ["name", "group"]
    list_display_links = ["name"]
    list_display_fields = ["name"]
    list_filter = ["group", "restricted_to", "visible_only_if_in_equipment_list"]
    inlines = [
        ContentEquipmentCategoryFighterRestrictionInline,
        ContentFighterEquipmentCategoryLimitInline,
    ]


class ContentWeaponProfileInline(ContentStackedInline):
    model = ContentWeaponProfile
    extra = 0


class ContentWeaponAccessoryInline(ContentTabularInline):
    model = ContentWeaponAccessory
    extra = 0


class ContentEquipmentFighterProfileInline(ContentTabularInline):
    model = ContentEquipmentFighterProfile
    extra = 0


class ContentEquipmentEquipmentProfileInline(ContentTabularInline):
    model = ContentEquipmentEquipmentProfile
    extra = 0
    fk_name = "equipment"


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
        self.fields["modifiers"].queryset = (
            mod_qs.instance_of(
                ContentModFighterStat,
            )
            | mod_qs.instance_of(
                ContentModFighterRule,
            )
            | mod_qs.instance_of(
                ContentModFighterSkill,
            )
            | mod_qs.instance_of(
                ContentModSkillTreeAccess,
            )
            | mod_qs.instance_of(
                ContentModPsykerDisciplineAccess,
            )
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
        ContentEquipmentEquipmentProfileInline,
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

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )
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

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )


@admin.register(ContentFighterEquipmentListWeaponAccessory)
class ContentFighterEquipmentListWeaponAccessoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "weapon_accessory__name"]
    form = ContentFighterEquipmentListWeaponAccessoryAdminForm

    actions = [copy_selected_to_fighter]


class ContentFighterEquipmentListUpgradeAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )
        group_select(self, "upgrade", key=lambda x: x.equipment.name)


@admin.register(ContentFighterEquipmentListUpgrade)
class ContentFighterEquipmentListUpgradeAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "upgrade__name", "upgrade__equipment__name"]
    list_filter = ["upgrade__equipment__upgrade_mode"]
    form = ContentFighterEquipmentListUpgradeAdminForm

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "fighter":
            kwargs["queryset"] = ContentFighter.objects.select_related("house")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )
        group_select(self, "equipment", key=lambda x: x.cat())
        group_select(self, "weapon_profiles_field", key=lambda x: x.equipment.name)


@admin.register(ContentFighterDefaultAssignment)
class ContentFighterDefaultAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profiles_field__name"]
    form = ContentFighterDefaultAssignmentAdminForm
    actions = [copy_selected_to_fighter]


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


class ContentFighterEquipmentCategoryLimitForFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show equipment categories that have fighter restrictions
        self.fields["equipment_category"].queryset = (
            ContentEquipmentCategory.objects.filter(fighter_restrictions__isnull=False)
            .distinct()
            .order_by("group", "name")
        )

        group_select(self, "equipment_category", key=lambda x: x.group)

    class Meta:
        model = ContentFighterEquipmentCategoryLimit
        fields = ["equipment_category", "limit"]


class ContentFighterEquipmentCategoryLimitForFighterInline(ContentTabularInline):
    model = ContentFighterEquipmentCategoryLimit
    form = ContentFighterEquipmentCategoryLimitForFighterForm
    extra = 0
    verbose_name = "Equipment Category Limit"
    verbose_name_plural = "Equipment Category Limits"


class ContentFighterForm(forms.ModelForm):
    pass


class ContentStatlineInline(ContentStackedInline):
    model = ContentStatline
    extra = 0
    max_num = 1
    verbose_name = "Fighter Statline"
    verbose_name_plural = "Fighter Statline"
    fields = ["statline_type"]
    can_delete = True

    def has_add_permission(self, request, obj=None):
        # Allow adding a statline if the fighter doesn't have one
        if obj and hasattr(obj, "custom_statline"):
            return False
        return super().has_add_permission(request, obj)


@admin.register(ContentFighter)
class ContentFighterAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentFighterForm
    search_fields = ["type", "category", "house__name"]
    list_filter = ["category", "house", "psyker_disciplines__discipline"]
    inlines = [
        ContentStatlineInline,
        # ContentFighterHouseOverrideInline,
        # ContentFighterEquipmentInline,
        # ContentFighterDefaultAssignmentInline,
        ContentFighterEquipmentCategoryLimitForFighterInline,
        ContentFighterPsykerDisciplineAssignmentInline,
        ContentFighterPsykerPowerDefaultAssignmentInline,
    ]
    actions = [copy_selected_to_house]


@admin.register(ContentFighterPsykerDisciplineAssignment)
class ContentFighterPsykerDisciplineAssignmentAdmin(ContentAdmin):
    search_fields = ["fighter__type", "discipline__name"]
    list_filter = ["fighter__type", "discipline__name"]


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
        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )
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
    inlines = [ContentFighterInline]


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


class ContentEquipmentEquipmentProfileAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "equipment", key=lambda x: x.cat())
        group_select(self, "linked_equipment", key=lambda x: x.cat())


@admin.register(ContentEquipmentEquipmentProfile)
class ContentEquipmentEquipmentProfileAdmin(ContentAdmin):
    form = ContentEquipmentEquipmentProfileAdminForm
    search_fields = ["equipment__name", "linked_equipment__name"]


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


class ContentModFighterSkillAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "skill", key=lambda x: x.category.name)


@admin.register(ContentModFighterSkill)
class ContentModFighterSkillAdmin(ContentModChildAdmin):
    base_model = ContentModFighterSkill
    form = ContentModFighterSkillAdminForm


@admin.register(ContentModSkillTreeAccess)
class ContentModSkillTreeAccessAdmin(ContentModChildAdmin):
    base_model = ContentModSkillTreeAccess


@admin.register(ContentModPsykerDisciplineAccess)
class ContentModPsykerDisciplineAccessAdmin(ContentModChildAdmin):
    base_model = ContentModPsykerDisciplineAccess


@admin.register(ContentMod)
class ContentModAdmin(PolymorphicParentModelAdmin, ContentAdmin):
    base_model = ContentMod
    child_models = (
        ContentModStat,
        ContentModFighterStat,
        ContentModTrait,
        ContentModFighterRule,
        ContentModFighterSkill,
        ContentModSkillTreeAccess,
        ContentModPsykerDisciplineAccess,
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


class ContentModInline(ContentTabularInline):
    model = ContentInjury.modifiers.through
    extra = 0
    verbose_name = "Modifier"
    verbose_name_plural = "Modifiers"


class ContentInjuryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "phase" in self.fields:
            self.fields["phase"].label = "Default Outcome"

    class Meta:
        model = ContentInjury
        fields = "__all__"


class ContentInjuryInline(ContentTabularInline):
    model = ContentInjury
    extra = 0
    fields = ["name", "description", "phase", "modifiers"]


@admin.register(ContentInjuryGroup)
class ContentInjuryGroupAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "description",
        "restricted_to_houses",
        "restricted_to_fighters",
        "unavailable_to_fighters",
    ]

    inlines = [ContentInjuryInline]

    @admin.display(description="Restricted to Houses")
    def restricted_to_houses(self, obj):
        if obj.restricted_to_house.exists():
            return ", ".join([house.name for house in obj.restricted_to_house.all()])
        return "-"

    @admin.display(description="Restricted to Fighters")
    def restricted_to_fighters(self, obj):
        return obj.get_restricted_to_display()

    @admin.display(description="Unavailable to Fighters")
    def unavailable_to_fighters(self, obj):
        return obj.get_unavailable_to_display()


@admin.register(ContentInjury)
class ContentInjuryAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentInjuryForm
    search_fields = ["name", "description"]
    list_filter = ["phase"]
    list_display = ["name", "description", "phase", "get_modifier_count"]
    readonly_fields = ["id", "created", "modified"]

    inlines = [ContentModInline]

    def get_modifier_count(self, obj):
        return obj.modifiers.count()

    get_modifier_count.short_description = "Modifiers"


class ContentAttributeValueInline(ContentTabularInline):
    model = ContentAttributeValue
    extra = 0
    fields = ["name", "description"]


@admin.register(ContentAttribute)
class ContentAttributeAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
    list_display = ["name", "is_single_select", "get_value_count"]
    list_filter = ["is_single_select"]
    list_display_links = ["name"]
    filter_horizontal = ["restricted_to"]

    inlines = [ContentAttributeValueInline]

    def get_value_count(self, obj):
        return obj.values.count()

    get_value_count.short_description = "Values"


@admin.register(ContentAttributeValue)
class ContentAttributeValueAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "attribute__name", "description"]
    list_display = ["name", "attribute", "description"]
    list_filter = ["attribute"]
    list_display_links = ["name"]


class ContentStatlineTypeStatInline(ContentTabularInline):
    model = ContentStatlineTypeStat
    extra = 0
    fields = [
        "stat",
        "position",
        "is_highlighted",
        "is_first_of_group",
    ]
    readonly_fields = []
    ordering = ["position"]


@admin.register(ContentStat)
class ContentStatAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["field_name", "short_name", "full_name"]
    list_display = ["field_name", "short_name", "full_name"]
    list_display_links = ["field_name"]
    readonly_fields = ["field_name"]  # Auto-generated from full_name


@admin.register(ContentStatlineType)
class ContentStatlineTypeAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
    list_display = ["name", "get_stat_count"]
    list_display_links = ["name"]

    inlines = [ContentStatlineTypeStatInline]

    def get_stat_count(self, obj):
        return obj.stats.count()

    get_stat_count.short_description = "Stats"


class ContentStatlineStatInline(ContentTabularInline):
    model = ContentStatlineStat
    extra = 0
    fields = ["statline_type_stat", "value"]
    readonly_fields = []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "statline_type_stat":
            # Get the parent statline object if it exists
            if request.resolver_match.kwargs.get("object_id"):
                try:
                    statline = ContentStatline.objects.get(
                        pk=request.resolver_match.kwargs["object_id"]
                    )
                    # Filter to only show stats for this statline type
                    kwargs["queryset"] = ContentStatlineTypeStat.objects.filter(
                        statline_type=statline.statline_type
                    )
                except ContentStatline.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ContentStatline)
class ContentStatlineAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["content_fighter__type", "statline_type__name"]
    list_display = ["content_fighter", "statline_type"]
    list_filter = ["statline_type"]
    list_display_links = ["content_fighter"]
    inlines = [ContentStatlineStatInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        # After saving, ensure all required stats exist
        statline = form.instance
        if statline.statline_type:
            # Get all required stats for this statline type
            required_stats = statline.statline_type.stats.all()
            existing_stats = set(
                statline.stats.values_list("statline_type_stat_id", flat=True)
            )

            # Create missing stats with empty values
            for stat in required_stats:
                if stat.id not in existing_stats:
                    ContentStatlineStat.objects.create(
                        statline=statline,
                        statline_type_stat=stat,
                        value="-",  # Default empty value
                    )


@admin.register(ContentFighterCategoryTerms)
class ContentFighterCategoryTermsAdmin(ContentAdmin):
    pass


##
## Equipment List Expansion Admin
##


class ContentEquipmentListExpansionItemInline(ContentTabularInline):
    model = ContentEquipmentListExpansionItem
    extra = 1
    autocomplete_fields = ["equipment"]
    fields = ["equipment", "cost"]
    verbose_name = "Expansion Item"
    verbose_name_plural = "Expansion Items"


@admin.register(ContentEquipmentListExpansion)
class ContentEquipmentListExpansionAdmin(ContentAdmin):
    search_fields = ["name"]
    list_display = ["name", "get_rule_count", "get_item_count"]
    filter_horizontal = ["rules"]
    inlines = [ContentEquipmentListExpansionItemInline]

    def get_rule_count(self, obj):
        return obj.rules.count()

    get_rule_count.short_description = "Rules"

    def get_item_count(self, obj):
        return obj.items.count()

    get_item_count.short_description = "Items"


# Polymorphic admin for expansion rules
class ContentEquipmentListExpansionRuleChildAdmin(PolymorphicChildModelAdmin):
    base_model = ContentEquipmentListExpansionRule


@admin.register(ContentEquipmentListExpansionRuleByAttribute)
class ContentEquipmentListExpansionRuleByAttributeAdmin(
    ContentEquipmentListExpansionRuleChildAdmin
):
    autocomplete_fields = ["attribute"]
    filter_horizontal = ["attribute_values"]
    list_display = ["__str__", "attribute"]
    search_fields = ["attribute__name"]


@admin.register(ContentEquipmentListExpansionRuleByHouse)
class ContentEquipmentListExpansionRuleByHouseAdmin(
    ContentEquipmentListExpansionRuleChildAdmin
):
    autocomplete_fields = ["house"]
    list_display = ["__str__", "house"]
    search_fields = ["house__name"]


@admin.register(ContentEquipmentListExpansionRuleByFighterCategory)
class ContentEquipmentListExpansionRuleByFighterCategoryAdmin(
    ContentEquipmentListExpansionRuleChildAdmin
):
    list_display = ["__str__", "get_categories"]

    def get_categories(self, obj):
        return ", ".join(obj.fighter_categories[:3])

    get_categories.short_description = "Categories"


@admin.register(ContentEquipmentListExpansionRule)
class ContentEquipmentListExpansionRuleParentAdmin(PolymorphicParentModelAdmin):
    base_model = ContentEquipmentListExpansionRule
    child_models = (
        ContentEquipmentListExpansionRuleByAttribute,
        ContentEquipmentListExpansionRuleByHouse,
        ContentEquipmentListExpansionRuleByFighterCategory,
    )
    list_filter = [PolymorphicChildModelFilter]
    list_display = ["__str__", "polymorphic_ctype"]
    search_fields = []
