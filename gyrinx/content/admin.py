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
from gyrinx.content.models.availability_preset import ContentAvailabilityPreset
from gyrinx.forms import group_select
from gyrinx.models import (
    SMART_QUOTES,
    FighterCategoryChoices,
    equipment_category_groups,
)

from .models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
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
    ContentCounter,
    ContentInjury,
    ContentInjuryGroup,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
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
        self.list_display.append("packs_display")
        self.initial_list_display = self.list_display.copy()
        super().__init__(model, admin_site)

    def get_queryset(self, request):
        manager = self.model._default_manager
        if hasattr(manager, "all_content"):
            qs = manager.all_content()
            ordering = self.get_ordering(request)
            if ordering:
                qs = qs.order_by(*ordering)
            return qs
        return super().get_queryset(request)

    @admin.display(description="Packs")
    def packs_display(self, obj):
        from django.contrib.contenttypes.models import ContentType

        from gyrinx.core.models.pack import CustomContentPackItem

        ct = ContentType.objects.get_for_model(obj)
        items = CustomContentPackItem.objects.filter(
            content_type=ct, object_id=obj.pk
        ).select_related("pack")
        if not items:
            return "-"
        return ", ".join(item.pack.name for item in items)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if "packs_display" not in readonly:
            readonly.append("packs_display")
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if "packs_display" not in fields:
            fields.append("packs_display")
        return fields


class ContentTabularInline(admin.TabularInline):
    show_change_link = True

    def get_queryset(self, request):
        manager = self.model._default_manager
        if hasattr(manager, "all_content"):
            qs = manager.all_content()
            ordering = self.get_ordering(request)
            if ordering:
                qs = qs.order_by(*ordering)
            return qs
        return super().get_queryset(request)


class ContentStackedInline(admin.StackedInline):
    show_change_link = True

    def get_queryset(self, request):
        manager = self.model._default_manager
        if hasattr(manager, "all_content"):
            qs = manager.all_content()
            ordering = self.get_ordering(request)
            if ordering:
                qs = qs.order_by(*ordering)
            return qs
        return super().get_queryset(request)


class ContentStackedPolymorphicInline(
    StackedPolymorphicInline, ContentStackedInline
): ...


class ContentEquipmentCategoryFighterRestrictionInline(ContentTabularInline):
    model = ContentEquipmentCategoryFighterRestriction
    extra = 0
    verbose_name = "Fighter Category Restriction"
    verbose_name_plural = "Fighter Category Restrictions"


class ContentFighterEquipmentCategoryLimitForm(forms.ModelForm):
    """
    Form for managing fighter equipment category limits.

    Validates that limits can only be set for categories with fighter restrictions.
    Groups fighters by house for better UX in the admin interface.
    """

    def init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        group_select(
            self, "fighter", key=lambda x: x.house.name if x.house else "No House"
        )

    class Meta:
        model = ContentFighterEquipmentCategoryLimit
        fields = "__all__"

    def clean(self):
        """
        Validate that equipment category limits are only set for restricted categories.

        Raises:
            ValidationError: If trying to set limits on unrestricted categories.
        """
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
        """
        Customize formset to pass parent instance to child forms.

        This allows child forms to access the parent equipment category
        for validation purposes.

        Args:
            request: The current HTTP request
            obj: The parent ContentEquipmentCategory instance
            **kwargs: Additional formset parameters

        Returns:
            Formset class with parent instance access
        """
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            # Pass the parent instance to the form class
            original_form = formset.form

            class FormWithParentInstance(original_form):
                """
                Form wrapper that provides access to parent equipment category.

                Used for validation against the parent category's restrictions.
                """

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


class ContentEquipmentFighterProfileAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "content_fighter", key=lambda x: x.house.name)

    class Meta:
        model = ContentEquipmentFighterProfile
        fields = "__all__"


class ContentEquipmentFighterProfileInline(ContentTabularInline):
    model = ContentEquipmentFighterProfile
    form = ContentEquipmentFighterProfileAdminForm
    extra = 0


class ContentEquipmentEquipmentProfileInline(ContentTabularInline):
    model = ContentEquipmentEquipmentProfile
    extra = 0
    fk_name = "equipment"


class ContentEquipmentUpgradeInline(ContentTabularInline):
    model = ContentEquipmentUpgrade
    extra = 0


class ContentEquipmentAdminForm(forms.ModelForm):
    """
    Custom form for equipment admin with enhanced filtering and grouping.

    Orders equipment categories by predefined group order and filters modifiers
    to only show those that affect fighters directly.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = self.fields["category"].queryset.order_by(
            Case(
                *[
                    When(
                        group=group,
                        then=i,
                    )
                    for i, group in enumerate(equipment_category_groups)
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
        """
        Create copies of selected equipment items with their weapon profiles.

        Each cloned item gets "(Clone)" appended to its name and all associated
        weapon profiles are also duplicated.

        Args:
            request: The current HTTP request
            queryset: QuerySet of ContentEquipment items to clone
        """
        try:
            for item in queryset:
                with transaction.atomic():
                    profiles = ContentWeaponProfile.objects.filter(equipment=item)
                    item.pk = None
                    item.name = f"{item.name} (Clone)"
                    item.save()
                    for profile in profiles:
                        # Store the original traits before clearing the pk
                        original_traits = list(profile.traits.all())
                        profile.pk = None
                        profile.equipment = item
                        profile.save()
                        # Copy the traits from the original profile
                        profile.traits.set(original_traits)

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
    """
    Form for assigning equipment items to fighters.

    Dynamically filters weapon profiles based on selected equipment and only
    shows profiles with a cost greater than zero. Groups fields for better UX.
    """

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

        group_select(self, "weapon_profile", key=lambda x: x.equipment.name)


@admin.register(ContentFighterEquipmentListItem)
class ContentFighterEquipmentListItemAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profile__name"]
    autocomplete_fields = ["fighter", "equipment"]
    form = ContentFighterEquipmentListItemAdminForm

    actions = [copy_selected_to_fighter]


@admin.register(ContentFighterEquipmentListWeaponAccessory)
class ContentFighterEquipmentListWeaponAccessoryAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "weapon_accessory__name"]
    autocomplete_fields = ["fighter", "weapon_accessory"]

    actions = [copy_selected_to_fighter]


@admin.register(ContentEquipmentUpgrade)
class ContentFighterEquipmentUpgradeAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "equipment__name"]
    autocomplete_fields = ["equipment"]


@admin.register(ContentFighterEquipmentListUpgrade)
class ContentFighterEquipmentListUpgradeAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "upgrade__name", "upgrade__equipment__name"]
    autocomplete_fields = ["fighter", "upgrade"]
    list_filter = ["upgrade__equipment__upgrade_mode"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Optimize fighter field queryset with select_related.

        Preloads house data to avoid N+1 queries when displaying fighter options.

        Args:
            db_field: The foreign key field being rendered
            request: The current HTTP request
            **kwargs: Additional field parameters

        Returns:
            Modified form field with optimized queryset
        """
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

        group_select(self, "weapon_profiles_field", key=lambda x: x.equipment.name)


@admin.register(ContentFighterDefaultAssignment)
class ContentFighterDefaultAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name", "weapon_profiles_field__name"]
    autocomplete_fields = ["fighter", "equipment"]
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
        """
        Control when new statlines can be added.

        Only allows adding a statline if the fighter doesn't already have one,
        enforcing a one-to-one relationship.

        Args:
            request: The current HTTP request
            obj: The parent ContentFighter instance

        Returns:
            Boolean indicating if adding is permitted
        """
        # Allow adding a statline if the fighter doesn't have one
        if obj and hasattr(obj, "custom_statline"):
            return False
        return super().has_add_permission(request, obj)


@admin.register(ContentFighter)
class ContentFighterAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentFighterForm
    search_fields = ["type", "category", "house__name"]
    list_filter = ["category", "house", "psyker_disciplines__discipline"]
    autocomplete_fields = ["house"]
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
    autocomplete_fields = ["fighter", "discipline"]
    search_fields = ["fighter__type", "discipline__name"]
    list_filter = ["fighter__type", "discipline__name"]


@admin.register(ContentFighterHouseOverride)
class ContentFighterHouseOverrideAdmin(ContentAdmin):
    autocomplete_fields = ["fighter", "house"]
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


class ContentAdvancementAssignmentForm(forms.ModelForm):
    class Meta:
        model = ContentAdvancementAssignment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.equipment_id:
            # Restrict upgrades to those available for the selected equipment
            self.fields[
                "upgrades_field"
            ].queryset = ContentEquipmentUpgrade.objects.filter(
                equipment=self.instance.equipment
            )


@admin.register(ContentAdvancementAssignment)
class ContentAdvancementAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentAdvancementAssignmentForm
    search_fields = ["equipment__name", "advancement__name"]
    list_display = ["equipment", "get_upgrade_count", "advancement"]
    list_filter = ["equipment__category", "advancement"]
    filter_horizontal = ["upgrades_field"]
    fieldsets = (
        (None, {"fields": ("equipment", "advancement")}),
        (
            "Upgrades",
            {
                "fields": ("upgrades_field",),
                "description": "Select the upgrades that come with this equipment assignment.",
            },
        ),
    )

    def get_upgrade_count(self, obj):
        return obj.upgrades_field.count()

    get_upgrade_count.short_description = "Upgrades"


class ContentAdvancementEquipmentAdminForm(forms.ModelForm):
    restricted_to_fighter_categories = forms.MultipleChoiceField(
        choices=FighterCategoryChoices.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select fighter categories that can take this advancement",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Group equipment by category

        # Set initial value for fighter categories from JSON field
        if self.instance and self.instance.pk:
            self.fields["restricted_to_fighter_categories"].initial = (
                self.instance.restricted_to_fighter_categories or []
            )

    def clean_restricted_to_fighter_categories(self):
        # Convert the form field back to a list for the JSON field
        return self.cleaned_data.get("restricted_to_fighter_categories", [])


class ContentAdvancementAssignmentInline(admin.TabularInline):
    model = ContentAdvancementAssignment
    form = ContentAdvancementAssignmentForm
    extra = 1
    fields = ["equipment", "upgrades_field"]
    filter_horizontal = ["upgrades_field"]
    fk_name = "advancement"
    autocomplete_fields = ["equipment"]


@admin.register(ContentAdvancementEquipment)
class ContentAdvancementEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentAdvancementEquipmentAdminForm
    search_fields = ["name"]
    list_display = [
        "name",
        "xp_cost",
        "cost_increase",
        "enable_chosen",
        "enable_random",
        "get_equipment_count",
        "get_restrictions",
    ]
    list_filter = ["enable_chosen", "enable_random", "restricted_to_houses"]
    filter_horizontal = ["restricted_to_houses"]
    inlines = [ContentAdvancementAssignmentInline]
    fieldsets = (
        (None, {"fields": ("name", "xp_cost", "cost_increase")}),
        (
            "Assignment Selection",
            {
                "fields": ("enable_chosen", "enable_random"),
                "description": "At least one selection type (chosen/random) must be enabled. Use the inline form below to add equipment assignments.",
            },
        ),
        (
            "Restrictions",
            {
                "fields": (
                    "restricted_to_houses",
                    "restricted_to_fighter_categories",
                ),
                "classes": ("collapse",),
                "description": "Optional restrictions on which fighters can take this advancement.",
            },
        ),
    )

    def get_equipment_count(self, obj):
        return obj.assignments.count()

    get_equipment_count.short_description = "Assignment Options"

    def get_restrictions(self, obj):
        restrictions = []
        if obj.restricted_to_houses.exists():
            restrictions.append(
                f"Houses: {', '.join(h.name for h in obj.restricted_to_houses.all()[:2])}"
            )
        if obj.restricted_to_fighter_categories:
            restrictions.append(
                f"Categories: {', '.join(obj.restricted_to_fighter_categories[:2])}"
            )
        return " | ".join(restrictions) if restrictions else "-"

    get_restrictions.short_description = "Restrictions"


@admin.register(ContentEquipmentFighterProfile)
class ContentEquipmentFighterProfileAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["equipment__name", "content_fighter__type"]
    autocomplete_fields = ["equipment", "content_fighter"]


@admin.register(ContentEquipmentEquipmentProfile)
class ContentEquipmentEquipmentProfileAdmin(ContentAdmin):
    search_fields = ["equipment__name", "linked_equipment__name"]
    autocomplete_fields = ["equipment", "linked_equipment"]


class ContentWeaponProfileAdminForm(forms.ModelForm):
    class Meta:
        model = ContentWeaponProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        """Validate that no smart quotes are used in stat fields."""
        cleaned_data = super().clean()

        # Smart quotes to check for
        smart_quotes = SMART_QUOTES.values()

        # Fields to check for smart quotes
        stat_fields = [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]

        for field in stat_fields:
            value = cleaned_data.get(field)
            if (
                value
                and isinstance(value, str)
                and any(quote in value for quote in smart_quotes)
            ):
                raise forms.ValidationError(
                    {
                        field: 'Smart quotes are not allowed. Please use simple quotes (") instead.'
                    }
                )

        return cleaned_data


@admin.register(ContentWeaponProfile)
class ContentWeaponProfileAdmin(ContentAdmin):
    form = ContentWeaponProfileAdminForm
    search_fields = ["name"]
    list_display_links = ["equipment", "name"]
    autocomplete_fields = ["equipment"]


def mods(obj):
    """
    Display comma-separated list of modifier names.

    Helper function for admin list display to show all modifiers
    associated with an object.

    Args:
        obj: Model instance with modifiers relation

    Returns:
        Comma-separated string of modifier names
    """
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


class ContentModFighterStatAdminForm(forms.ModelForm):
    stat = forms.CharField(
        max_length=50, widget=forms.Select(attrs={"class": "form-select"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate choices from ContentStat objects
        stat_choices = [
            (stat.field_name, stat.full_name)
            for stat in ContentStat.objects.all().order_by("full_name")
        ]
        self.fields["stat"].widget.choices = stat_choices

    class Meta:
        model = ContentModFighterStat
        fields = ["stat", "mode", "value"]


@admin.register(ContentModFighterStat)
class ContentModFighterStatAdmin(ContentModChildAdmin):
    base_model = ContentModFighterStat
    form = ContentModFighterStatAdminForm


@admin.register(ContentModTrait)
class ContentModTraitAdmin(ContentModChildAdmin):
    base_model = ContentModTrait


@admin.register(ContentModFighterRule)
class ContentModFighterRuleAdmin(ContentModChildAdmin):
    base_model = ContentModFighterRule
    autocomplete_fields = ["rule"]


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
        """
        Order page references by numeric page number.

        Converts string page numbers to integers for proper ordering,
        treating empty pages as 0.

        Args:
            request: The current HTTP request

        Returns:
            QuerySet ordered by numeric page value
        """
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
    list_display = ["name", "default_for_categories", "get_stat_count"]
    list_display_links = ["name"]

    inlines = [ContentStatlineTypeStatInline]

    def get_stat_count(self, obj):
        return obj.stats.count()

    get_stat_count.short_description = "Stats"


class ContentStatlineStatForm(forms.ModelForm):
    """Form for ContentStatlineStat with smart quote validation."""

    def clean_value(self):
        """Validate that no smart quotes are used in stat value."""
        value = self.cleaned_data.get("value")

        # Smart quotes to check for
        smart_quotes = SMART_QUOTES.values()

        if (
            value
            and isinstance(value, str)
            and any(quote in value for quote in smart_quotes)
        ):
            raise forms.ValidationError(
                'Smart quotes are not allowed. Please use simple quotes (") instead.'
            )

        return value

    class Meta:
        model = ContentStatlineStat
        fields = "__all__"


class ContentStatlineStatInline(ContentTabularInline):
    model = ContentStatlineStat
    form = ContentStatlineStatForm
    extra = 0
    fields = ["statline_type_stat", "value"]
    readonly_fields = []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Filter statline type stats based on parent statline.

        Ensures only stats relevant to the current statline type are shown
        when editing statline stats inline.

        Args:
            db_field: The foreign key field being rendered
            request: The current HTTP request
            **kwargs: Additional field parameters

        Returns:
            Modified form field with filtered queryset
        """
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
    autocomplete_fields = ["content_fighter"]
    list_display = ["content_fighter", "statline_type"]
    list_filter = ["statline_type"]
    list_display_links = ["content_fighter"]
    inlines = [ContentStatlineStatInline]

    def save_related(self, request, form, formsets, change):
        """
        Ensure all required stats exist for a statline after saving.

        Creates missing ContentStatlineStat entries with default empty values
        for any stats required by the statline type but not yet present.

        Args:
            request: The current HTTP request
            form: The main model form
            formsets: Related inline formsets
            change: Boolean indicating if this is an edit (True) or create (False)
        """
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
    autocomplete_fields = ["equipment", "weapon_profile"]
    fields = ["equipment", "weapon_profile", "cost"]
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


@admin.register(ContentAvailabilityPreset)
class ContentAvailabilityPresetAdmin(ContentAdmin):
    list_filter = ["category", "house"]
    search_fields = ["fighter__type", "house__name"]
    autocomplete_fields = ["fighter", "house"]

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        self.list_display = ["preset_name_display"] + self.list_display
        self.list_display_links = ["preset_name_display"]

    @admin.display(description="Name")
    def preset_name_display(self, obj):
        return obj.preset_name


# Counters & Roll Tables


class ContentRollFlowInline(ContentTabularInline):
    model = ContentRollFlow
    extra = 0
    fields = ["name", "cost", "roll_table"]
    autocomplete_fields = ["roll_table"]


@admin.register(ContentCounter)
class ContentCounterAdmin(ContentAdmin):
    search_fields = ["name"]
    list_display = ["name", "description", "display_order"]
    filter_horizontal = ["restricted_to_fighters"]
    inlines = [ContentRollFlowInline]


class ContentRollTableRowInline(ContentTabularInline):
    model = ContentRollTableRow
    extra = 0
    fields = ["sort_order", "roll_value", "name", "description", "rating_increase"]


@admin.register(ContentRollTable)
class ContentRollTableAdmin(ContentAdmin):
    search_fields = ["name"]
    list_display = ["name", "dice", "description"]
    list_filter = ["dice"]
    inlines = [ContentRollTableRowInline]


@admin.register(ContentRollTableRow)
class ContentRollTableRowAdmin(ContentAdmin):
    search_fields = ["name", "table__name"]
    list_display = ["table", "roll_value", "name", "rating_increase", "sort_order"]
    list_filter = ["table"]
    autocomplete_fields = ["table"]
    filter_horizontal = ["modifiers"]


@admin.register(ContentRollFlow)
class ContentRollFlowAdmin(ContentAdmin):
    search_fields = ["name"]
    list_display = ["name", "counter", "cost", "roll_table"]
    autocomplete_fields = ["counter", "roll_table"]
