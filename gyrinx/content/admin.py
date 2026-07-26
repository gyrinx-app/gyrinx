import operator
from collections import defaultdict
from functools import reduce
from itertools import groupby

from django import forms
from django.contrib import admin, messages
from django.contrib.contenttypes.models import ContentType
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
    ContentBattleRole,
    ContentBattleRoleOption,
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentInjuryLink,
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
    ContentHouseSkillRankAccess,
    ContentCounter,
    ContentInjury,
    ContentInjuryGroup,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
    ContentMod,
    ContentModApplication,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModPsykerDisciplineAccess,
    ContentModSkillTreeAccess,
    ContentModStat,
    ContentModTrait,
    ContentPageRef,
    ContentPolicy,
    ContentPromotionPath,
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


def fighter_house_name(fighter):
    """Group label for fighter selects, tolerant of a missing house.

    A dangling ``house`` FK (local template-data drift) raises ``DoesNotExist``
    on attribute access — even behind an ``if fighter.house`` guard — which used
    to 500 whole admin pages (e.g. every equipment change page). Group such
    fighters under "No House" instead.
    """
    try:
        return fighter.house.name if fighter.house else "No House"
    except ContentHouse.DoesNotExist:
        return "No House"


def grouped_fighter_choices(field):
    """Build house-grouped ``<optgroup>`` choices for a fighter select.

    ``group_select`` does the same job, but it runs inside a form's ``__init__``
    — so on an inline it re-iterates every fighter once per row and issues an
    N+1 query for each fighter's house. Building the choices once, with
    ``select_related("house")``, and sharing the resulting list across rows
    turns thousands of queries into one. See
    ``share_grouped_fighter_choices``.
    """
    label = field.label_from_instance
    fighters = field.queryset.select_related("house").order_by("house__name", "type")
    return [("", "---------")] + [
        (house_name, [(fighter.pk, label(fighter)) for fighter in items])
        for house_name, items in groupby(fighters, key=fighter_house_name)
    ]


def share_field_choices(formset, field_name, build_choices):
    """Give every row of ``formset`` the same precomputed choices for a field.

    Inline formsets build one form per existing row plus an empty template
    form. A field whose option list is expensive to assemble — a fighter select
    grouped by house, a polymorphic modifications select — would otherwise be
    rebuilt from scratch by each of those forms, so the page's cost grows with
    the number of rows.
    """
    # A field listed in readonly_fields is not on the form at all.
    if field_name not in formset.form.base_fields:
        return formset

    choices = build_choices(formset.form.base_fields[field_name])
    original_form = formset.form

    class FormWithSharedChoices(original_form):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields[field_name].widget.choices = choices

    formset.form = FormWithSharedChoices
    return formset


def share_grouped_fighter_choices(formset, field_name):
    """Share one house-grouped fighter option list across every inline row."""
    return share_field_choices(formset, field_name, grouped_fighter_choices)


def _fighter_stat_mods(queryset):
    mods = list(queryset)
    ContentModFighterStat.prime_stat_definitions(mods)
    return mods


# How to load each concrete modification type so its label costs no further
# queries. A polymorphic queryset can't ``select_related`` a child model's
# field, so labelling modifications one at a time costs a query each — see
# ``modifier_choices``.
#
# This is an optimisation, not an allow-list: a type missing from here still
# gets its options, just at a query per row. ``modifier_choices`` drives off
# what is actually in the queryset so a new subclass can never silently lose
# its <option> (and with it, the selection, on the next save).
MODIFIER_LABEL_LOADERS = {
    ContentModStat: list,
    ContentModFighterStat: _fighter_stat_mods,
    ContentModTrait: lambda qs: list(qs.select_related("trait")),
    ContentModFighterRule: lambda qs: list(qs.select_related("rule")),
    ContentModFighterSkill: lambda qs: list(qs.select_related("skill")),
    ContentModSkillTreeAccess: lambda qs: list(qs.select_related("skill_category")),
    ContentModPsykerDisciplineAccess: lambda qs: list(qs.select_related("discipline")),
}

# The subset that changes something on the fighter rather than a weapon.
FIGHTER_MODIFIER_TYPES = (
    ContentModFighterStat,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModSkillTreeAccess,
    ContentModPsykerDisciplineAccess,
)


def modifier_choices(field):
    """Build the option list for a modifications field in one query per type.

    Django asks each modification for its label, and a polymorphic instance
    fetches its own related objects — so a list of N modifications costs N
    queries, repeated for every form on the page. Grouping the queryset by
    concrete type lets ``select_related`` do that work up front.

    Every type present is loaded, whether or not ``MODIFIER_LABEL_LOADERS``
    knows about it. A modification with no ``<option>`` cannot be submitted, so
    dropping one here would quietly clear it from the field on the next save.
    """
    pks_by_type = defaultdict(list)
    for pk, ctype_id in field.queryset.non_polymorphic().values_list(
        "pk", "polymorphic_ctype_id"
    ):
        pks_by_type[ctype_id].append(pk)

    mods = []
    for ctype_id, pks in pks_by_type.items():
        model = ContentType.objects.get_for_id(ctype_id).model_class()
        if model is None:
            continue
        load = MODIFIER_LABEL_LOADERS.get(model, list)
        mods.extend(load(model.objects.filter(pk__in=pks)))

    label = field.label_from_instance
    return sorted(((mod.pk, label(mod)) for mod in mods), key=lambda choice: choice[1])


def restrict_to_fighter_modifiers(field):
    """Limit a modifications field to the types that affect fighters."""
    field.queryset = reduce(
        operator.or_,
        (field.queryset.instance_of(model) for model in FIGHTER_MODIFIER_TYPES),
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


class _AllContentInlineMixin:
    """Shared behaviour for content inlines that surface pack content.

    Content managers exclude pack content by default; ``all_content()``
    bypasses that filter. These inlines display *all* content (including pack
    items) so it can be managed from the admin.

    The catch: Django builds the inline formset's primary-key field as a
    ``ModelChoiceField`` whose queryset comes from ``model._default_manager``,
    which excludes pack content. So a pack-content row renders fine but fails
    validation on its hidden ``id`` field with "Select a valid choice…". That
    error is never displayed (the tabular template doesn't render hidden-field
    errors), yet ``AdminErrorList`` counts it — the page shows "Please correct
    the errors below" with no visible error and the row can never be saved.

    To keep the display and validation querysets consistent, ``get_formset``
    binds the pk field's queryset to the formset's own queryset (which uses
    ``all_content()`` and is filtered to the parent instance) instead of the
    default manager.
    """

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

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        manager = self.model._default_manager
        if not hasattr(manager, "all_content"):
            return formset

        pk_name = self.model._meta.pk.name

        class AllContentFormSet(formset):
            def add_fields(self, form, index):
                super().add_fields(form, index)
                pk_field = form.fields.get(pk_name)
                # The pk field is a ModelChoiceField bound to the default
                # manager, which excludes pack content — so pack-content rows
                # this inline displays would fail validation on their hidden id.
                # Bind it to the formset's queryset instead: it includes pack
                # content (all_content()) yet stays scoped to this parent, so a
                # crafted POST can't smuggle in an unrelated object's pk.
                if pk_field is not None and hasattr(pk_field, "queryset"):
                    pk_field.queryset = self.get_queryset()

        return AllContentFormSet


class ContentTabularInline(_AllContentInlineMixin, admin.TabularInline):
    pass


class ContentStackedInline(_AllContentInlineMixin, admin.StackedInline):
    pass


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
    The fighter field is rendered as a grouped-by-house dropdown; the inline
    builds those choices once and shares them across rows (see
    ``ContentFighterEquipmentCategoryLimitInline.get_formset``).
    """

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
        Customize the formset to render the fighter field as a grouped-by-house
        dropdown and to pass the parent instance to child forms for validation.

        The grouped choices are built once here — with ``select_related`` on the
        fighter's house — and shared across every inline row. Previously
        ``group_select`` ran inside each row's form ``__init__``, re-iterating
        all fighters and issuing an N+1 query for each fighter's house, which
        made this page extremely slow on categories with many limits.

        Args:
            request: The current HTTP request
            obj: The parent ContentEquipmentCategory instance
            **kwargs: Additional formset parameters

        Returns:
            Formset class with shared grouped choices and parent instance access
        """
        formset = super().get_formset(request, obj, **kwargs)
        formset = share_grouped_fighter_choices(formset, "fighter")

        original_form = formset.form
        parent_instance = obj

        class FormWithParentInstance(original_form):
            """Expose the parent equipment category to the form for validation."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if parent_instance is not None:
                    self.parent_instance = parent_instance

        formset.form = FormWithParentInstance
        return formset


@admin.register(ContentEquipmentCategory)
class ContentEquipmentCategoryAdmin(ContentAdmin):
    search_fields = ["name", "group"]
    list_display_links = ["name"]
    list_display_fields = ["name"]
    list_filter = [
        "group",
        "restricted_to",
        "visible_only_if_in_equipment_list",
        "persistent",
    ]
    inlines = [
        ContentEquipmentCategoryFighterRestrictionInline,
        ContentFighterEquipmentCategoryLimitInline,
    ]


class ContentWeaponProfileInline(ContentStackedInline):
    model = ContentWeaponProfile
    extra = 0

    def get_queryset(self, request):
        # Each row lists its traits and names its equipment; without this that
        # is two queries per profile.
        return (
            super()
            .get_queryset(request)
            .select_related("equipment")
            .prefetch_related("traits")
        )


class ContentWeaponAccessoryInline(ContentTabularInline):
    model = ContentWeaponAccessory
    extra = 0


class ContentEquipmentFighterProfileInline(ContentTabularInline):
    model = ContentEquipmentFighterProfile
    extra = 0

    def get_queryset(self, request):
        # Each row names its equipment and fighter, and a fighter's name
        # includes its house.
        return (
            super()
            .get_queryset(request)
            .select_related("equipment", "content_fighter__house")
        )

    def get_formset(self, request, obj=None, **kwargs):
        """Render the fighter select grouped by house, built once per page.

        This inline used to group the choices in each row's form ``__init__``,
        which re-walked every fighter (and queried its house) once per row —
        the single biggest cost in rendering the equipment change page.
        """
        formset = super().get_formset(request, obj, **kwargs)
        return share_grouped_fighter_choices(formset, "content_fighter")


class ContentEquipmentEquipmentProfileInline(ContentTabularInline):
    model = ContentEquipmentEquipmentProfile
    extra = 0
    fk_name = "equipment"


class ContentEquipmentUpgradeInline(ContentTabularInline):
    model = ContentEquipmentUpgrade
    extra = 0

    def get_queryset(self, request):
        # Each row shows the modifications it already has selected and names
        # its equipment; without this that is two queries per row.
        return (
            super()
            .get_queryset(request)
            .select_related("equipment")
            .prefetch_related("modifiers")
        )

    def get_formset(self, request, obj=None, **kwargs):
        """Build the modifications option list once for all upgrade rows.

        Equipment with many upgrades (Unborn has 18) rendered the full
        polymorphic modifications list once per row, at a query per
        modification per row.
        """
        formset = super().get_formset(request, obj, **kwargs)
        return share_field_choices(formset, "modifiers", modifier_choices)


class ContentEquipmentInjuryLinkInline(ContentTabularInline):
    """Equipment-injury links, editable from either end of the relation."""

    model = ContentEquipmentInjuryLink
    extra = 0
    fields = ["equipment", "injury", "mode"]
    # Without these, the injury page renders a <select> of every piece of
    # equipment once per row plus the empty template form.
    autocomplete_fields = ["equipment", "injury"]
    verbose_name = "Injury treated"
    verbose_name_plural = "Injuries treated"

    def get_queryset(self, request):
        # Both columns are rendered on every row, so without this the inline
        # costs a query per link.
        return super().get_queryset(request).select_related("equipment", "injury")


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
        # Only offer modifications that change things on the fighter. Order
        # matters: assigning a field's queryset resets its widget choices, so
        # the restriction has to happen before the choices are built.
        modifiers_field = self.fields["modifiers"]
        restrict_to_fighter_modifiers(modifiers_field)
        modifiers_field.widget.choices = modifier_choices(modifiers_field)

        # Every fighter is rendered as an option here, and a fighter's label
        # includes its house — without select_related that is one query per
        # fighter.
        companion_field = self.fields.get("auto_companion_for_fighter")
        if companion_field is not None:
            companion_field.queryset = companion_field.queryset.select_related("house")

        group_select(self, "category", key=lambda x: x.group)


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentEquipmentAdminForm

    search_fields = ["name", "category__name", "contentweaponprofile__name"]
    list_filter = ["category", "crew_treated_as_fighter"]

    inlines = [
        ContentWeaponProfileInline,
        ContentEquipmentFighterProfileInline,
        ContentEquipmentEquipmentProfileInline,
        ContentEquipmentUpgradeInline,
        ContentEquipmentInjuryLinkInline,
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
        group_select(self, "fighter", key=fighter_house_name)
        group_select(self, "psyker_power", key=lambda x: x.discipline.name)


@admin.register(ContentFighterPsykerPowerDefaultAssignment)
class ContentFighterPsykerPowerDefaultAssignmentAdmin(ContentAdmin):
    search_fields = ["fighter__type", "psyker_power__name"]
    list_filter = ["fighter__type", "psyker_power__discipline"]
    form = ContentFighterPsykerPowerDefaultAssignmentForm


class ContentFighterInline(ContentTabularInline):
    model = ContentFighter
    # Only render cheap scalar fields. The default (all fields) renders the
    # fighter's M2M widgets (skills, primary/secondary skill categories, rules)
    # as <select multiple> per row, evaluating each field's queryset per form.
    # For a house with dozens of fighters that is tens of thousands of <option>
    # elements and hundreds of full-table queries — the change page took minutes
    # to load. Use show_change_link (inherited) to edit the rest of a fighter.
    fields = ["type", "category", "base_cost"]
    extra = 0


class ContentHouseSkillRankAccessInline(ContentTabularInline):
    model = ContentHouseSkillRankAccess
    fields = ["fighter_category", "slot", "role"]
    extra = 0


@admin.register(ContentHouse)
class ContentHouseAdmin(ContentAdmin, admin.ModelAdmin):
    # ContentAdmin.__init__ builds list_display from the model's fields, so the
    # new `icon` field appears in the changelist automatically — no override
    # needed here. The icon is editable via the change form for the same reason.
    list_display_links = ["name"]
    search_fields = ["name"]
    filter_horizontal = ["skill_categories", "gang_skill_tree_choices"]
    inlines = [ContentHouseSkillRankAccessInline, ContentFighterInline]


@admin.register(ContentHouseSkillRankAccess)
class ContentHouseSkillRankAccessAdmin(ContentAdmin, admin.ModelAdmin):
    list_filter = ["house", "fighter_category", "role"]
    list_display_links = ["fighter_category"]
    search_fields = ["house__name"]


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


class ContentPromotionPathAdminForm(forms.ModelForm):
    # The model stores rolls as a JSON list of 2d6 totals; hand-typing a JSON array is
    # error-prone, so render one checkbox per possible total instead (same pattern as
    # ContentAdvancementEquipmentAdminForm's restricted_to_fighter_categories).
    rolls = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=[(total, str(total)) for total in range(2, 13)],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="2d6 totals that offer this promotion in the roll-driven flow.",
    )

    class Meta:
        model = ContentPromotionPath
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["rolls"].initial = self.instance.rolls or []

    def clean_rolls(self):
        # Store sorted for stable equality/display; checkboxes make dupes impossible.
        return sorted(self.cleaned_data.get("rolls") or [])


@admin.register(ContentPromotionPath)
class ContentPromotionPathAdmin(ContentAdmin, admin.ModelAdmin):
    form = ContentPromotionPathAdminForm
    search_fields = ["name"]
    list_filter = [
        "kind",
        "timing",
        "from_category",
        "to_category",
        "restricted_to_houses",
    ]
    filter_horizontal = ["restricted_to_houses"]
    # targets uses autocomplete, not filter_horizontal: rendering a choice per catalog
    # fighter is an N+1 over thousands of rows and 500s on any fighter whose house row
    # is missing (str() dereferences house).
    autocomplete_fields = ["source_fighter", "targets"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "kind",
                    "from_category",
                    "source_fighter",
                    "to_category",
                    "targets",
                    "rank",
                )
            },
        ),
        ("Cost", {"fields": ("xp_cost", "cost_increase")}),
        (
            "Behaviour",
            {
                "fields": ("grants_skill", "rolls", "advancements_threshold", "timing"),
                "description": "What the fighter gains, the 2d6 totals that offer this promotion in the roll-driven flow, and when the rules say it happens.",
            },
        ),
        (
            "Restrictions",
            {
                "fields": ("restricted_to_houses",),
                "classes": ("collapse",),
                "description": "Optional: limit which houses are offered this promotion.",
            },
        ),
    )

    def get_list_display(self, request):
        # ContentAdmin.__init__ builds list_display from every model field (including the raw
        # `rolls` JSON); override with a curated set. Keep packs_display — a promotion path can
        # itself be pack content.
        return (
            "name",
            "kind",
            "from_category",
            "to_category",
            "rank",
            "xp_cost",
            "cost_increase",
            "grants_skill",
            "packs_display",
        )


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
    list_display_links = ("mod_description",)
    # Downcast changelist rows to their real subclass (batched per child model
    # by django-polymorphic) so each renders its own __str__ instead of the base
    # "Base Modification". Without this the parent admin marks the queryset
    # .non_polymorphic() for speed and rows come back as base ContentMod.
    polymorphic_list = True

    @admin.display(description="Modification")
    def mod_description(self, obj):
        # obj is downcast (polymorphic_list = True), so str(obj) renders the
        # mod's own description, e.g. "Add rule Cunning Killers".
        return str(obj)

    def get_list_display(self, request):
        # ContentAdmin.__init__ builds list_display from the base model's
        # fields, which for the polymorphic parent is just ``polymorphic_ctype``
        # — an unhelpful "Content | Fighter Rule Modifier" label. Lead with the
        # rendered mod instead, keeping the type column alongside.
        #
        # ContentAdmin also appends ``packs_display``, but a ContentMod is never
        # a CustomContentPackItem (mods attach via M2M / ContentModApplication),
        # so it would always render "-" while costing a query per row. Drop it.
        return ("mod_description", "polymorphic_ctype")


@admin.register(ContentModApplication)
class ContentModApplicationAdmin(ContentAdmin):
    list_filter = ("target_content_type",)
    raw_id_fields = ("modifier",)

    def get_list_display(self, request):
        return ("__str__", "target_content_type", "modifier", "packs_display")


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
    list_filter = ["shed_on_promotion"]


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

    inlines = [ContentModInline, ContentEquipmentInjuryLinkInline]

    def get_modifier_count(self, obj):
        return obj.modifiers.count()

    get_modifier_count.short_description = "Modifiers"


class ContentBattleRoleOptionInline(ContentTabularInline):
    model = ContentBattleRoleOption
    extra = 0
    fields = ["name", "description"]


@admin.register(ContentBattleRole)
class ContentBattleRoleAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "description"]
    list_display = ["name", "description", "get_option_count"]
    readonly_fields = ["id", "created", "modified"]
    inlines = [ContentBattleRoleOptionInline]

    @admin.display(description="Options")
    def get_option_count(self, obj):
        return obj.options.count()


@admin.register(ContentBattleRoleOption)
class ContentBattleRoleOptionAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "description", "role__name"]
    list_filter = ["role"]
    list_display = ["name", "role", "description"]
    readonly_fields = ["id", "created", "modified"]


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
    list_display = ["name", "description", "display_order", "warning_stat"]
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
