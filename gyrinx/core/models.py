from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentSkill,
    ContentWeaponProfile,
)
from gyrinx.models import Archived, Base, Owned


class AppBase(Base, Owned, Archived):
    """An AppBase object is a base class for all application models."""

    class Meta:
        abstract = True


##
## Application Models
##


class List(AppBase):
    """A List is a reusable collection of fighters."""

    help_text = "A List is a reusable collection of fighters."
    name = models.CharField(max_length=255)
    content_house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=False, blank=False
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        return sum([f.cost_int() for f in self.listfighter_set.all()])

    class Meta:
        verbose_name = "List"
        verbose_name_plural = "Lists"

    def __str__(self):
        return self.name


class ListFighter(AppBase):
    """A Fighter is a member of a List."""

    help_text = "A ListFighter is a member of a List, linked to a Content Fighter archetype to give base stats and equipment."
    name = models.CharField(max_length=255)
    content_fighter = models.ForeignKey(
        ContentFighter, on_delete=models.CASCADE, null=False, blank=False
    )
    list = models.ForeignKey(List, on_delete=models.CASCADE, null=False, blank=False)

    equipment = models.ManyToManyField(
        ContentEquipment, through="ListFighterEquipmentAssignment", blank=True
    )

    skills = models.ManyToManyField(ContentSkill, blank=True)

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        # TODO: Take into account equipment list cost
        return self.content_fighter.cost_int() + sum(
            [e.cost_int() for e in self.equipment.all()]
        )

    def assign(self, equipment, weapon_profile=None):
        """Assign an equipment to this fighter."""
        if weapon_profile:
            self.equipment.add(
                equipment, through_defaults=dict(weapon_profile=weapon_profile)
            )
        else:
            self.equipment.add(equipment)

    def assignments(self):
        return self.equipment.through.objects.filter(list_fighter=self)

    def skilline(self):
        return [s.name for s in self.skills.all()]

    def weapons(self):
        return self.assignments().filter(weapon_profile__isnull=False)

    def wargear(self):
        return self.assignments().filter(weapon_profile__isnull=True)

    def wargearline(self):
        return [e.content_equipment.name for e in self.wargear()]

    class Meta:
        verbose_name = "List Fighter"
        verbose_name_plural = "List Fighters"

    def __str__(self):
        cf = self.content_fighter
        return f"{self.name} – {cf.type} ({cf.category})"

    def clean(self):
        cf = self.content_fighter
        cf_house = cf.house
        list_house = self.list.content_house
        if cf_house != list_house:
            raise ValidationError(f"{cf.type} cannot be a member of {list_house} list")


class ListFighterEquipmentAssignment(AppBase):
    """A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."""

    help_text = "A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."
    list_fighter = models.ForeignKey(
        ListFighter, on_delete=models.CASCADE, null=False, blank=False
    )
    content_equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, null=False, blank=False
    )

    weapon_profile = models.ForeignKey(
        ContentWeaponProfile, on_delete=models.CASCADE, null=True, blank=True
    )

    def all_profiles(self):
        profiles = list(
            ContentWeaponProfile.objects.filter(
                Q(equipment=self.content_equipment, cost=0)
                | Q(id=self.weapon_profile.id)
            ).order_by(
                Case(
                    When(name="", then=0),
                    default=1,
                )
            )
        )

        return profiles

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Fighter Equipment Assignment"
        verbose_name_plural = "Fighter Equipment Assignments"

    def __str__(self):
        return f"{self.list_fighter} – {self.content_equipment}"
