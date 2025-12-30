"""
Default assignment models for content data.

This module contains:
- ContentFighterDefaultAssignment: Default equipment for fighters
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.models import CostMixin

from .base import Content
from .weapon import VirtualWeaponProfile


class ContentFighterDefaultAssignment(CostMixin, Content):
    """
    Associates a fighter with a piece of equipment by default, including weapon profiles.
    """

    help_text = "Captures the default equipment assignments for a fighter."
    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="default_assignments",
    )
    equipment = models.ForeignKey(
        "ContentEquipment", on_delete=models.CASCADE, db_index=True
    )
    weapon_profiles_field = models.ManyToManyField(
        "ContentWeaponProfile",
        blank=True,
    )
    weapon_accessories_field = models.ManyToManyField(
        "ContentWeaponAccessory",
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
