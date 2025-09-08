"""
Models and utilities for managing fighter, equipment, rules, and related
content in Necromunda.

This module includes abstract base classes for shared data, plus concrete
models for fighters, equipment, rules, and more. Custom managers and querysets
provide streamlined data access.
"""

import logging
import math
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce, Lower
from django.utils.functional import cached_property
from multiselectfield import MultiSelectField
from polymorphic.models import PolymorphicModel
from simple_history.models import HistoricalRecords
from simpleeval import simple_eval

from gyrinx.core.models.base import AppBase
from gyrinx.models import (
    Base,
    CostMixin,
    FighterCategoryChoices,
    FighterCostMixin,
    QuerySetOf,
    equipment_category_group_choices,
    format_cost_display,
)

logger = logging.getLogger(__name__)

##
## Content Models
##


class Content(Base):
    """
    An abstract base model that captures common fields for all content-related
    models. Subclasses should inherit from this to store standard metadata.
    """

    class Meta:
        abstract = True


class ContentHouse(Content):
    """
    Represents a faction or house that fighters can belong to.
    """

    help_text = "The Content House identifies the house or faction of a fighter."
    name = models.CharField(max_length=255, db_index=True)
    skill_categories = models.ManyToManyField(
        "ContentSkillCategory",
        blank=True,
        related_name="houses",
        verbose_name="Unique Skill Categories",
    )
    generic = models.BooleanField(
        default=False,
        help_text="If checked, fighters in this House can join lists and gangs of any other House.",
    )
    legacy = models.BooleanField(
        default=False,
        help_text="If checked, this House is considered a legacy/older faction.",
    )
    can_hire_any = models.BooleanField(
        default=False,
        help_text="If checked, this House can hire any fighter from any house (except stash fighters).",
    )
    can_buy_any = models.BooleanField(
        default=False,
        help_text="If checked, this House can buy any equipment from any equipment list and trading post.",
    )

    history = HistoricalRecords()

    def fighters(self):
        """
        Returns all fighters associated with this house.
        """
        return self.contentfighter_set.all()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House"
        verbose_name_plural = "Houses"
        ordering = ["name"]


class ContentSkillCategory(Content):
    """
    Represents a category of skills that fighters may possess.
    """

    name = models.CharField(max_length=255, unique=True)
    restricted = models.BooleanField(
        default=False,
        help_text="If checked, this skill tree is only available to specific gangs.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Skill Tree"
        verbose_name_plural = "Skill Trees"
        ordering = ["name"]


class ContentSkill(Content):
    """
    Represents a skill that fighters may possess.
    """

    name = models.CharField(max_length=255, db_index=True)
    category = models.ForeignKey(
        ContentSkillCategory,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="skills",
        verbose_name="tree",
        db_index=True,
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"
        ordering = ["category", "name"]
        unique_together = ["name", "category"]


class ContentPsykerDiscipline(Content):
    """
    Represents a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255, unique=True)
    generic = models.BooleanField(
        default=False,
        help_text="If checked, this discipline can be used by any psyker.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Discipline"
        verbose_name_plural = "Psyker Disciplines"
        ordering = ["name"]


class ContentPsykerPower(Content):
    """
    Represents a specific power within a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255)
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="powers",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Power"
        verbose_name_plural = "Psyker Powers"
        ordering = ["discipline__name", "name"]
        unique_together = ["name", "discipline"]


class ContentFighterPsykerDisciplineAssignment(Content):
    """
    Represents a discipline assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="psyker_disciplines",
    )
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean(self):
        """
        Validation to ensure that a generic discipline cannot be assigned to a fighter.
        """
        # This is removed because fighters can *become* psykers later in the game, if a rule
        # is added via an updgrade or other means.
        # if not self.fighter.is_psyker:
        #     raise ValidationError(
        #         {
        #             "fighter": "Cannot assign a psyker discipline to a non-psyker fighter."
        #         }
        #     )

        if self.discipline.generic:
            raise ValidationError(
                {
                    "discipline": "Cannot assign a generic psyker discipline to a fighter."
                }
            )

    def __str__(self):
        return f"{self.fighter} {self.discipline}"

    class Meta:
        verbose_name = "Fighter Psyker Discipline"
        verbose_name_plural = "Fighter Psyker Disciplines"
        unique_together = ["fighter", "discipline"]
        ordering = ["fighter__type", "discipline__name"]


class ContentFighterPsykerPowerDefaultAssignment(Content):
    """
    Represents a default power assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="default_psyker_powers",
    )
    psyker_power = models.ForeignKey(
        ContentPsykerPower,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean_fields(self, exclude={}):
        """
        Validation to ensure that defaults cannot be assigned to a non-Psyker fighter.
        """
        if "fighter" not in exclude and not self.fighter.is_psyker:
            raise ValidationError(
                {"fighter": "Cannot assign a psyker power to a non-psyker fighter."}
            )

    def name(self):
        return f"{self.psyker_power.name} ({self.psyker_power.discipline})"

    def __str__(self):
        return f"{self.fighter} {self.psyker_power}"

    class Meta:
        verbose_name = "Psyker Fighter-Power Default Assignment"
        verbose_name_plural = "Psyker Fighter-Power Default Assignments"
        unique_together = ["fighter", "psyker_power"]
        ordering = ["fighter__type", "psyker_power__name"]


class ContentRule(Content):
    """
    Represents a specific rule from the game system.
    """

    name = models.CharField(max_length=255)

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"
        ordering = ["name"]


class ContentEquipmentCategory(Content):
    name = models.CharField(max_length=255, unique=True)
    group = models.CharField(max_length=255, choices=equipment_category_group_choices)
    restricted_to = models.ManyToManyField(
        ContentHouse,
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


class ContentEquipmentManager(models.Manager):
    """
    Custom manager for :model:`content.ContentEquipment` model, providing annotated
    default querysets (cost as integer, presence of weapon profiles, etc.).
    """

    def get_queryset(self):
        """
        Returns the default annotated queryset for equipment.
        """
        return (
            super()
            .get_queryset()
            .annotate(
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
            )
            .order_by("category__name", "name", "id")
        )


class ContentEquipmentQuerySet(models.QuerySet):
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

    def house_restricted(self, house: "ContentHouse") -> "ContentEquipmentQuerySet":
        return self.filter(Q(category__restricted_to=house))

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with fighter-specific cost overrides, if any.
        """
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
        self, content_fighter: "ContentFighter", rule_inputs
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with fighter-specific cost overrides,
        including those from equipment list expansions.
        """
        # Avoid circular import by importing models here
        from gyrinx.content.models_.expansion import (
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

    def with_profiles_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with weapon profiles for a given fighter, if any.
        """
        # contentweaponprofile_set.with_cost_for_fighter(content_fighter)
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
        self, content_fighter: "ContentFighter", rule_inputs
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with weapon profiles for a given fighter,
        including those from equipment list expansions.
        """
        from gyrinx.content.models_.expansion import (
            ContentEquipmentListExpansion,
            ContentEquipmentListExpansionItem,
        )

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

        return self.contentweaponprofile_set.with_cost_for_fighter(content_fighter)

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


class ContentFighterManager(models.Manager):
    """
    Custom manager for :model:`content.ContentFighter` model.
    """

    def without_stash(self):
        return (
            super()
            .get_queryset()
            .exclude(is_stash=True)
            .annotate(
                _category_order=Case(
                    *[
                        When(category=category, then=index)
                        for index, category in enumerate(
                            [
                                "LEADER",
                                "CHAMPION",
                                "PROSPECT",
                                "SPECIALIST",
                                "GANGER",
                                "JUVE",
                            ]
                        )
                    ],
                    # Gang Terrain always sorts last
                    When(category="GANG_TERRAIN", then=999),
                    # Other categories (including ALLY) sort in the middle, undefined
                    default=50,
                )
            )
            .order_by(
                "house__name",
                "_category_order",
                "type",
            )
        )

    def get_queryset(self):
        """
        Returns all fighters including stash fighters.
        """
        return (
            super()
            .get_queryset()
            .annotate(
                _category_order=Case(
                    *[
                        When(category=category, then=index)
                        for index, category in enumerate(
                            [
                                "STASH",
                                "LEADER",
                                "CHAMPION",
                                "PROSPECT",
                                "SPECIALIST",
                                "GANGER",
                                "JUVE",
                            ]
                        )
                    ],
                    # Gang Terrain always sorts last
                    When(category="GANG_TERRAIN", then=999),
                    # Other categories (including ALLY) sort in the middle, undefined
                    default=50,
                )
            )
            .order_by(
                "house__name",
                "_category_order",
                "type",
            )
        )


class ContentFighterQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentFighter`.
    """

    def available_for_house(
        self,
        house,
        include=[],
        exclude=[
            FighterCategoryChoices.EXOTIC_BEAST,
            FighterCategoryChoices.VEHICLE,
            FighterCategoryChoices.STASH,
        ],
    ):
        """
        Returns fighters available for a specific house.

        This includes:
        - Fighters for the house itself
        - Fighters from generic houses (excluding exotic beasts and stash)
        - All fighters if the house can_hire_any

        Args:
            house: ContentHouse instance
            include: List of fighter categories to include, which are removed from exclude
            exclude: List of fighter categories to exclude, defaults to exotic beasts, vehicles, and stash

        Returns:
            QuerySet of ContentFighter objects
        """
        from gyrinx.models import FighterCategoryChoices

        exclude = set(exclude) - set(include)

        # Check if the house can hire any fighter
        if house.can_hire_any:
            # Can hire any fighter except stash fighters
            return self.exclude(category=FighterCategoryChoices.STASH)
        else:
            # Normal filtering: only house and generic houses, exclude exotic beasts and stash
            generic_houses = ContentHouse.objects.filter(generic=True).values_list(
                "id", flat=True
            )
            return self.filter(
                house__in=[house.id] + list(generic_houses),
            ).exclude(category__in=exclude)


class ContentFighter(Content):
    """
    Represents a fighter or character archetype. Includes stats, base cost,
    and relationships to skills, rules, and a house/faction.
    """

    help_text = "The Content Fighter captures archetypal information about a fighter from the rulebooks."
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=FighterCategoryChoices)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )
    skills = models.ManyToManyField(
        ContentSkill, blank=True, verbose_name="Default Skills"
    )
    primary_skill_categories = models.ManyToManyField(
        ContentSkillCategory,
        blank=True,
        related_name="primary_fighters",
        verbose_name="Primary Skill Trees",
    )
    secondary_skill_categories = models.ManyToManyField(
        ContentSkillCategory,
        blank=True,
        related_name="secondary_fighters",
        verbose_name="Secondary Skill Trees",
    )
    rules = models.ManyToManyField(ContentRule, blank=True)
    base_cost = models.IntegerField(default=0)

    movement = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="M"
    )
    weapon_skill = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="WS"
    )
    ballistic_skill = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="BS"
    )
    strength = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="S"
    )
    toughness = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="T"
    )
    wounds = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="W"
    )
    initiative = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="I"
    )
    attacks = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="A"
    )
    leadership = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Ld"
    )
    cool = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Cl"
    )
    willpower = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Wil"
    )
    intelligence = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Int"
    )

    # Policy

    can_take_legacy = models.BooleanField(
        default=False,
        help_text="If checked, list fighters of this type can take on legacy content fighters.",
    )

    can_be_legacy = models.BooleanField(
        default=False,
        help_text="If checked, this fighter can be assigned as a legacy content fighter.",
    )

    is_stash = models.BooleanField(
        default=False,
        help_text="If checked, this fighter represents a gang's stash and should only show gear/weapons.",
    )

    hide_skills = models.BooleanField(
        default=False,
        help_text="If checked, skills section will not be displayed on fighter card.",
    )

    hide_house_restricted_gear = models.BooleanField(
        default=False,
        help_text="If checked, house restricted gear section will not be displayed on fighter card.",
    )

    # Other

    history = HistoricalRecords()

    def __str__(self):
        """
        Returns a string representation, including house and fighter category.
        """
        house = f"{self.house}" if self.house else ""
        return f"{house} {self.type} ({FighterCategoryChoices[self.category].label})".strip()

    def cat(self):
        """
        Returns the human-readable label of the fighter's category.
        """
        return FighterCategoryChoices[self.category].label

    def name(self):
        """
        Returns a composite name combining fighter type and category label.
        """
        return f"{self.type} ({self.cat()})"

    @cached_property
    def is_vehicle(self):
        """
        Indicates whether this fighter is a vehicle.
        """
        return self.category == FighterCategoryChoices.VEHICLE

    def cost(self):
        """
        Returns the cost of the fighter (base cost only, unless additional
        equipment costs are considered).
        """
        return self.base_cost

    def cost_int(self):
        """
        Returns the fighter's cost as an integer.
        """
        return int(self.cost())

    def cost_for_house(self, house):
        """
        Returns the cost of the fighter for a specific house, including
        any overrides.
        """
        cost_override = ContentFighterHouseOverride.objects.filter(
            fighter=self,
            house=house,
            cost__isnull=False,
        ).first()
        if cost_override:
            return cost_override.cost

        return self.cost_int()

    def statline(self, ignore_custom=False):
        """
        Returns a list of dictionaries describing the fighter's core stats,
        with additional styling indicators. Prefers custom statline if available.

        Performance: Note that this method is expensive and is entirely skipped if the statline is prefecthed
        by ListFighter with_related_data.
        """
        # Check for custom statline first
        if not ignore_custom and hasattr(self, "custom_statline"):
            statline = self.custom_statline
            stats = []
            # Get all stat values for this statline
            stat_values = {
                stat.statline_type_stat.field_name: stat.value
                for stat in statline.stats.select_related("statline_type_stat")
            }
            for stat_def in statline.statline_type.stats.all():
                value = stat_values.get(stat_def.field_name, "-")
                stats.append(
                    {
                        "field_name": stat_def.field_name,
                        "name": stat_def.short_name,
                        "value": value,
                        "highlight": stat_def.is_highlighted,
                        "first_of_group": stat_def.is_first_of_group,
                    }
                )
            return stats

        # Fall back to legacy hardcoded stats
        return self._legacy_statline()

    def _legacy_statline(self):
        """
        Returns the hardcoded statline for backward compatibility.
        """
        stats = [
            (f, self._meta.get_field(f))
            for f in [
                "movement",
                "weapon_skill",
                "ballistic_skill",
                "strength",
                "toughness",
                "wounds",
                "initiative",
                "attacks",
                "leadership",
                "cool",
                "willpower",
                "intelligence",
            ]
        ]
        return [
            {
                "field_name": f,
                "name": field.verbose_name,
                "value": getattr(self, field.name) or "-",
                "highlight": bool(
                    field.name in ["leadership", "cool", "willpower", "intelligence"]
                ),
                "first_of_group": field.name in ["leadership"],
            }
            for f, field in stats
        ]

    def ruleline(self) -> list[str]:
        """
        Returns a list of rule names associated with this fighter.
        """
        return [rule.name for rule in self.rules.all()]

    @cached_property
    def is_psyker(self):
        """
        Indicates whether this fighter is a psyker.
        """
        return (
            self.rules.annotate(name_lower=Lower("name"))
            .filter(
                name_lower__in=["psyker", "non-sanctioned psyker", "sanctioned psyker"]
            )
            .exists()
        )

    def copy_to_house(self, house):
        skills = self.skills.all()
        primary_skill_categories = self.primary_skill_categories.all()
        secondary_skill_categories = self.secondary_skill_categories.all()
        rules = self.rules.all()
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=self
        )
        equipment_list_weapon_accessories = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(fighter=self)
        )
        equipment_list_upgrades = ContentFighterEquipmentListUpgrade.objects.filter(
            fighter=self
        )
        default_assignments = ContentFighterDefaultAssignment.objects.filter(
            fighter=self
        )

        # Copy the fighter
        self.pk = None
        self.house = house
        self.save()
        fighter_id = self.pk

        self.skills.set(skills)
        self.primary_skill_categories.set(primary_skill_categories)
        self.secondary_skill_categories.set(secondary_skill_categories)
        self.rules.set(rules)

        for equipment in equipment_list_items:
            equipment.pk = None
            equipment.fighter_id = fighter_id
            equipment.save()

        for accessory in equipment_list_weapon_accessories:
            accessory.pk = None
            accessory.fighter_id = fighter_id
            accessory.save()

        for upgrade in equipment_list_upgrades:
            upgrade.pk = None
            upgrade.fighter_id = fighter_id
            upgrade.save()

        for assignment in default_assignments:
            weapon_profiles = assignment.weapon_profiles_field.all()
            weapon_accessories = assignment.weapon_accessories_field.all()

            assignment.pk = None
            assignment.fighter_id = fighter_id
            assignment.save()
            assignment.weapon_profiles_field.set(weapon_profiles)
            assignment.weapon_accessories_field.set(weapon_accessories)
            assignment.save()

        self.save()

        # self is now the new fighter
        return self

    def clean(self):
        """
        Validation to ensure stash fighters have 0 base cost.
        """
        if self.is_stash and self.base_cost != 0:
            raise ValidationError(
                {"base_cost": "Stash fighters must have a base cost of 0."}
            )

    class Meta:
        verbose_name = "Fighter"
        verbose_name_plural = "Fighters"

    objects: ContentFighterManager = ContentFighterManager.from_queryset(
        ContentFighterQuerySet
    )()


class ContentFighterCategoryTerms(Content):
    """
    Stores custom terminology for specific fighter types.
    Allows customization of language used for different fighter categories.
    """

    categories = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=False,
        help_text="Fighter categories that use these terms",
    )
    singular = models.CharField(
        max_length=255,
        default="Fighter",
        help_text="Singular form of fighter (e.g., 'Fighter', 'Vehicle')",
    )
    proximal_demonstrative = models.CharField(
        max_length=255,
        default="This fighter",
        help_text="How to refer to this fighter (e.g., 'This fighter', 'The stash', 'The vehicle')",
    )
    injury_singular = models.CharField(
        max_length=255,
        default="Injury",
        help_text="Singular form of injury (e.g., 'Injury', 'Damage', 'Glitch')",
    )
    injury_plural = models.CharField(
        max_length=255,
        default="Injuries",
        help_text="Plural form of injury (e.g., 'Injuries', 'Damage')",
    )
    recovery_singular = models.CharField(
        max_length=255,
        default="Recovery",
        help_text="Singular form of recovery (e.g., 'Recovery', 'Repair')",
    )

    history = HistoricalRecords()

    def __str__(self):
        categories_display = ", ".join(
            str(dict(FighterCategoryChoices.choices)[cat]) for cat in self.categories
        )
        return f"Terms for: {categories_display}"

    class Meta:
        verbose_name = "Fighter Category Terms"
        verbose_name_plural = "Fighter Category Terms"
        unique_together = ["categories"]


class ContentFighterEquipmentListItem(CostMixin, Content):
    """
    Associates :model:`content.ContentEquipment` with a given fighter in the rulebook, optionally
    specifying a weapon profile and cost override.
    """

    help_text = "Captures the equipment list available to a fighter in the rulebook."
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    weapon_profile = models.ForeignKey(
        "ContentWeaponProfile",
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=True,
        help_text="The weapon profile to use for this equipment list item.",
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        profile = f" ({self.weapon_profile})" if self.weapon_profile else ""
        return f"{self.fighter}: {self.equipment}{profile}"

    class Meta:
        verbose_name = "Equipment List Item"
        verbose_name_plural = "Equipment List Items"
        unique_together = ["fighter", "equipment", "weapon_profile"]
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        """
        Validation to ensure that the weapon profile matches the correct equipment.
        """
        if not self.equipment_id:
            raise ValidationError({"equipment": "Equipment must be specified."})

        if self.weapon_profile and self.weapon_profile.equipment != self.equipment:
            raise ValidationError(
                {"weapon_profile": "Weapon profile must match the equipment selected."}
            )


class ContentFighterEquipmentListWeaponAccessory(CostMixin, Content):
    """
    Associates :model:`content.ContentWeaponAccessory` with a given fighter in the rulebook, optionally
    specifying a cost override.
    """

    help_text = (
        "Captures the weapon accessories available to a fighter in the rulebook."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    weapon_accessory = models.ForeignKey(
        "ContentWeaponAccessory", on_delete=models.CASCADE, db_index=True
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.fighter} {self.weapon_accessory} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Weapon Accessory"
        verbose_name_plural = "Equipment List Weapon Accessories"
        unique_together = ["fighter", "weapon_accessory"]
        ordering = ["fighter__type", "weapon_accessory__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")


class ContentFighterEquipmentListUpgrade(CostMixin, Content):
    """
    Associates ContentEquipmentUpgrade with a given fighter in the rulebook,
    specifying a cost override.
    """

    help_text = (
        "Captures the equipment upgrades available to a fighter with cost overrides."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    upgrade = models.ForeignKey(
        "ContentEquipmentUpgrade", on_delete=models.CASCADE, db_index=True
    )
    cost = models.IntegerField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.fighter.type} {self.upgrade} ({self.cost})"

    class Meta:
        verbose_name = "Equipment List Upgrade"
        verbose_name_plural = "Equipment List Upgrades"
        unique_together = ["fighter", "upgrade"]
        ordering = ["fighter__type", "upgrade__equipment__name", "upgrade__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")


class ContentWeaponTrait(Content):
    """
    Represents a trait that can be associated with a weapon, such as 'Knockback'
    or 'Rapid Fire'.
    """

    name = models.CharField(max_length=255, unique=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Trait"
        verbose_name_plural = "Weapon Traits"
        ordering = ["name"]


class ContentEquipmentFighterProfile(models.Model):
    """
    Links ContentEquipment to a ContentFighter for assigning Exotic Beasts and Vehicles.
    """

    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, verbose_name="Equipment"
    )
    content_fighter = models.ForeignKey(
        ContentFighter,
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


class ContentWeaponProfileManager(models.Manager):
    """
    Custom manager for :model:`content.ContentWeaponProfile` model.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                _name_order=Case(
                    When(name="", then=0),
                    default=1,
                    output_field=models.IntegerField(),
                )
            )
            .order_by(
                "equipment__name",
                "_name_order",
                "name",
                "cost",
            )
        )


class ContentWeaponProfileQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponProfile`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        equipment_list_items = ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=OuterRef("equipment"),
            # This is critical to make sure we only annotate the cost of this profile.
            weapon_profile=OuterRef("pk"),
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_items.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
        )


@dataclass
class RulelineDisplay:
    value: str
    modded: bool = False


@dataclass
class StatlineDisplay:
    name: str
    field_name: str
    value: str
    classes: str = ""
    modded: bool = False
    highlight: bool = False


class ContentWeaponProfile(FighterCostMixin, Content):
    """
    Represents a specific profile for :model:`content.ContentEquipment`. "Standard" profiles have zero cost.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=False,
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Leave blank if the profile has no name (i.e. is the default statline). Don't include the hyphen for named profiles.",
    )
    help_text = "Captures the cost, rarity and statline for a weapon."

    # If the cost is zero, then the profile is free to use and "standard".
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the weapon profile at the Trading Post. If the cost is zero, "
        "then the profile is free to use and standard. This cost can be overridden by the "
        "fighter's equipment list.",
    )
    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this profile from the Trading Post.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    # Stat line
    range_short = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Rng S"
    )
    range_long = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Rng L"
    )
    accuracy_short = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Acc S"
    )
    accuracy_long = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Acc L"
    )
    strength = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Str"
    )
    armour_piercing = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Ap"
    )
    damage = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="D"
    )
    ammo = models.CharField(
        max_length=12, blank=True, null=False, default="", verbose_name="Am"
    )

    traits = models.ManyToManyField(
        ContentWeaponTrait,
        blank=True,
        db_index=True,  # Add index for better search performance
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.equipment} {self.name if self.name else '(Standard)'}"

    def cost_display(self, show_sign=False) -> str:
        """
        Returns a readable display for the cost, including any sign and '¢'.

        For weapon profiles:
        - Standard (unnamed) profiles always return empty string
        - Named profiles with zero cost return empty string
        - Named profiles with positive cost always show with '+' sign
        """
        if self.name == "" or self.cost_int() == 0:
            return ""
        # Always show sign for named profiles with non-zero cost
        return format_cost_display(self.cost_int(), show_sign=True)

    def statline(self) -> list[StatlineDisplay]:
        """
        Returns a list of dictionaries describing the weapon profile's stats,
        including range, accuracy, strength, and so forth.
        """
        stats = [
            self._meta.get_field(field)
            for field in [
                "range_short",
                "range_long",
                "accuracy_short",
                "accuracy_long",
                "strength",
                "armour_piercing",
                "damage",
                "ammo",
            ]
        ]
        return [
            StatlineDisplay(
                **{
                    "name": field.verbose_name,
                    "field_name": field.name,
                    "classes": (
                        "border-start"
                        if field.name in ["accuracy_short", "strength"]
                        else ""
                    ),
                    "value": getattr(self, field.name) or "-",
                }
            )
            for field in stats
        ]

    def traitline(self):
        """
        Returns a list of weapon trait names associated with this profile.
        """
        return [trait.name for trait in self.traits.all()]

    @cached_property
    def traitline_cached(self):
        return self.traitline()

    class Meta:
        verbose_name = "Weapon Profile"
        verbose_name_plural = "Weapon Profiles"
        unique_together = ["equipment", "name"]

    def clean(self):
        """
        Validation to ensure appropriate costs and cost signs for standard
        vs non-standard weapon profiles.
        """
        self.name = self.name.strip()

        if self.name.startswith("-"):
            raise ValidationError("Name should not start with a hyphen.")

        if self.name == "(Standard)":
            raise ValidationError('Name should not be "(Standard)".')

        # Ensure that specific fields are not hyphens
        for pf in [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]:
            setattr(self, pf, getattr(self, pf).strip())
            value = getattr(self, pf)
            if value == "-":
                setattr(self, pf, "")

            if pf in [
                "range_short",
                "range_long",
            ]:
                if value and value[0].isdigit() and not value.endswith('"'):
                    setattr(self, pf, f'{value}"')

        if self.cost_int() < 0:
            raise ValidationError({"cost": "Cost cannot be negative."})

        if self.name == "" and self.cost_int() != 0:
            raise ValidationError(
                {
                    "cost": "Standard (un-named) profiles should have zero cost.",
                }
            )

    objects = ContentWeaponProfileManager.from_queryset(ContentWeaponProfileQuerySet)()


class ContentWeaponAccessoryManager(models.Manager):
    """
    Custom manager for :model:`content.ContentWeaponAccessory` model. Currently unused but available
    for future extensions.
    """

    pass


class ContentWeaponAccessoryQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponAccessory`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentWeaponAccessoryQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        equipment_list_entries = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(
                fighter=content_fighter,
                weapon_accessory=OuterRef("pk"),
            )
        )
        return self.annotate(
            cost_override=Subquery(
                equipment_list_entries.values("cost")[:1],
                output_field=models.IntegerField(),
            ),
            cost_for_fighter=Coalesce("cost_override", "cost"),
        )


class ContentWeaponAccessory(FighterCostMixin, Content):
    """
    Represents an accessory that can be associated with a weapon.
    """

    name = models.CharField(max_length=255, unique=True)
    cost = models.IntegerField(
        default=0,
        help_text="The credit cost of the weapon accessory at the Trading Post. This cost can be "
        "overridden by the fighter's equipment list.",
    )
    cost_expression = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional cost calculation expression. If provided, this will be used instead of the base cost. "
        "Available variables: cost_int (the base cost of the weapon). "
        "Available functions: min(), max(), round(), ceil(), floor(). "
        "Example: 'ceil(cost_int * 0.25 / 5) * 5' for 25% of cost rounded up to nearest 5.",
    )
    rarity = models.CharField(
        max_length=1,
        choices=[
            ("R", "Rare (R)"),
            ("I", "Illegal (I)"),
            ("E", "Exclusive (E)"),
            ("C", "Common (C)"),
        ],
        blank=True,
        default="C",
        help_text="Use 'E' to exclude this profile from the Trading Post.",
        verbose_name="Availability",
    )
    rarity_roll = models.IntegerField(
        blank=True, null=True, verbose_name="Availability Level"
    )

    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers to apply to the weapon's statline and traits.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def calculate_cost_for_weapon(self, weapon_base_cost: int) -> int:
        """Calculate the cost of this accessory for a given weapon base cost."""
        if not self.cost_expression:
            return self.cost

        # Define available functions
        functions = {
            "round": round,
            "ceil": math.ceil,
            "floor": math.floor,
            "min": min,
            "max": max,
        }

        # Define available names (variables)
        names = {
            "cost_int": weapon_base_cost,
        }

        try:
            result = simple_eval(self.cost_expression, functions=functions, names=names)
            # Ensure result is an integer
            return int(result)
        except Exception:
            # If evaluation fails, fall back to base cost
            logger.exception(
                "Failed to evaluate cost expression for weapon accessory %s",
                self.name,
            )
            return self.cost

    class Meta:
        verbose_name = "Weapon Accessory"
        verbose_name_plural = "Weapon Accessories"
        ordering = ["name"]

    objects = ContentWeaponAccessoryManager.from_queryset(
        ContentWeaponAccessoryQuerySet
    )()


class ContentEquipmentUpgradeQuerySet(models.QuerySet):
    """
    Custom QuerySet for ContentEquipmentUpgrade. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter: "ContentFighter"
    ) -> "ContentEquipmentUpgradeQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
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


class ContentEquipmentUpgradeManager(models.Manager):
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
        return f"{self.equipment.upgrade_stack_name_display} – {self.name}"

    objects = ContentEquipmentUpgradeManager.from_queryset(
        ContentEquipmentUpgradeQuerySet
    )()


class ContentFighterDefaultAssignment(CostMixin, Content):
    """
    Associates a fighter with a piece of equipment by default, including weapon profiles.
    """

    help_text = "Captures the default equipment assignments for a fighter."
    fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="default_assignments",
    )
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    weapon_profiles_field = models.ManyToManyField(
        ContentWeaponProfile,
        blank=True,
    )
    weapon_accessories_field = models.ManyToManyField(
        ContentWeaponAccessory,
        blank=True,
    )
    cost = models.IntegerField(
        default=0, help_text="You typically should not overwrite this."
    )
    history = HistoricalRecords()

    def is_weapon(self):
        return self.equipment.is_weapon()

    def all_profiles(self):
        """Return all profiles for the equipment, including the default profiles."""
        standard_profiles = self.standard_profiles_cached
        weapon_profiles = self.weapon_profiles_cached

        seen = set()
        result = []
        for p in standard_profiles + weapon_profiles:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result

    def standard_profiles(self):
        # Performance: this is better in Python because it avoids additional database queries when
        # prefetched.
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in self.equipment.contentweaponprofile_set.all()
            if p.cost == 0
        ]

    @cached_property
    def standard_profiles_cached(self):
        return list(self.standard_profiles())

    def weapon_profiles(self):
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in self.weapon_profiles_field.all()
        ]

    @cached_property
    def weapon_profiles_cached(self):
        return list(self.weapon_profiles())

    # Accessories

    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    @cached_property
    def weapon_accessories_cached(self):
        return self.weapon_accessories()

    # Mods

    @cached_property
    def _mods(self):
        accessories = self.weapon_accessories_cached
        mods = [m for a in accessories for m in a.modifiers.all()]
        return mods

    # Behaviour

    def __str__(self):
        return f"{self.fighter} – {self.name()}"

    def name(self):
        profiles_names = ", ".join(
            [profile.name for profile in self.weapon_profiles_cached]
        )
        return f"{self.equipment}" + (f" ({profiles_names})" if profiles_names else "")

    class Meta:
        verbose_name = "Default Equipment Assignment"
        verbose_name_plural = "Default Equipment Assignments"
        ordering = ["fighter__type", "equipment__name"]

    def clean(self):
        """
        Validation to ensure cost is not negative and that any weapon profiles
        are associated with the correct equipment.
        """
        if self.cost_int() < 0:
            raise ValidationError("Cost cannot be negative.")

        for profile in self.weapon_profiles_field.all():
            if profile.equipment != self.equipment:
                raise ValidationError("Weapon profiles must be for the same equipment.")


class ContentFighterHouseOverride(Content):
    """
    Captures cases where a fighter has specific modifications (i.e. cost) when being added to
    a specific house.
    """

    fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="house_overrides",
    )
    house = models.ForeignKey(
        ContentHouse,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="fighter_overrides",
    )
    cost = models.IntegerField(
        null=True,
        blank=True,
        help_text="What should this Fighter cost when added to this House?",
    )

    class Meta:
        verbose_name = "Fighter-House Override"
        verbose_name_plural = "Fighter-House Overrides"
        ordering = ["house__name", "fighter__type"]
        unique_together = ["fighter", "house"]

    def __str__(self):
        return f"{self.fighter} for {self.house}"


def check(rule, category, name):
    """
    Check if the rule applies to the given category and name.
    A rule matches if its 'category' and 'name' entries are either
    None or match the input.
    """
    dc = rule.get("category") in [None, category]
    dn = rule.get("name") in [None, name]
    return dc and dn


class ContentPolicy(Content):
    """
    Captures rules for restricting or allowing certain equipment to fighters.
    """

    help_text = (
        "Not used currently. Captures the rules for equipment availability to fighters."
    )
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    rules = models.JSONField()
    history = HistoricalRecords()

    def allows(self, equipment: ContentEquipment) -> bool:
        """
        Determines if the equipment is allowed by the policy. This is evaluated
        by checking rules from last to first.
        """
        name = equipment.name
        # TODO: This won't work — this model should be dropped for now as it's not used
        #       and is deadwood.
        category = equipment.category.name
        # Work through the rules in reverse order. If any of them
        # allow, then the equipment is allowed.
        # If we get to an explicit deny, then the equipment is denied.
        # If we get to the end, then the equipment is allowed.
        for rule in reversed(self.rules):
            deny = rule.get("deny", [])
            if deny == "all":
                return False
            # The deny rule is an AND rule. The category and name must
            # both match, or be missing, for the rule to apply.
            deny_fail = any([check(d, category, name) for d in deny])
            if deny_fail:
                return False

            allow = rule.get("allow", [])
            if allow == "all":
                return True
            # The allow rule is an AND rule. The category and name must
            # both match, or be missing, for the allow to apply.
            allow_pass = any([check(a, category, name) for a in allow])
            if allow_pass:
                return True

        return True

    class Meta:
        verbose_name = "Policy"
        verbose_name_plural = "Policies"


class ContentBook(Content):
    """
    Represents a rulebook, including its name, shortname, year of publication,
    and whether it is obsolete.
    """

    help_text = "Captures rulebook information."
    name = models.CharField(max_length=255)
    shortname = models.CharField(max_length=50, blank=True, null=False)
    year = models.CharField(blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    type = models.CharField(max_length=50, blank=True, null=False)
    obsolete = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name} ({self.type}, {self.year})"

    class Meta:
        verbose_name = "Book"
        verbose_name_plural = "Books"
        ordering = ["name"]


class ContentPack(AppBase):
    """
    Represents a collection of custom content that can be shared between
    players and campaign arbitrators. Content packs allow users to create
    and organize their own houses, fighters, weapons, and other game entities.
    """

    help_text = "A user-created collection of game content."
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    color = models.CharField(
        max_length=7, default="#000000", help_text="Hex color code for UI theming"
    )
    is_public = models.BooleanField(
        default=False, help_text="Whether this content pack is publicly visible"
    )

    # ManyToMany relationships to content models
    houses = models.ManyToManyField(
        ContentHouse, blank=True, related_name="content_packs"
    )
    skill_categories = models.ManyToManyField(
        ContentSkillCategory, blank=True, related_name="content_packs"
    )
    rules = models.ManyToManyField(
        ContentRule, blank=True, related_name="content_packs"
    )
    fighters = models.ManyToManyField(
        ContentFighter, blank=True, related_name="content_packs"
    )
    weapon_traits = models.ManyToManyField(
        ContentWeaponTrait, blank=True, related_name="content_packs"
    )
    equipment = models.ManyToManyField(
        ContentEquipment, blank=True, related_name="content_packs"
    )
    weapon_profiles = models.ManyToManyField(
        ContentWeaponProfile, blank=True, related_name="content_packs"
    )
    weapon_accessories = models.ManyToManyField(
        ContentWeaponAccessory, blank=True, related_name="content_packs"
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Content Pack"
        verbose_name_plural = "Content Packs"
        ordering = ["name"]


class ContentAttribute(Content):
    """
    Represents an attribute that can be associated with gangs/lists
    (e.g., Alignment, Alliance, Affiliation).
    """

    help_text = "Defines attributes that can be associated with gangs, such as Alignment, Alliance, or Affiliation."
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="The name of the attribute (e.g., 'Alignment', 'Alliance', 'Affiliation').",
    )
    is_single_select = models.BooleanField(
        default=True,
        help_text="If True, only one value can be selected. If False, multiple values can be selected.",
    )
    restricted_to = models.ManyToManyField(
        ContentHouse,
        blank=True,
        related_name="restricted_attributes",
        verbose_name="Restricted To",
        help_text="If provided, this attribute is only available to specific gang houses.",
    )

    history = HistoricalRecords()

    def __str__(self):
        select_type = "single-select" if self.is_single_select else "multi-select"
        return f"{self.name} ({select_type})"

    class Meta:
        verbose_name = "Gang Attribute"
        verbose_name_plural = "Gang Attributes"
        ordering = ["name"]


class ContentAttributeValue(Content):
    """
    Represents allowed values for a ContentAttribute.
    """

    help_text = "Defines the allowed values for a gang attribute."
    attribute = models.ForeignKey(
        ContentAttribute,
        on_delete=models.CASCADE,
        related_name="values",
        help_text="The attribute this value belongs to.",
    )
    name = models.CharField(
        max_length=255,
        help_text="The value name (e.g., 'Law Abiding', 'Outlaw', 'Chaos Cult').",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description of what this value represents.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Gang Attribute Value"
        verbose_name_plural = "Gang Attribute Values"
        ordering = ["attribute__name", "name"]
        unique_together = [["attribute", "name"]]


def similar(a, b):
    """
    Returns a similarity ratio between two strings, ignoring case.
    If one is contained in the other, returns 0.9 for partial matches,
    or 1.0 if they are identical.
    """
    lower_a = a.lower()
    lower_b = b.lower()
    if lower_a == lower_b:
        return 1.0
    if lower_a in lower_b or lower_b in lower_a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


class ContentPageRef(Content):
    """
    Represents a reference to a page (or pages) in a rulebook (:model:`content.ContentBook`). Provides a parent
    relationship for nested references, used to resolve page numbers.
    """

    help_text = "Captures the page references for game content. Title is used to match with other entities (e.g. Skills)."
    book = models.ForeignKey(ContentBook, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    page = models.CharField(max_length=50, blank=True, null=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    category = models.CharField(max_length=255, blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.book.shortname} - {self.category} - p{self.resolve_page_cached} - {self.title}".strip()

    def bookref(self):
        """
        Returns a short, human-readable reference string combining the
        book shortname and resolved page number.
        """
        return f"{self.book.shortname} p{self.resolve_page_cached}".strip()

    def resolve_page(self):
        """
        If the page field is empty, attempts to resolve the page
        through its parent. Returns None if no page can be resolved.
        """
        if self.page:
            return self.page

        if self.parent:
            return self.parent.resolve_page_cached

        return None

    @cached_property
    def resolve_page_cached(self):
        return self.resolve_page()

    class Meta:
        verbose_name = "Page Reference"
        verbose_name_plural = "Page References"
        ordering = ["category", "book__name", "title"]

    # TODO: Move this to a custom Manager
    @classmethod
    def find(cls, *args, **kwargs):
        """
        Finds a single page reference matching the given query parameters.
        Returns the first match or None if no match is found.
        """
        return ContentPageRef.objects.filter(*args, **kwargs).first()

    # TODO: Move this to a custom Manager
    @classmethod
    def find_similar(cls, title: str, **kwargs):
        """
        Finds references whose titles match or are similar to the given string.
        Uses caching to avoid repeated lookups. Returns a QuerySet.
        """
        cache = caches["content_page_ref_cache"]
        key = f"content_page_ref_cache:{title}"
        cached = cache.get(key)
        if cached:
            return cached

        refs = ContentPageRef.objects.filter(**kwargs).filter(
            Q(title__icontains=title) | Q(title=title)
        )
        cache.set(key, refs)
        return refs

    # TODO: Move this to a custom Manager
    @classmethod
    def all_ordered(cls):
        """
        Returns top-level page references (no parent) with numeric pages, ordered by:
        - Core book first
        - Then by book shortname
        - Then ascending by numeric page
        """
        return (
            # TODO: Implement this as a method on the Manager/QuerySet
            ContentPageRef.objects.filter(parent__isnull=True)
            .exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
            )
        )

    # TODO: Add default ordering to the Meta class, possibly with default annotations from the Manager
    def children_ordered(self):
        """
        Returns any child references of this reference that have a page specified,
        ordered similarly (Core first, then shortname, then ascending page, then title).
        """
        return (
            self.children.exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
                "title",
            )
        )

    def children_no_page(self):
        """
        Returns any child references of this reference that do not have a page
        specified, ordered similarly (Core first, then shortname, then title).
        """
        return self.children.filter(page="").order_by(
            Case(
                When(book__shortname="Core", then=0),
                default=99,
            ),
            "book__shortname",
            "title",
        )


class ContentMod(PolymorphicModel, Content):
    """
    Base class for all modifications.
    """

    help_text = "Base class for all modifications."
    history = HistoricalRecords()

    def __str__(self):
        return "Base Modification"

    class Meta:
        verbose_name = "Modification"
        verbose_name_plural = "Modifications"


class ContentModStatApplyMixin:
    inverted_stats = [
        "ammo",
        "armour_piercing",
        "weapon_skill",
        "ballistic_skill",
        "intelligence",
        "leadership",
        "cool",
        "willpower",
        "initiative",
        "handling",
        "save",
    ]

    inch_stats = ["range_short", "range_long", "movement"]

    modifier_stats = ["accuracy_short", "accuracy_long", "armour_piercing"]

    target_roll_stats = [
        "ammo",
        "weapon_skill",
        "ballistic_skill",
        "intelligence",
        "leadership",
        "cool",
        "willpower",
        "initiative",
        "handling",
        "save",
    ]

    def apply(self, input_value: str) -> str:
        """
        Apply the modification to a given value.
        """

        if self.mode == "set":
            return self.value

        direction = 1 if self.mode == "improve" else -1
        # For some stats, we need to reverse the direction
        # e.g. if the stat is a target roll value
        if self.stat in self.inverted_stats:
            direction = -direction

        # Stats can be:
        #   - (meaning 0)
        #   X" (meaning X inches) — Rng
        #   X (meaning X) — Str, D
        #   S (meaning fighter Str) — Str
        #   S+X (meaning fighter Str+X) — Str
        #   +X (meaning add X to roll) — Acc and Ap
        #   X+ (meaning target X on roll) — Am
        current_value = input_value.strip()
        join = None
        # A developer has a problem. She uses a regex... Now she has two problems.
        if current_value in ["-", ""]:
            current_value = 0
        elif current_value.endswith('"'):
            # Inches
            current_value = int(current_value[:-1])
        elif current_value.endswith("+"):
            # Target roll
            current_value = int(current_value[:-1])
        elif current_value.startswith("+"):
            # Modifier
            current_value = int(current_value[1:])
        elif current_value == "S":
            # Stat-linked: e.g. S
            current_value = 0
            join = ["S"]
        elif "+" in current_value:
            # Stat-linked: e.g. S+1
            split = current_value.split("+")
            join = split[:-1]
            current_value = int(split[-1])
        elif "-" in current_value:
            # Stat-linked: e.g. S-1
            split = current_value.split("-")
            join = split[:-1]
            # Note! Negative
            current_value = -int(split[-1])
        else:
            current_value = int(current_value)

        # TODO: We should validate that the value is number in improve/worsen mode
        mod_value = int(self.value.strip()) * direction
        output_value = current_value + mod_value
        output_str = str(output_value)

        if join:
            # Stat-linked: e.g. S+1
            # The else case handles negative case
            if output_str == "0":
                return f"{''.join(join)}"
            sign = "+" if output_value > 0 else ""
            return f"{''.join(join)}{sign}{output_value}"
        elif output_str == "0":
            return ""
        elif self.stat in self.inch_stats:
            # Inches
            return f'{output_str}"'
        elif self.stat in self.modifier_stats:
            # Modifier
            if mod_value > 0:
                return f"+{output_str}"
            return f"{output_str}"
        elif self.stat in self.target_roll_stats:
            # Target roll
            return f"{output_str}+"

        return output_str


class ContentModStat(ContentMod, ContentModStatApplyMixin):
    """
    Weapon stat modifier
    """

    help_text = "A modification to a specific value in a weapon statline"
    stat = models.CharField(
        max_length=50,
        choices=[
            ("strength", "Strength"),
            ("range_short", "Range (Short)"),
            ("range_long", "Range (Long)"),
            ("accuracy_short", "Accuracy (Short)"),
            ("accuracy_long", "Accuracy (Long)"),
            ("armour_piercing", "Armour Piercing"),
            ("damage", "Damage"),
            ("ammo", "Ammo"),
        ],
    )
    mode = models.CharField(
        max_length=10,
        choices=[("improve", "Improve"), ("worsen", "Worsen"), ("set", "Set")],
    )
    value = models.CharField(max_length=5)

    def __str__(self):
        mode_choices = dict(self._meta.get_field("mode").choices)
        stat_choices = dict(self._meta.get_field("stat").choices)
        return f"{mode_choices[self.mode]} weapon {stat_choices[self.stat]} by {self.value}"

    class Meta:
        verbose_name = "Weapon Stat Modifier"
        verbose_name_plural = "Weapon Stat Modifiers"
        ordering = ["stat"]


class ContentModFighterStat(ContentMod, ContentModStatApplyMixin):
    """
    Fighter stat modifier.

    Note: The choices for the `stat` field are auto-generated dynamically in the admin form
    from ContentStat objects to ensure consistency across the system.
    """

    help_text = "A modification to a specific value in a fighter statline"
    stat = models.CharField(
        max_length=50,
        # Choices are dynamically generated in ContentModFighterStatAdminForm
        # from ContentStat objects to ensure all defined stats are available
    )
    mode = models.CharField(
        max_length=10,
        choices=[("improve", "Improve"), ("worsen", "Worsen"), ("set", "Set")],
    )
    value = models.CharField(max_length=5)

    def __str__(self):
        mode_choices = dict(self._meta.get_field("mode").choices)
        return f"{mode_choices[self.mode]} fighter {self.stat} by {self.value}"

    class Meta:
        verbose_name = "Fighter Stat Modifier"
        verbose_name_plural = "Fighter Stat Modifiers"
        ordering = ["stat"]

    def clean(self):
        # Check that there isn't a duplicate of this already
        duplicate = ContentModFighterStat.objects.filter(
            stat=self.stat, mode=self.mode, value=self.value
        ).exists()

        if duplicate:
            raise ValidationError("This fighter stat modifier already exists.")


class ContentModTrait(ContentMod):
    """
    Trait modifier
    """

    help_text = "A modification to a weapon trait"
    trait = models.ForeignKey(
        ContentWeaponTrait,
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} {self.trait}"

    class Meta:
        verbose_name = "Weapon Trait Modifier"
        verbose_name_plural = "Weapon Trait Modifiers"
        ordering = ["trait__name", "mode"]


class ContentModFighterRule(ContentMod):
    """
    Rule modifier
    """

    help_text = "A modification to a fighter rule"
    rule = models.ForeignKey(
        ContentRule,
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} rule {self.rule}"

    class Meta:
        verbose_name = "Fighter Rule Modifier"
        verbose_name_plural = "Fighter Rule Modifiers"
        ordering = ["rule__name", "mode"]


class ContentModFighterSkill(ContentMod):
    """
    Skill modifier
    """

    help_text = "A modification to a fighter skills"
    skill = models.ForeignKey(
        ContentSkill,
        on_delete=models.CASCADE,
        related_name="modified_by",
        null=False,
        blank=False,
    )
    mode = models.CharField(
        max_length=255,
        choices=[("add", "Add"), ("remove", "Remove")],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} skill {self.skill}"

    class Meta:
        verbose_name = "Fighter Skill Modifier"
        verbose_name_plural = "Fighter Skill Modifiers"
        ordering = ["skill__name", "mode"]


class ContentModSkillTreeAccess(ContentMod):
    """
    Modifies fighter skill tree access (primary/secondary)
    """

    help_text = "A modification to fighter skill tree access"

    skill_category = models.ForeignKey(
        ContentSkillCategory,
        on_delete=models.CASCADE,
        related_name="modified_by_skill_tree_access",
        null=False,
        blank=False,
    )

    mode = models.CharField(
        max_length=20,
        choices=[
            ("add_primary", "Add as Primary"),
            ("add_secondary", "Add as Secondary"),
            ("remove_primary", "Remove from Primary"),
            ("remove_secondary", "Remove from Secondary"),
            ("disable", "Disable Access"),
        ],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} - {self.skill_category}"

    class Meta:
        verbose_name = "Skill Tree Access Modifier"
        verbose_name_plural = "Skill Tree Access Modifiers"
        ordering = ["skill_category__name", "mode"]


class ContentModPsykerDisciplineAccess(ContentMod):
    """
    Modifies fighter psyker discipline access.
    Allows adding or removing psyker discipline access to fighters.
    """

    help_text = "A modification to fighter psyker discipline access"

    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="modified_by_psyker_discipline_access",
        null=False,
        blank=False,
    )

    mode = models.CharField(
        max_length=20,
        choices=[
            ("add", "Add Discipline"),
            ("remove", "Remove Discipline"),
        ],
    )

    def __str__(self):
        choices = dict(self._meta.get_field("mode").choices)
        return f"{choices[self.mode]} - {self.discipline}"

    class Meta:
        verbose_name = "Psyker Discipline Access Modifier"
        verbose_name_plural = "Psyker Discipline Access Modifiers"
        ordering = ["discipline__name", "mode"]


@dataclass
class VirtualWeaponProfile:
    """
    A virtual container for profiles that applies mods.
    """

    profile: ContentWeaponProfile
    mods: list[ContentMod] = field(default_factory=list)

    @property
    def id(self):
        return self.profile.id

    @property
    def name(self):
        return self.profile.name

    def cost_int(self):
        return self.profile.cost_int()

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def _statmods(self, stat=None) -> list[ContentModStat]:
        return [
            mod
            for mod in self.mods
            if isinstance(mod, ContentModStat) and (stat is None or mod.stat == stat)
        ]

    def _traitmods(self) -> list[ContentModTrait]:
        return [mod for mod in self.mods if isinstance(mod, ContentModTrait)]

    def __post_init__(self):
        stats = [
            "range_short",
            "range_long",
            "accuracy_short",
            "accuracy_long",
            "strength",
            "armour_piercing",
            "damage",
            "ammo",
        ]
        for stat in stats:
            value = self.profile.__getattribute__(stat)
            setattr(
                self,
                stat,
                self._apply_mods(stat, value, self._statmods(stat=stat)),
            )

    def _apply_mods(self, stat: str, value: str, mods: list[ContentModStat]):
        for mod in mods:
            value = mod.apply(value)
        return value

    @property
    def traits(self):
        mods = self._traitmods()
        value = list(self.profile.traits.all())
        for mod in mods:
            if mod.mode == "add" and mod.trait not in value:
                value.append(mod.trait)
            elif mod.mode == "remove" and mod.trait in value:
                value.remove(mod.trait)
        return value

    def statline(self):
        statline = self.profile.statline()
        output = []
        for stat in statline:
            base_value = stat.value
            value = getattr(self, stat.field_name) or "-"
            if value != base_value:
                stat = replace(stat, value=value, modded=True)
            output.append(stat)
        return output

    def traitline(self):
        # TODO: We need some kind of TraitDisplay thing
        # Get original traits from the profile
        original_traits = list(self.profile.traits.all())

        # Get the final trait list after modifications
        final_traits = self.traits

        # Separate traits into original (that weren't removed) and mod-added
        original_trait_names = [
            trait.name for trait in final_traits if trait in original_traits
        ]
        mod_added_trait_names = sorted(
            [trait.name for trait in final_traits if trait not in original_traits]
        )

        # Return original traits first, then mod-added traits
        return original_trait_names + mod_added_trait_names

    @cached_property
    def traitline_cached(self):
        return self.traitline()

    @cached_property
    def rarity(self):
        return self.profile.rarity

    @cached_property
    def rarity_roll(self):
        return self.profile.rarity_roll

    def __str__(self):
        return self.name()

    def __eq__(self, value):
        return self.profile == value


class ContentInjuryDefaultOutcome(models.TextChoices):
    """Default fighter state outcomes when injuries are applied"""

    NO_CHANGE = "no_change", "No Change"
    ACTIVE = "active", "Active"
    RECOVERY = "recovery", "Recovery"
    CONVALESCENCE = "convalescence", "Convalescence"
    DEAD = "dead", "Dead"
    IN_REPAIR = "in_repair", "In Repair"


class ContentInjuryGroup(Content):
    """
    Represents a group of injuries that can be applied to specific fighter categories.
    """

    help_text = (
        "Groups injuries and specifies which fighter categories can receive them."
    )
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    restricted_to = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text="If set, only these fighter categories can receive injuries from this group.",
    )
    unavailable_to = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text="If set, these fighter categories cannot receive injuries from this group.",
    )
    restricted_to_house = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        help_text="If set, only these houses can use injuries from this group.",
        related_name="injury_groups",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Injury Group"
        verbose_name_plural = "Injury Groups"
        ordering = ["name"]


class ContentInjury(Content):
    """
    Named injuries that can be applied to fighters during campaigns.
    """

    help_text = "Represents a lasting injury that can be suffered by a fighter during campaign play."
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    phase = models.CharField(
        max_length=20,
        choices=ContentInjuryDefaultOutcome.choices,
        default=ContentInjuryDefaultOutcome.NO_CHANGE,
        help_text="The default fighter state outcome when this injury is applied.",
        verbose_name="Default Outcome",
    )
    injury_group = models.ForeignKey(
        ContentInjuryGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The injury group this injury belongs to.",
        related_name="injuries",
    )
    # Temporary: keep the old group field for migration purposes
    group = models.CharField(
        max_length=100,
        blank=True,
        help_text="(Deprecated) Text-based grouping for organizing injuries.",
    )
    modifiers = models.ManyToManyField(
        ContentMod,
        blank=True,
        help_text="Modifiers applied when this injury is active.",
        related_name="injuries",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Injury"
        verbose_name_plural = "Injuries"
        ordering = ["injury_group__name", "name"]


##
## Statline Models for flexible stat systems (e.g., vehicles)
##


class ContentStat(Content):
    """
    Represents a single stat definition that can be used across multiple
    statline types. This avoids duplication of stat definitions.
    """

    help_text = "A stat definition that can be shared across different statline types."
    field_name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal field name (e.g., 'movement', 'front_toughness')",
    )
    short_name = models.CharField(
        max_length=10, help_text="Short display name (e.g., 'M', 'Fr')"
    )
    full_name = models.CharField(
        max_length=50,
        help_text="Full display name (e.g., 'Movement', 'Front Toughness')",
    )

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Auto-generate field_name from full_name on first save
        if not self.field_name and self.full_name:
            import re

            # Convert to lowercase and replace non-alphanumeric with underscores
            field_name = re.sub(r"[^a-z0-9]+", "_", self.full_name.lower())
            # Remove leading/trailing underscores
            field_name = field_name.strip("_")
            # Replace multiple underscores with single
            field_name = re.sub(r"_+", "_", field_name)
            self.field_name = field_name

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.short_name} ({self.full_name})"

    class Meta:
        verbose_name = "Stat"
        verbose_name_plural = "Stats"
        ordering = ["full_name"]


class ContentStatlineType(Content):
    """
    Defines a type of statline (e.g., 'Fighter', 'Vehicle') that can have
    different sets of statistics.
    """

    help_text = "Represents a type of statline with its own set of stats (e.g., Fighter, Vehicle)."
    name = models.CharField(max_length=255, unique=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Statline Type"
        verbose_name_plural = "Statline Types"
        ordering = ["name"]


class ContentStatlineTypeStat(Content):
    """
    Links a stat to a statline type with display properties.
    This allows the same stat to be used across multiple statline types
    with different positions and display settings.
    """

    help_text = "Links a stat definition to a statline type with positioning and display settings."
    statline_type = models.ForeignKey(
        ContentStatlineType, on_delete=models.CASCADE, related_name="stats"
    )
    stat = models.ForeignKey(
        ContentStat, on_delete=models.CASCADE, related_name="statline_type_stats"
    )
    position = models.IntegerField(
        help_text="Display order position (lower numbers appear first)"
    )
    is_highlighted = models.BooleanField(
        default=False,
        help_text="Whether this stat should be highlighted in the UI (like Ld, Cl, Wil, Int)",
    )
    is_first_of_group = models.BooleanField(
        default=False,
        help_text="Whether this stat starts a new visual group (adds border)",
    )

    history = HistoricalRecords()

    # Properties for backward compatibility
    @property
    def field_name(self):
        return self.stat.field_name

    @property
    def short_name(self):
        return self.stat.short_name

    @property
    def full_name(self):
        return self.stat.full_name

    def __str__(self):
        return f"{self.statline_type.name} - {self.stat.short_name} ({self.stat.full_name})"

    class Meta:
        verbose_name = "Statline Type Stat"
        verbose_name_plural = "Statline Type Stats"
        ordering = ["statline_type", "position"]
        unique_together = ["statline_type", "stat"]


class ContentStatline(Content):
    """
    Stores actual stat values for a ContentFighter using a flexible statline type.
    """

    help_text = (
        "Stores the actual stat values for a fighter using a custom statline type."
    )
    content_fighter = models.OneToOneField(
        ContentFighter, on_delete=models.CASCADE, related_name="custom_statline"
    )
    statline_type = models.ForeignKey(ContentStatlineType, on_delete=models.CASCADE)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.content_fighter} - {self.statline_type.name} Statline"

    def clean(self):
        """
        Validates that all required stats have values through ContentStatlineStat.

        Note: This validation is skipped during creation since the related
        ContentStatlineStat objects are created after the ContentStatline is saved.
        The admin's save_related method handles creating missing stats automatically.
        """
        # Only validate if this is an existing object (has a pk) and has a statline type
        # Skip validation during creation or when pk is not yet set
        if (
            self.statline_type_id
            and self.pk
            and hasattr(self, "_state")
            and not self._state.adding
        ):
            required_stats = set(
                self.statline_type.stats.values_list("stat__field_name", flat=True)
            )

            # Only validate if there are required stats
            if required_stats:
                provided_stats = set(
                    self.stats.values_list(
                        "statline_type_stat__stat__field_name", flat=True
                    )
                )
                missing_stats = required_stats - provided_stats

                if missing_stats:
                    raise ValidationError(
                        f"Missing required stats: {', '.join(sorted(missing_stats))}"
                    )

    class Meta:
        verbose_name = "Fighter Statline"
        verbose_name_plural = "Fighter Statlines"


class ContentStatlineStat(Content):
    """
    Stores a single stat value for a ContentStatline.
    """

    help_text = "Stores a single stat value for a fighter's statline."
    statline = models.ForeignKey(
        ContentStatline, on_delete=models.CASCADE, related_name="stats"
    )
    statline_type_stat = models.ForeignKey(
        ContentStatlineTypeStat, on_delete=models.CASCADE
    )
    value = models.CharField(
        max_length=10,
        help_text="The stat value (e.g., '5\"', '12', '4+', '-')",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.statline_type_stat.short_name}: {self.value}"

    class Meta:
        verbose_name = "Statline Stat"
        verbose_name_plural = "Statline Stats"
        unique_together = ["statline", "statline_type_stat"]
        ordering = ["statline_type_stat__position"]
