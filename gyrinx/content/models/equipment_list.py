"""
Equipment list models for content data.

This module contains:
- ContentFighterEquipmentListItem: Equipment available to fighters
- ContentFighterEquipmentListWeaponAccessory: Weapon accessories available to fighters
- ContentFighterEquipmentListUpgrade: Equipment upgrades available to fighters
"""

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import CostMixin

from .base import Content


class ContentFighterEquipmentListItem(CostMixin, Content):
    """
    Associates :model:`content.ContentEquipment` with a given fighter in the rulebook, optionally
    specifying a weapon profile and cost override.
    """

    help_text = "Captures the equipment list available to a fighter in the rulebook."
    fighter = models.ForeignKey(
        "ContentFighter", on_delete=models.CASCADE, db_index=True
    )
    equipment = models.ForeignKey(
        "ContentEquipment", on_delete=models.CASCADE, db_index=True
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

    def set_dirty(self) -> None:
        """
        Mark affected ListFighterEquipmentAssignments as dirty.

        Finds assignments where:
        - The equipment matches this item's equipment
        - The fighter's content_fighter (or legacy) matches this item's fighter
        """
        from django.db.models import Q

        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find assignments for this equipment on fighters using this content fighter
        assignments = ListFighterEquipmentAssignment.objects.filter(
            Q(list_fighter__content_fighter=self.fighter)
            | Q(list_fighter__legacy_content_fighter=self.fighter),
            content_equipment=self.equipment,
            archived=False,
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)


class ContentFighterEquipmentListWeaponAccessory(CostMixin, Content):
    """
    Associates :model:`content.ContentWeaponAccessory` with a given fighter in the rulebook, optionally
    specifying a cost override.
    """

    help_text = (
        "Captures the weapon accessories available to a fighter in the rulebook."
    )
    fighter = models.ForeignKey(
        "ContentFighter", on_delete=models.CASCADE, db_index=True
    )
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

    def set_dirty(self) -> None:
        """
        Mark affected ListFighterEquipmentAssignments as dirty.

        Finds assignments where:
        - The assignment has this accessory
        - The fighter's content_fighter (or legacy) matches this item's fighter
        """
        from django.db.models import Q

        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find assignments with this accessory on fighters using this content fighter
        assignments = ListFighterEquipmentAssignment.objects.filter(
            Q(list_fighter__content_fighter=self.fighter)
            | Q(list_fighter__legacy_content_fighter=self.fighter),
            weapon_accessories_field=self.weapon_accessory,
            archived=False,
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)


class ContentFighterEquipmentListUpgrade(CostMixin, Content):
    """
    Associates ContentEquipmentUpgrade with a given fighter in the rulebook,
    specifying a cost override.
    """

    help_text = (
        "Captures the equipment upgrades available to a fighter with cost overrides."
    )
    fighter = models.ForeignKey(
        "ContentFighter", on_delete=models.CASCADE, db_index=True
    )
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

    def set_dirty(self) -> None:
        """
        Mark affected ListFighterEquipmentAssignments as dirty.

        Finds assignments where:
        - The assignment has this upgrade
        - The fighter's content_fighter (or legacy) matches this item's fighter
        """
        from django.db.models import Q

        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        # Find assignments with this upgrade on fighters using this content fighter
        assignments = ListFighterEquipmentAssignment.objects.filter(
            Q(list_fighter__content_fighter=self.fighter)
            | Q(list_fighter__legacy_content_fighter=self.fighter),
            upgrades_field=self.upgrade,
            archived=False,
        ).select_related("list_fighter__list")

        for assignment in assignments:
            assignment.set_dirty(save=True)
