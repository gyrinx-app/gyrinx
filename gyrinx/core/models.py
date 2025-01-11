import uuid
from dataclasses import dataclass
from typing import Union

from django.contrib import admin
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, When
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentHouse,
    ContentSkill,
    ContentWeaponProfile,
)
from gyrinx.models import Archived, Base, Owned, QuerySetOf


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
    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(3)]
    )
    content_house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=False, blank=False
    )
    public = models.BooleanField(
        default=True, help_text="Public lists are visible to all users."
    )
    narrative = models.TextField(
        "about",
        blank=True,
        help_text="Narrative description of the gang in this list: their history and how to play them.",
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        return sum([f.cost_int() for f in self.fighters()])

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.filter(archived=False)

    def archived_fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.filter(archived=True)

    def clone(self, name=None, owner=None, **kwargs):
        """Clone the list, creating a new list with the same fighters."""
        if not name:
            name = f"{self.name} (Clone)"

        if not owner:
            owner = self.owner

        values = {
            "public": self.public,
            **kwargs,
        }

        clone = List.objects.create(
            name=name,
            content_house=self.content_house,
            owner=owner,
            **values,
        )

        for fighter in self.fighters():
            fighter.clone(list=clone)

        return clone

    class Meta:
        verbose_name = "List"
        verbose_name_plural = "Lists"

    def __str__(self):
        return self.name


class ListFighter(AppBase):
    """A Fighter is a member of a List."""

    help_text = "A ListFighter is a member of a List, linked to a Content Fighter archetype to give base stats and equipment."
    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(3)]
    )
    content_fighter = models.ForeignKey(
        ContentFighter, on_delete=models.CASCADE, null=False, blank=False
    )
    list = models.ForeignKey(List, on_delete=models.CASCADE, null=False, blank=False)

    equipment = models.ManyToManyField(
        ContentEquipment, through="ListFighterEquipmentAssignment", blank=True
    )

    skills = models.ManyToManyField(ContentSkill, blank=True)
    narrative = models.TextField(
        "about",
        blank=True,
        help_text="Narrative description of the Fighter: their history and how to play them.",
    )

    history = HistoricalRecords()

    @admin.display(description="Total Cost with Equipment")
    def cost_int(self):
        return self.content_fighter.cost_int() + sum(
            [e.cost_int() for e in self.assignments()]
        )

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def assign(self, equipment, weapon_profile=None, weapon_profiles=None):
        if weapon_profiles and weapon_profile:
            raise ValueError("Cannot specify both weapon_profile and weapon_profiles")

        if weapon_profile and not weapon_profiles:
            weapon_profiles = [weapon_profile]

        # We create the assignment directly because Django does not use the through_defaults
        # if you .add() equipment that is already in the list, which prevents us from
        # assigning the same equipment multiple times, once with a weapon profile and once without.
        assign = ListFighterEquipmentAssignment(
            list_fighter=self, content_equipment=equipment
        )
        if weapon_profiles:
            assign.weapon_profiles_field.set(weapon_profiles)

        assign.save()
        return assign

    def _direct_assignments(self) -> QuerySetOf["ListFighterEquipmentAssignment"]:
        return self.equipment.through.objects.filter(list_fighter=self)

    def assignments(self):
        return [
            VirtualListFighterEquipmentAssignment.from_assignment(a)
            for a in self._direct_assignments().order_by("list_fighter__name")
        ] + [
            VirtualListFighterEquipmentAssignment.from_default_assignment(a, self)
            for a in self.content_fighter.default_assignments.all()
        ]

    def skilline(self):
        return [s.name for s in self.skills.all()]

    def weapons(self):
        return [e for e in self.assignments() if e.is_weapon()]

    def wargear(self):
        return [e for e in self.assignments() if not e.is_weapon()]

    def wargearline(self):
        return [e.content_equipment.name for e in self.wargear()]

    def clone(self, list=None):
        """Clone the fighter, creating a new fighter with the same equipment."""
        if not list:
            list = self.list

        clone = ListFighter.objects.create(
            name=self.name,
            content_fighter=self.content_fighter,
            list=list,
            owner=list.owner,
            narrative=self.narrative,
        )

        clone.skills.set(self.skills.all())

        for assignment in self._direct_assignments():
            assignment.clone(list_fighter=clone)

        return clone

    class Meta:
        verbose_name = "List Fighter"
        verbose_name_plural = "List Fighters"
        ordering = [
            Case(
                *[
                    When(content_fighter__category=category, then=index)
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
                default=99,
            ),
            "content_fighter__category",
            "name",
        ]

    def __str__(self):
        cf = self.content_fighter
        return f"{self.name} – {cf.type} ({cf.category})"

    def clean_fields(self, exclude=None):
        super().clean_fields()
        if "list" not in exclude:
            cf = self.content_fighter
            cf_house = cf.house
            list_house = self.list.content_house
            if cf_house != list_house:
                raise ValidationError(
                    f"{cf.type} cannot be a member of {list_house} list"
                )


class ListFighterEquipmentAssignment(AppBase):
    """A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."""

    help_text = "A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."
    list_fighter = models.ForeignKey(
        ListFighter, on_delete=models.CASCADE, null=False, blank=False
    )
    content_equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, null=False, blank=False
    )

    # TODO: Deprecate and remove this field
    weapon_profile = models.ForeignKey(
        ContentWeaponProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="This field is deprecated and should not be used. Use weapon profiles instead.",
        verbose_name="weapon profile (deprecated)",
    )

    # This is a many-to-many field because we want to be able to assign equipment
    # with multiple weapon profiles.
    weapon_profiles_field = models.ManyToManyField(
        ContentWeaponProfile,
        blank=True,
        related_name="weapon_profiles",
        verbose_name="weapon profiles",
        help_text="Select the costed weapon profiles to assign to this equipment. The standard profiles are automatically included in the cost of the equipment.",
    )

    history = HistoricalRecords()

    def weapon_profiles(self):
        profiles = self.weapon_profiles_field.all()
        # It's possible that there is a weapon profile set, and it is also in the list of profiles.
        # This goes away as we deprecate the weapon_profile field.
        duplicated = self.weapon_profile in profiles
        return list(profiles) + (
            [self.weapon_profile] if self.weapon_profile and not duplicated else []
        )

    def weapon_profiles_display(self):
        """Return a list of dictionaries with the weapon profiles and their costs."""
        profiles = self.weapon_profiles()
        return [
            dict(
                profile=p,
                cost_int=self.profile_cost_int(p),
                cost_display=self.profile_cost_display(p),
            )
            for p in profiles
        ]

    def all_profiles(self):
        """Return all profiles for the equipment, including the default profiles."""
        standard_profiles = list(self.standard_profiles())
        weapon_profiles = self.weapon_profiles()

        seen = set()
        result = []
        for p in standard_profiles + weapon_profiles:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result

    def standard_profiles(self):
        return ContentWeaponProfile.objects.filter(
            equipment=self.content_equipment, cost=0
        )

    def is_weapon(self):
        return self.content_equipment.is_weapon()

    def name(self):
        profile_name = self.weapon_profiles_names()
        return f"{self.content_equipment}" + (
            f" ({profile_name})" if profile_name else ""
        )

    def weapon_profiles_names(self):
        profile_names = [p.name for p in self.weapon_profiles()]
        return ", ".join(profile_names)

    def base_name(self):
        return f"{self.content_equipment}"

    def base_cost_int(self):
        return self._equipment_cost_with_override()

    def base_cost_display(self):
        return f"{self.base_cost_int()}¢"

    def weapon_profiles_cost_int(self):
        return self._profile_cost_with_override()

    def weapon_profiles_cost_display(self):
        return f"+{self.weapon_profiles_cost_int()}¢"

    @admin.display(description="Total Cost of Assignment")
    def cost_int(self):
        return self.base_cost_int() + self.weapon_profiles_cost_int()

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def _equipment_cost_with_override(self):
        if hasattr(self.content_equipment, "cost_for_fighter"):
            return self.content_equipment.cost_for_fighter_int()

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
        profiles = self.weapon_profiles()
        if not profiles:
            return 0

        after_overrides = [
            self._profile_cost_with_override_for_profile(p) for p in profiles
        ]
        return sum(after_overrides)

    def _profile_cost_with_override_for_profile(self, profile):
        if hasattr(profile, "cost_for_fighter"):
            return profile.cost_for_fighter_int()

        try:
            override = ContentFighterEquipmentListItem.objects.get(
                fighter=self.list_fighter.content_fighter,
                equipment=self.content_equipment,
                weapon_profile=profile,
            )
            return override.cost_int()
        except ContentFighterEquipmentListItem.DoesNotExist:
            return profile.cost_int()

    def profile_cost_int(self, profile):
        return self._profile_cost_with_override_for_profile(profile)

    def profile_cost_display(self, profile):
        return f"+{self.profile_cost_int(profile)}¢"

    def clone(self, list_fighter=None):
        """Clone the assignment, creating a new assignment with the same weapon profiles."""
        if not list_fighter:
            list_fighter = self.list_fighter

        clone = ListFighterEquipmentAssignment.objects.create(
            list_fighter=list_fighter,
            content_equipment=self.content_equipment,
        )

        for profile in self.weapon_profiles_field.all():
            clone.weapon_profiles_field.add(profile)

        return clone

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


@dataclass
class VirtualListFighterEquipmentAssignment:
    """
    A virtual container that groups a :model:`core.ListFighter` with
    :model:`content.ContentEquipment` and relevant weapon profiles.

    The cases this handles:
    * _assignment is None: Used for generating the add/edit equipment page: all the "potential"
        assignments for a fighter.
    * _assignment is a ContentFighterDefaultAssignment: Used to abstract over the fighter's default
        equipment assignments so that we can treat them as if they were ListFighterEquipmentAssignments.
    * _assignment is a ListFighterEquipmentAssignment: Used to abstract over the fighter's specific
        equipment assignments so that we can handle the above two cases.
    """

    fighter: ListFighter
    equipment: ContentEquipment
    profiles: QuerySetOf[ContentWeaponProfile]
    _assignment: (
        Union[ListFighterEquipmentAssignment, ContentFighterDefaultAssignment] | None
    ) = None

    @classmethod
    def from_assignment(cls, assignment: ListFighterEquipmentAssignment):
        return cls(
            fighter=assignment.list_fighter,
            equipment=assignment.content_equipment,
            profiles=assignment.all_profiles(),
            _assignment=assignment,
        )

    @classmethod
    def from_default_assignment(
        cls, assignment: ContentFighterDefaultAssignment, fighter: ListFighter
    ):
        return cls(
            fighter=fighter,
            equipment=assignment.equipment,
            profiles=assignment.all_profiles(),
            _assignment=assignment,
        )

    @property
    def id(self):
        if not self._assignment:
            return uuid.uuid4()

        return self._assignment.id

    @property
    def category(self):
        """
        Return the category code for this equipment.
        """
        return self.equipment.category

    @property
    def content_equipment(self):
        return self.equipment

    def name(self):
        if not self._assignment:
            return f"{self.equipment.name} (Virtual)"

        return self._assignment.name()

    def kind(self):
        if not self._assignment:
            return "virtual"

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return "default"

        return "assigned"

    def base_cost_int(self):
        """
        Return the integer cost for this equipment, factoring in fighter overrides.
        """
        if not self._assignment:
            return self.equipment.cost_for_fighter_int()

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.base_cost_int()

    def base_cost_display(self):
        """
        Return a formatted string of the base cost with the '¢' suffix.
        """
        return f"{self.base_cost_int()}¢"

    def cost_int(self):
        """
        Return the integer cost for this equipment, factoring in fighter overrides.
        """
        return self.base_cost_int() + self.profiles_cost_int()

    def cost_display(self):
        """
        Return a formatted string of the total cost with the '¢' suffix.
        """
        return f"{self.cost_int()}¢"

    def profiles_cost_int(self):
        """
        Return the integer cost for all weapon profiles, factoring in fighter overrides.
        """
        if not self._assignment:
            return sum([profile.cost_for_fighter_int() for profile in self.profiles])

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.weapon_profiles_cost_int()

    def base_name(self):
        """
        Return the equipment's name as a string.
        """
        return f"{self.equipment}"

    def all_profiles(self):
        """
        Return all profiles for this equipment.
        """
        if not self._assignment:
            return self.profiles

        return self._assignment.all_profiles()

    def standard_profiles(self):
        """
        Return only the standard (cost=0) weapon profiles for this equipment.
        """
        if not self._assignment:
            return [profile for profile in self.profiles if profile.cost == 0]

        return self._assignment.standard_profiles()

    def weapon_profiles_display(self):
        """
        Return a list of dictionaries containing each profile and its cost display.
        """
        return [
            {
                "profile": profile,
                "cost_int": self._weapon_profile_cost(profile),
                "cost_display": f"+{self._weapon_profile_cost(profile)}¢",
            }
            for profile in self.profiles
            if profile.cost_int() > 0
        ]

    def _weapon_profile_cost(self, profile):
        if not self._assignment:
            return profile.cost_for_fighter_int()

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.profile_cost_int(profile)

    def cat(self):
        """
        Return the human-readable label for the equipment category.
        """
        return self.equipment.cat()

    def is_weapon(self):
        return self.equipment.is_weapon()
