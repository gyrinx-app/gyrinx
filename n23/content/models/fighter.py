"""
Fighter models for content data.

This module contains:
- ContentFighterManager/QuerySet: Custom manager and queryset
- ContentFighter: Main fighter/character archetype model
- ContentFighterCategoryTerms: Custom terminology for fighter types
"""

import logging

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from django.db.models.functions import Lower
from django.utils.functional import cached_property
from multiselectfield import MultiSelectField
from simple_history.models import HistoricalRecords

from n23.models import FighterCategoryChoices

from .base import Content, ContentManager, ContentQuerySet

logger = logging.getLogger(__name__)


class ContentFighterManager(ContentManager):
    """
    Custom manager for :model:`content.ContentFighter` model.
    """

    def _annotate_default(self, qs):
        """Apply the default category ordering annotations."""
        return qs.annotate(
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
        ).order_by(
            "house__name",
            "_category_order",
            "type",
        )

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
        Returns all fighters including stash fighters, excluding pack content.
        """
        return self._annotate_default(super().get_queryset())

    def all_content(self):
        """Return all fighters including pack content."""
        return self._annotate_default(super().all_content())

    def with_packs(self, packs, include_archived_items=False):
        """Return base fighters plus fighters from specified packs."""
        return self._annotate_default(
            super().with_packs(packs, include_archived_items=include_archived_items)
        )


class ContentFighterQuerySet(ContentQuerySet):
    """
    Custom QuerySet for :model:`content.ContentFighter`.
    """

    def available_for_house(
        self,
        house,
        include=(),
        exclude=(
            FighterCategoryChoices.EXOTIC_BEAST,
            FighterCategoryChoices.VEHICLE,
            FighterCategoryChoices.STASH,
        ),
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

    # Stats live in the fighter's ContentStatline, one row per stat, which
    # lets a vehicle or crew carry a different set from a ganger. The 12
    # hardcoded columns that used to hold them were dropped by #1861.

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
        try:
            house = f"{self.house}" if self.house else ""
        except models.ObjectDoesNotExist:
            # A dangling house FK (local template-data drift) must not make the
            # fighter unprintable — that 500s any admin page listing fighters.
            house = ""
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
        from n23.core.models.list import ListFighter, bulk_mark_fighters_dirty

        # Find all list fighters using this content fighter (including legacy)
        fighters = ListFighter.objects.filter(
            Q(content_fighter=self) | Q(legacy_content_fighter=self),
            archived=False,
        )

        bulk_mark_fighters_dirty(fighters)

    def statline(self):
        """
        Returns a list of dictionaries describing the fighter's core stats,
        with additional styling indicators, read from the fighter's statline.

        Performance: Note that this method is expensive and is entirely skipped if the statline is prefecthed
        by ListFighter with_related_data.
        """
        statline = getattr(self, "custom_statline", None)
        if statline is None:
            # Every fighter is given one on save, so this means the save-time
            # guarantee did not fire — most likely no statline type is
            # configured for its category. Render nothing rather than invent
            # stats, and say so.
            logger.warning(
                "ContentFighter %s (%r) has no statline; rendering no stats.",
                self.pk,
                self.category,
            )
            return []

        stats = []
        # Get all stat values for this statline. Both loops reach through
        # ContentStatlineTypeStat to ContentStat for the field and short
        # names, so the chain has to be select_related in both — without it
        # this is two queries per stat, every time a card is built off the
        # un-annotated path.
        stat_values = {
            stat.statline_type_stat.field_name: stat.value
            for stat in statline.stats.select_related("statline_type_stat__stat")
        }
        for stat_def in statline.statline_type.stats.select_related("stat"):
            stats.append(
                {
                    "field_name": stat_def.field_name,
                    "name": stat_def.short_name,
                    "value": stat_values.get(stat_def.field_name, "-"),
                    "highlight": stat_def.is_highlighted,
                    "first_of_group": stat_def.is_first_of_group,
                }
            )
        return stats

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
        from n23.content.statlines import set_fighter_statline

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

        # Read the statline off the source before it stops being ours. Stats
        # used to be columns on this row and rode along with the duplicate for
        # free; now they are rows keyed to the fighter, so saving the copy
        # gives it a fresh empty statline that has to be filled in below.
        source_statline = getattr(self, "custom_statline", None)
        statline_type = source_statline.statline_type if source_statline else None
        stat_values = (
            {
                stat.statline_type_stat_id: stat.value
                for stat in source_statline.stats.all()
            }
            if source_statline
            else {}
        )

        # Copy the fighter
        self.pk = None
        self.house = house
        # The statline is a reverse one-to-one cached on the instance; left in
        # place it would point the copy at the original's row.
        self._state.fields_cache.pop("custom_statline", None)
        self.save()
        fighter_id = self.pk

        if statline_type is not None:
            set_fighter_statline(self, statline_type, stat_values)

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
