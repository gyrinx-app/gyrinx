from django.contrib import admin
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, When
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
    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(3)]
    )
    content_house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=False, blank=False
    )
    public = models.BooleanField(
        default=True, help_text="Public lists are visible to all users."
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        return sum([f.cost_int() for f in self.fighters()])

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def fighters(self):
        return self.listfighter_set.filter(archived=False)

    def archived_fighters(self):
        return self.listfighter_set.filter(archived=True)

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
