"""
Weapon models for content data.

This module contains:
- ContentWeaponTrait: Weapon traits (Rapid Fire, Knockback, etc.)
- ContentWeaponProfileManager/QuerySet: Manager and queryset
- ContentWeaponProfile: Weapon stat profiles
- ContentWeaponAccessoryManager/QuerySet: Manager and queryset
- ContentWeaponAccessory: Weapon accessories
- VirtualWeaponProfile: Dataclass wrapper for profiles with mods applied
"""

import logging
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, OuterRef, Subquery, When
from django.db.models.functions import Coalesce
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords
from simpleeval import simple_eval

from gyrinx.models import FighterCostMixin, format_cost_display

from .base import Content, ContentManager, ContentQuerySet, StatlineDisplay

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ContentWeaponTrait(Content):
    """
    Represents a trait that can be associated with a weapon, such as 'Knockback'
    or 'Rapid Fire'.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(
        blank=True,
        default="",
        help_text="An optional description of what this trait does.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Weapon Trait"
        verbose_name_plural = "Weapon Traits"
        ordering = ["name"]


class ContentWeaponProfileManager(ContentManager):
    """
    Custom manager for :model:`content.ContentWeaponProfile` model.
    """

    def _annotate_default(self, qs):
        """Apply the default name ordering annotations."""
        return qs.annotate(
            _name_order=Case(
                When(name="", then=0),
                default=1,
                output_field=models.IntegerField(),
            )
        ).order_by(
            "equipment__name",
            "_name_order",
            "name",
            "cost",
        )

    def get_queryset(self):
        return self._annotate_default(super().get_queryset())

    def all_content(self):
        return self._annotate_default(super().all_content())

    def with_packs(self, packs):
        return self._annotate_default(super().with_packs(packs))


class ContentWeaponProfileQuerySet(ContentQuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponProfile`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(self, content_fighter) -> "ContentWeaponProfileQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        from .equipment_list import ContentFighterEquipmentListItem

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


class ContentWeaponProfile(FighterCostMixin, Content):
    """
    Represents a specific profile for :model:`content.ContentEquipment`. "Standard" profiles have zero cost.
    """

    equipment = models.ForeignKey(
        "ContentEquipment",
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

    def all_traits(self):
        """Return all traits including pack-scoped ones.

        The default M2M manager (self.traits.all()) uses ContentManager which
        excludes pack content. This method bypasses that filter so custom
        weapon traits from content packs are included.
        """
        trait_ids = self.traits.through.objects.filter(
            contentweaponprofile_id=self.pk
        ).values_list("contentweapontrait_id", flat=True)
        return list(ContentWeaponTrait.objects.all_content().filter(pk__in=trait_ids))

    def traitline(self):
        """
        Returns a list of weapon trait names associated with this profile.
        """
        return [trait.name for trait in self.all_traits()]

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

    def set_dirty(self) -> None:
        """
        Mark all ListFighterEquipmentAssignments using this weapon profile as dirty.

        Propagates to parent fighters and lists via their set_dirty() methods.
        Called when this profile's cost field changes.
        """
        # Lazy import to avoid circular dependency
        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find all assignments using this weapon profile (via M2M)
        assignments = ListFighterEquipmentAssignment.objects.filter(
            weapon_profiles_field=self, archived=False
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)

    objects = ContentWeaponProfileManager.from_queryset(ContentWeaponProfileQuerySet)()


class ContentWeaponAccessoryManager(ContentManager):
    """
    Custom manager for :model:`content.ContentWeaponAccessory` model. Currently unused but available
    for future extensions.
    """

    pass


class ContentWeaponAccessoryQuerySet(ContentQuerySet):
    """
    Custom QuerySet for :model:`content.ContentWeaponAccessory`. Provides fighter-specific cost overrides.
    """

    def with_cost_for_fighter(
        self, content_fighter
    ) -> "ContentWeaponAccessoryQuerySet":
        """
        Annotates the queryset with cost overrides for a given fighter, if present.
        """
        from .equipment_list import ContentFighterEquipmentListWeaponAccessory

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
        """Calculate the cost of this accessory for a given weapon base cost.

        Uses simpleeval for safe expression evaluation (not Python's eval).
        """
        if not self.cost_expression:
            return self.cost

        # Define available functions for simpleeval
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
            # simpleeval is a safe expression evaluator, not Python's eval()
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

    def set_dirty(self) -> None:
        """
        Mark all ListFighterEquipmentAssignments using this accessory as dirty.

        Propagates to parent fighters and lists via their set_dirty() methods.
        Called when this accessory's cost field changes.
        """
        # Lazy import to avoid circular dependency
        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find all assignments using this weapon accessory (via M2M)
        assignments = ListFighterEquipmentAssignment.objects.filter(
            weapon_accessories_field=self, archived=False
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)

    class Meta:
        verbose_name = "Weapon Accessory"
        verbose_name_plural = "Weapon Accessories"
        ordering = ["name"]

    objects = ContentWeaponAccessoryManager.from_queryset(
        ContentWeaponAccessoryQuerySet
    )()


@dataclass
class VirtualWeaponProfile:
    """
    A virtual container for profiles that applies mods.
    """

    profile: ContentWeaponProfile
    mods: list = field(default_factory=list)

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

    def _statmods(self, stat=None) -> list:
        from .modifier import ContentModStat

        return [
            mod
            for mod in self.mods
            if isinstance(mod, ContentModStat) and (stat is None or mod.stat == stat)
        ]

    def _traitmods(self) -> list:
        from .modifier import ContentModTrait

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

    def _apply_mods(self, stat: str, value: str, mods: list):
        for mod in mods:
            value = mod.apply(value)
        return value

    @property
    def traits(self):
        mods = self._traitmods()
        value = self.profile.all_traits()
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
        original_traits = self.profile.all_traits()

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
