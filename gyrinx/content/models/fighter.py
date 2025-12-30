"""
Fighter models for content data.

This module contains:
- ContentFighterManager/QuerySet: Custom manager and queryset
- ContentFighter: Main fighter/character archetype model
- ContentFighterCategoryTerms: Custom terminology for fighter types
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from django.db.models.functions import Lower
from django.utils.functional import cached_property
from multiselectfield import MultiSelectField
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content


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
        from .house import ContentHouse

        exclude = set(exclude) - set(include)

        # Check if the house can hire any fighter
        if house.can_hire_any:
            # Can hire any fighter except stash fighters
            return self.exclude(category=FighterCategoryChoices.STASH).select_related(
                "house"
            )
        else:
            # Normal filtering: only house and generic houses, exclude exotic beasts and stash
            generic_houses = ContentHouse.objects.filter(generic=True).values_list(
                "id", flat=True
            )
            return (
                self.filter(
                    house__in=[house.id] + list(generic_houses),
                )
                .exclude(category__in=exclude)
                .select_related("house")
            )


class ContentFighter(Content):
    """
    Represents a fighter or character archetype. Includes stats, base cost,
    and relationships to skills, rules, and a house/faction.
    """

    help_text = "The Content Fighter captures archetypal information about a fighter from the rulebooks."
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255, choices=FighterCategoryChoices)
    house = models.ForeignKey(
        "ContentHouse", on_delete=models.CASCADE, null=True, blank=True
    )
    skills = models.ManyToManyField(
        "ContentSkill", blank=True, verbose_name="Default Skills"
    )
    primary_skill_categories = models.ManyToManyField(
        "ContentSkillCategory",
        blank=True,
        related_name="primary_fighters",
        verbose_name="Primary Skill Trees",
    )
    secondary_skill_categories = models.ManyToManyField(
        "ContentSkillCategory",
        blank=True,
        related_name="secondary_fighters",
        verbose_name="Secondary Skill Trees",
    )
    rules = models.ManyToManyField("ContentRule", blank=True)
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
        from .house import ContentFighterHouseOverride

        cost_override = ContentFighterHouseOverride.objects.filter(
            fighter=self,
            house=house,
            cost__isnull=False,
        ).first()
        if cost_override:
            return cost_override.cost

        return self.cost_int()

    def set_dirty(self) -> None:
        """
        Mark all ListFighters using this content fighter as dirty.

        Propagates to parent lists via their set_dirty() methods.
        Called when this fighter's base_cost field changes.
        """
        # Lazy import to avoid circular dependency
        from gyrinx.core.models.list import ListFighter

        # Find all list fighters using this content fighter (including legacy)
        fighters = ListFighter.objects.filter(
            Q(content_fighter=self) | Q(legacy_content_fighter=self),
            archived=False,
        ).select_related("list")

        for fighter in fighters:
            fighter.set_dirty(save=True)

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
        from .default_assignment import ContentFighterDefaultAssignment
        from .equipment_list import (
            ContentFighterEquipmentListItem,
            ContentFighterEquipmentListUpgrade,
            ContentFighterEquipmentListWeaponAccessory,
        )

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
