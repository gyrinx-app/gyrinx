from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipmentListItem,
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

    def fighters(self):
        return self.listfighter_set.all().order_by(
            Case(
                When(content_fighter__category="LEADER", then=0),
                When(content_fighter__category="CHAMPION", then=1),
                When(content_fighter__category="PROSPECT", then=2),
                When(content_fighter__category="JUVE", then=3),
                default=99,
            ),
            "name",
        )

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

    @admin.display(description="Total Cost with Equipment")
    def cost_int(self):
        # TODO: Take into account equipment list cost
        return self.content_fighter.cost_int() + sum(
            [e.total_assignment_cost() for e in self.assignments()]
        )

    def assign(self, equipment, weapon_profile=None):
        # We create the assignment directly because Django does not use the through_defaults
        # if you .add() equipment that is already in the list, which prevents us from
        # assigning the same equipment multiple times, once with a weapon profile and once without.
        if weapon_profile:
            ListFighterEquipmentAssignment(
                list_fighter=self,
                content_equipment=equipment,
                weapon_profile=weapon_profile,
            ).save()
        else:
            ListFighterEquipmentAssignment(
                list_fighter=self,
                content_equipment=equipment,
            ).save()

    def assignments(self):
        return self.equipment.through.objects.filter(list_fighter=self).order_by(
            "list_fighter__name"
        )

    def skilline(self):
        return [s.name for s in self.skills.all()]

    def weapons(self):
        return [e for e in self.assignments() if e.is_weapon()]

    def wargear(self):
        return [e for e in self.assignments() if not e.is_weapon()]

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

    history = HistoricalRecords()

    def all_profiles(self):
        query = Q(equipment=self.content_equipment, cost=0)
        if self.weapon_profile:
            query = query | Q(id=self.weapon_profile.id)

        return ContentWeaponProfile.objects.filter(query).order_by(
            Case(
                When(name="", then=0),
                default=1,
            )
        )

    def standard_profiles(self):
        return ContentWeaponProfile.objects.filter(
            equipment=self.content_equipment, cost=0
        ).order_by(
            Case(
                When(name="", then=0),
                default=1,
            )
        )

    def is_weapon(self):
        return self.content_equipment.is_weapon()

    def name(self):
        return (
            f"{self.weapon_profile}"
            if self.weapon_profile
            else f"{self.content_equipment}"
        )

    def base_name(self):
        return f"{self.content_equipment}"

    def base_cost_int(self):
        return self._equipment_cost_with_override()

    def base_cost_display(self):
        return f"{self.base_cost_int()}¢"

    def profile_name(self):
        return f"{self.weapon_profile.name}" if self.weapon_profile else ""

    def profile_cost_int(self):
        return self._profile_cost_with_override()

    def profile_cost_display(self):
        return f"+{self.profile_cost_int()}¢"

    def statline(self):
        return self.weapon_profile.statline() if self.weapon_profile else []

    def traitline(self):
        return self.weapon_profile.traitline() if self.weapon_profile else []

    # The following methods are used to calculate the ensure assignments contribution
    # to the total cost of the ListFighter
    # TODO: The implementation of assignments is not right: there should be support for
    # multiple weapon profiles, with each additional profiles included in the cost, and
    # there should be support for having the same weapon multiple times (but not other equipment).
    # Additionally, it's confusing that the equipment itself can have a cost which can also be
    # overridden by the "default" weapon profile.

    @admin.display(description="Total Cost of Assignment")
    def total_assignment_cost(self):
        return self._equipment_cost_with_override() + self._profile_cost_with_override()

    def total_assignment_cost_display(self):
        return f"{self.total_assignment_cost()}¢"

    def _equipment_cost_with_override(self):
        try:
            override = ContentFighterEquipmentListItem.objects.get(
                fighter=self.list_fighter.content_fighter,
                equipment=self.content_equipment,
                # None here is very important: it means we're looking for the base equipment cost.
                weapon_profile=None,
            )
            return override.cost_int()
        except ContentFighterEquipmentListItem.DoesNotExist:
            return self.content_equipment.cost_int()

    def _profile_cost_with_override(self):
        if self.weapon_profile is None:
            return 0

        try:
            override = ContentFighterEquipmentListItem.objects.get(
                fighter=self.list_fighter.content_fighter,
                equipment=self.content_equipment,
                weapon_profile=self.weapon_profile,
            )
            return override.cost_int()
        except ContentFighterEquipmentListItem.DoesNotExist:
            return self.weapon_profile.cost_int()

    class Meta:
        verbose_name = "Fighter Equipment Assignment"
        verbose_name_plural = "Fighter Equipment Assignments"

    def __str__(self):
        return f"{self.list_fighter} – {self.name()}"

    def clean(self):
        if (
            self.weapon_profile
            and self.weapon_profile.equipment != self.content_equipment
        ):
            raise ValidationError(
                f"{self.weapon_profile} is not a profile for {self.content_equipment}"
            )
