"""
Equipment models for content data.

This module contains:
- ContentEquipmentCategory: Equipment categories
- ContentEquipmentCategoryFighterRestriction: Category restrictions by fighter type
- ContentFighterEquipmentCategoryLimit: Per-fighter category limits
- ContentEquipmentManager/QuerySet: Custom manager and queryset
- ContentEquipment: Main equipment model
- ContentEquipmentUpgradeManager/QuerySet: Upgrade manager and queryset
- ContentEquipmentUpgrade: Equipment upgrades
- ContentEquipmentFighterProfile: Links equipment to fighter types
- ContentEquipmentEquipmentProfile: Links equipment to other equipment
"""

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.models import (
    CostMixin,
    FighterCategoryChoices,
    FighterCostMixin,
    QuerySetOf,
    equipment_category_group_choices,
    format_cost_display,
)

from .base import Content, ContentManager, ContentQuerySet

if TYPE_CHECKING:
    from .weapon import ContentWeaponProfile


class ContentEquipmentCategory(Content):
    name = models.CharField(max_length=255, unique=True)
    group = models.CharField(max_length=255, choices=equipment_category_group_choices)
    restricted_to = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        related_name="restricted_equipment_categories",
        verbose_name="Restricted To",
        help_text="If provided, this equipment category is only available to specific gang houses.",
    )
    visible_only_if_in_equipment_list = models.BooleanField(
        default=False,
        help_text="If True, this category will only be visible on fighter cards if the fighter has equipment in this category in their equipment list.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def get_fighter_category_restrictions(self):
        """Returns a list of fighter categories this equipment category is restricted to."""
        return list(
            ContentEquipmentCategoryFighterRestriction.objects.filter(
                equipment_category=self
            ).values_list("fighter_category", flat=True)
        )

    def is_available_to_fighter_category(self, fighter_category):
        """Check if this equipment category is available to a specific fighter category."""
        restrictions = self.get_fighter_category_restrictions()
        # If no restrictions, available to all
        if not restrictions:
            return True
        # If restrictions exist, fighter category must be in the list
        return fighter_category in restrictions

    class Meta:
        verbose_name = "Equipment Category"
        verbose_name_plural = "Equipment Categories"
        ordering = ["name"]


class ContentEquipmentCategoryFighterRestriction(models.Model):
    equipment_category = models.ForeignKey(
        ContentEquipmentCategory,
        on_delete=models.CASCADE,
        related_name="fighter_restrictions",
    )
    fighter_category = models.CharField(
        max_length=255, choices=FighterCategoryChoices.choices
    )

    class Meta:
        unique_together = ["equipment_category", "fighter_category"]
        verbose_name = "Equipment Category Fighter Restriction"
        verbose_name_plural = "Equipment Category Fighter Restrictions"

    def __str__(self):
        return f"{self.equipment_category.name} - {self.get_fighter_category_display()}"


class ContentFighterEquipmentCategoryLimit(Content):
    """
    Links ContentFighter to ContentEquipmentCategory with a numeric limit.
    Used to set per-fighter limits on category-restricted equipment.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="equipment_category_limits",
    )
    equipment_category = models.ForeignKey(
        ContentEquipmentCategory,
        on_delete=models.CASCADE,
        related_name="fighter_limits",
    )
    limit = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of items from this category the fighter can have.",
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = ["fighter", "equipment_category"]
        verbose_name = "Fighter Equipment Category Limit"
        verbose_name_plural = "Fighter Equipment Category Limits"
        ordering = ["fighter__type", "equipment_category__name"]

    def __str__(self):
        return f"{self.fighter} - {self.equipment_category.name} (limit: {self.limit})"

    def clean(self):
        """
        Validate that the equipment category has a ContentEquipmentCategoryFighterRestriction.
        """
        if not ContentEquipmentCategoryFighterRestriction.objects.filter(
            equipment_category=self.equipment_category
        ).exists():
            raise ValidationError(
                {
                    "equipment_category": "The equipment category must have fighter restrictions before limits can be set."
                }
            )


class ContentEquipmentManager(ContentManager):
    """
    Custom manager for :model:`content.ContentEquipment` model, providing annotated
    default querysets (cost as integer, presence of weapon profiles, etc.).
    """

    def _annotate_default(self, qs):
        """Apply the default cost and weapon profile annotations."""
        from .weapon import ContentWeaponProfile

        return qs.annotate(
            cost_cast_int=Case(
                When(
                    Q(cost__regex=r"^-?\d+$"),
                    then=Cast("cost", models.IntegerField()),
                ),
                default=0,
            ),
            has_weapon_profiles=Exists(
                ContentWeaponProfile.objects.filter(equipment=OuterRef("pk"))
            ),
        ).order_by("category__name", "name", "id")

    def get_queryset(self):
        """
        Returns the default annotated queryset for equipment, excluding pack content.
        """
        return self._annotate_default(super().get_queryset())

    def all_content(self):
        """Return all equipment including pack content."""
        return self._annotate_default(super().all_content())

    def with_packs(self, packs):
        """Return base equipment plus equipment from specified packs."""
        return self._annotate_default(super().with_packs(packs))


class ContentEquipmentQuerySet(ContentQuerySet):
    """
    Custom QuerySet for ContentEquipment. Provides filtering and annotations
    for weapons vs. non-weapons, and fighter-specific cost.
    """

    def weapons(self) -> "ContentEquipmentQuerySet":
        """
        Filters the queryset to include only equipment items identified as weapons.
        """
        return self.filter(has_weapon_profiles=True)

    def non_weapons(self) -> "ContentEquipmentQuerySet":
        """
        Filters the queryset to include only equipment items that are not weapons.
        """
        return self.exclude(has_weapon_profiles=True)

    def house_restricted(self, house) -> "ContentEquipmentQuerySet":
        return self.filter(Q(category__restricted_to=house))

    def with_cost_for_fighter(self, content_fighter) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with fighter-specific cost overrides, if any.
        """
        # Import here to avoid circular import
        from .equipment_list import ContentFighterEquipmentListItem

        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("pk"),
            # This is critical to make sure we only annotate the cost of the base equipment.
            weapon_profile__isnull=True,
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost_cast_int"),
        )

    def with_expansion_cost_for_fighter(
        self, content_fighter, rule_inputs
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with fighter-specific cost overrides,
        including those from equipment list expansions.
        """
        # Import here to avoid circular import
        from .equipment_list import ContentFighterEquipmentListItem
        from .expansion import (
            ContentEquipmentListExpansion,
            ContentEquipmentListExpansionItem,
        )

        # Filter to only expansions that apply
        expansion_ids = ContentEquipmentListExpansion.get_applicable_expansions(
            rule_inputs
        ).values("id")

        # Get expansion item cost overrides (only for base equipment, not profiles)
        expansion_items = ContentEquipmentListExpansionItem.objects.filter(
            expansion__in=Subquery(expansion_ids),
            equipment=OuterRef("pk"),
            weapon_profile__isnull=True,  # Only base equipment costs, not profile-specific
        )

        # Get normal equipment list cost overrides
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("pk"),
            weapon_profile__isnull=True,
        )

        return self.annotate(
            # Cost from normal equipment list
            equipment_list_cost=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            # Cost from expansion
            expansion_cost=Subquery(
                expansion_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            # Use expansion cost if available, otherwise equipment list cost, otherwise base cost
            cost_for_fighter=Coalesce(
                "expansion_cost", "equipment_list_cost", "cost_cast_int"
            ),
            # Track if this came from an expansion
            from_expansion=Exists(expansion_items),
        )

    def with_profiles_for_fighter(self, content_fighter) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with weapon profiles for a given fighter, if any.
        """
        from .weapon import ContentWeaponProfile

        return self.prefetch_related(
            models.Prefetch(
                "contentweaponprofile_set",
                queryset=ContentWeaponProfile.objects.with_cost_for_fighter(
                    content_fighter
                ),
                to_attr="pre_profiles_for_fighter",
            )
        )

    def with_expansion_profiles_for_fighter(
        self, content_fighter, rule_inputs
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with weapon profiles for a given fighter,
        including those from equipment list expansions.
        """
        from .equipment_list import ContentFighterEquipmentListItem
        from .expansion import (
            ContentEquipmentListExpansion,
            ContentEquipmentListExpansionItem,
        )
        from .weapon import ContentWeaponProfile

        # Filter to only expansions that apply
        expansion_ids = ContentEquipmentListExpansion.get_applicable_expansions(
            rule_inputs
        ).values("id")

        # Get expansion item profile cost overrides
        expansion_profile_items = ContentEquipmentListExpansionItem.objects.filter(
            expansion__in=Subquery(expansion_ids),
            equipment=OuterRef("equipment"),
            weapon_profile=OuterRef("pk"),
        )

        # Get normal equipment list profile cost overrides
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("equipment"),
            weapon_profile=OuterRef("pk"),
        )

        # Create a queryset that includes both regular profiles and expansion profiles
        profile_queryset = ContentWeaponProfile.objects.annotate(
            # First priority: Expansion profile cost override
            expansion_profile_cost=Subquery(
                expansion_profile_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            # Second priority: Equipment list profile cost override
            equipment_list_profile_cost=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            # Use Coalesce to prioritize expansion > equipment list > base cost
            cost_override=Coalesce(
                "expansion_profile_cost",
                "equipment_list_profile_cost",
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
            # Track if this profile came from an expansion
            from_expansion=Exists(expansion_profile_items),
        )

        return self.prefetch_related(
            models.Prefetch(
                "contentweaponprofile_set",
                queryset=profile_queryset,
                to_attr="pre_profiles_for_fighter",
            )
        )


class ContentEquipment(FighterCostMixin, Content):
    """
    Represents an item of equipment that a fighter may acquire.
    Can be a weapon or other piece of gear. Cost and rarity are tracked.
    """

    name = models.CharField(max_length=255, db_index=True)
    category = models.ForeignKey(
        ContentEquipmentCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        related_name="equipment",
        db_index=True,
    )

    cost = models.CharField(
        help_text="The credit cost of the equipment at the Trading Post. Note that, in weapons, "
        "this is overridden by the 'Standard' weapon profile cost.",
        blank=True,
        null=False,
    )

    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("U", "Unique (U)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this equipment from the Trading Post. Use 'U' for equipment that is unique to a fighter.",
        verbose_name="Availability",
        db_index=True,
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    class UpgradeMode(models.TextChoices):
        SINGLE = "SINGLE", "Single"
        MULTI = "MULTI", "Multi"

    upgrade_mode = models.CharField(
        max_length=6,
        choices=UpgradeMode.choices,
        default=UpgradeMode.SINGLE,
        help_text="If applicable, does this equipment have an upgrade stack (single, e.g. cyberteknika) or options (multi, e.g. genesmithing)?",
    )

    upgrade_stack_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default="",
        help_text="If applicable, the name of the stack of upgrades for this equipment (e.g. Upgrade or Augmentation). Use the singular form.",
    )

    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the fighter's statline and traits.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    @cached_property
    def upgrade_stack_name_display(self):
        """
        Returns the upgrade stack name, or a default if not set.
        """
        return self.upgrade_stack_name or "Upgrade"

    def cat(self):
        """
        Returns the human-readable label of the equipment's category.
        """
        return self.category.name

    def is_weapon(self):
        """
        Indicates whether this equipment is a weapon. If 'has_weapon_profiles'
        is annotated, uses that; otherwise checks the database.
        """
        if hasattr(self, "has_weapon_profiles"):
            return self.has_weapon_profiles
        return self.contentweaponprofile_set.exists()

    @cached_property
    def is_weapon_cached(self):
        return self.is_weapon()

    @cached_property
    def is_house_additional(self):
        """
        Indicates whether this equipment is house-specific additional gear.
        """
        return self.category.restricted_to.exists()

    @cached_property
    def upgrade_mode_single(self):
        """
        Indicates whether this equipment is a multi-upgrade mode.
        """
        return self.upgrade_mode == ContentEquipment.UpgradeMode.SINGLE

    @cached_property
    def upgrade_mode_multi(self):
        """
        Indicates whether this equipment is a single-upgrade mode.
        """
        return self.upgrade_mode == ContentEquipment.UpgradeMode.MULTI

    def profiles(self):
        """
        Returns all associated weapon profiles for this equipment.
        """
        return self.contentweaponprofile_set.all()

    def profiles_for_fighter(
        self, content_fighter
    ) -> QuerySetOf["ContentWeaponProfile"]:
        """
        Returns all weapon profiles for this equipment, annotated with
        fighter-specific cost if available.
        """
        if hasattr(self, "pre_profiles_for_fighter"):
            return self.pre_profiles_for_fighter

        from .weapon import ContentWeaponProfile

        return ContentWeaponProfile.objects.filter(
            equipment=self
        ).with_cost_for_fighter(content_fighter)

    def set_dirty(self) -> None:
        """
        Mark all ListFighterEquipmentAssignments using this equipment as dirty.

        Propagates to parent fighters and lists via their set_dirty() methods.
        Called when this equipment's cost field changes.
        """
        # Lazy import to avoid circular dependency
        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find all assignments using this equipment
        assignments = ListFighterEquipmentAssignment.objects.filter(
            content_equipment=self, archived=False
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)

    class Meta:
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"
        unique_together = ["name", "category"]
        ordering = ["name"]

    def clean(self):
        self.name = self.name.strip()

    objects: ContentEquipmentManager = ContentEquipmentManager.from_queryset(
        ContentEquipmentQuerySet
    )()


class ContentEquipmentUpgradeQuerySet(ContentQuerySet):
    """
    Custom QuerySet for ContentEquipmentUpgrade. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter
    ) -> "ContentEquipmentUpgradeQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        from .equipment_list import ContentFighterEquipmentListUpgrade

        overrides = ContentFighterEquipmentListUpgrade.objects.filter(
            fighter=content_fighter,
            upgrade=OuterRef("pk"),
        )
        return self.annotate(
            cost_override=Subquery(
                overrides.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
        )


class ContentEquipmentUpgradeManager(ContentManager):
    """
    Custom manager for ContentEquipmentUpgrade model.
    """

    pass


class ContentEquipmentUpgrade(CostMixin, Content):
    """
    Represents an upgrade that can be associated with a piece of equipment.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="upgrades",
    )
    name = models.CharField(max_length=255)
    position = models.IntegerField(
        default=0,
        help_text="The position in which this upgrade sits in the stack, if applicable.",
    )
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the equipment upgrade. Costs are cumulative based on position.",
    )
    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the equipment or fighter's statline and traits.",
    )

    history = HistoricalRecords()

    def cost_int(self):
        """
        Returns the integer cost of this item.
        """
        # If the equipment is in multi-upgrade mode, return the cost directly.
        if self.equipment.upgrade_mode == ContentEquipment.UpgradeMode.MULTI:
            return self.cost

        # Otherwise, sum the costs of all upgrades up to this position.
        upgrades = self.equipment.upgrades.filter(position__lte=self.position)
        return sum(upgrade.cost for upgrade in upgrades)

    @cached_property
    def cost_int_cached(self):
        return self.cost_int()

    def cost_display(self, show_sign=False):
        """
        Returns a cost display string with '¢'.

        Always shows with '+' sign for equipment upgrades.
        """
        # If equipment is not set (e.g., unsaved object), use the cost directly
        if not hasattr(self, "equipment") or self.equipment_id is None:
            return format_cost_display(self.cost, show_sign=True)
        return format_cost_display(self.cost_int_cached, show_sign=True)

    class Meta:
        verbose_name = "Equipment Upgrade"
        verbose_name_plural = "Equipment Upgrades"
        ordering = ["equipment__name", "name"]
        unique_together = ["equipment", "name"]

    def __str__(self):
        return f"{self.equipment.upgrade_stack_name_display} – {self.name} ({self.equipment.name})"

    def set_dirty(self) -> None:
        """
        Mark all ListFighterEquipmentAssignments using this upgrade as dirty.

        Propagates to parent fighters and lists via their set_dirty() methods.
        Called when this upgrade's cost field changes.
        """
        # Lazy import to avoid circular dependency
        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find all assignments using this equipment upgrade (via M2M)
        assignments = ListFighterEquipmentAssignment.objects.filter(
            upgrades_field=self, archived=False
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)

    objects = ContentEquipmentUpgradeManager.from_queryset(
        ContentEquipmentUpgradeQuerySet
    )()


class ContentEquipmentFighterProfile(models.Model):
    """
    Links ContentEquipment to a ContentFighter for assigning Exotic Beasts and Vehicles.
    """

    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, verbose_name="Equipment"
    )
    content_fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        verbose_name="Fighter",
        help_text="This type of Fighter will be created when this Equipment is assigned",
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.content_fighter}"

    class Meta:
        verbose_name = "Equipment-Fighter Link"
        verbose_name_plural = "Equipment-Fighter Links"
        unique_together = ["equipment", "content_fighter"]


class ContentEquipmentEquipmentProfile(models.Model):
    """
    Links ContentEquipment to another ContentEquipment for auto-assigns.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        verbose_name="Equipment",
    )
    linked_equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        verbose_name="Auto-assigned Equipment",
        related_name="equip_equip_link_profiles",
        help_text="This Equipment will be auto-assigned when the main Equipment is assigned",
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.equipment} -> {self.linked_equipment}"

    def clean(self):
        """
        Validation to ensure that the linked equipment is not the same as the main equipment.
        """
        if self.equipment == self.linked_equipment:
            raise ValidationError(
                "The linked equipment cannot be the same as the main equipment."
            )

        if self.equipment.equip_equip_link_profiles.exists():
            raise ValidationError(
                "The linked equipment cannot itself be linked equipment."
            )

    class Meta:
        verbose_name = "Equipment-Equipment Link"
        verbose_name_plural = "Equipment-Equipment Links"
        unique_together = ["equipment", "linked_equipment"]
