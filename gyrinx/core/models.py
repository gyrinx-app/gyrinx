import uuid
from dataclasses import dataclass, field
from typing import Union

from django.contrib import admin
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Concat
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentFighterProfile,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentHouse,
    ContentSkill,
    ContentWeaponAccessory,
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


class ListFighterManager(models.Manager):
    """
    Custom manager for :model:`content.ListFighter` model.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                _is_linked=Case(
                    When(linked_fighter__isnull=False, then=True),
                    default=False,
                ),
                _category_order=Case(
                    *[
                        When(
                            # Put linked fighters in the same category as their parent
                            Q(content_fighter__category=category)
                            | Q(
                                linked_fighter__list_fighter__content_fighter__category=category
                            ),
                            then=index,
                        )
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
                _sort_key=Case(
                    # Linked fighters should be sorted next to their parent
                    When(
                        _is_linked=True,
                        then=Concat(
                            "linked_fighter__list_fighter__name", Value("-after")
                        ),
                    ),
                    default=F("name"),
                    output_field=models.CharField(),
                ),
            )
            .order_by(
                "list",
                "_category_order",
                "_sort_key",
            )
        )


class ListFighterQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ListFighter`.
    """

    pass


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
        ContentEquipment,
        through="ListFighterEquipmentAssignment",
        blank=True,
        through_fields=("list_fighter", "content_equipment"),
    )

    disabled_default_assignments = models.ManyToManyField(
        ContentFighterDefaultAssignment, blank=True
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

    def assign(self, equipment, weapon_profiles=None, weapon_accessories=None):
        """
        Assign equipment to the fighter, optionally with weapon profiles and accessories.

        Note that this is only used in tests. Behaviour here will not be run when assignments are made
        through the UI.

        The actual way things are assigned:
        - We create a "virtual" assignment with main and profile fields
        - The data from the virtual assignment is POSTed back each time equipment is added
        - This allows us to create an instance of ListFighterEquipmentAssignment with the correct
            weapon profiles and accessories each time equipment is added.

        TODO: Deprecate this method.
        """
        # We create the assignment directly because Django does not use the through_defaults
        # if you .add() equipment that is already in the list, which prevents us from
        # assigning the same equipment multiple times, once with a weapon profile and once without.
        assign = ListFighterEquipmentAssignment(
            list_fighter=self, content_equipment=equipment
        )
        if weapon_profiles:
            for profile in weapon_profiles:
                assign.assign_profile(profile)

        if weapon_accessories:
            for accessory in weapon_accessories:
                assign.weapon_accessories_field.add(accessory)

        assign.save()
        return assign

    def _direct_assignments(self) -> QuerySetOf["ListFighterEquipmentAssignment"]:
        return self.equipment.through.objects.filter(list_fighter=self)

    def assignments(self):
        default_assignments = self.content_fighter.default_assignments.exclude(
            Q(pk__in=self.disabled_default_assignments.all())
        )
        return [
            VirtualListFighterEquipmentAssignment.from_assignment(a)
            for a in self._direct_assignments().order_by("list_fighter__name")
        ] + [
            VirtualListFighterEquipmentAssignment.from_default_assignment(a, self)
            for a in default_assignments
        ]

    def skilline(self):
        skills = set(list(self.content_fighter.skills.all()) + list(self.skills.all()))
        return [s.name for s in skills]

    def weapons(self):
        return [e for e in self.assignments() if e.is_weapon()]

    def wargear(self):
        return [e for e in self.assignments() if not e.is_weapon()]

    def wargearline(self):
        return [e.content_equipment.name for e in self.wargear()]

    def toggle_default_assignment(
        self, assign: ContentFighterDefaultAssignment, enable=False
    ):
        """
        Turn off a specific default assignment for this Fighter.
        """
        exists = self.content_fighter.default_assignments.contains(assign)
        already_disabled = self.disabled_default_assignments.contains(assign)
        if enable and already_disabled:
            self.disabled_default_assignments.remove(assign)
        elif not enable and exists:
            self.disabled_default_assignments.add(assign)

        self.save()

    def clone(self, **kwargs):
        """Clone the fighter, creating a new fighter with the same equipment."""

        values = {
            "name": self.name,
            "content_fighter": self.content_fighter,
            "narrative": self.narrative,
            "list": self.list,
            **kwargs,
        }

        clone = ListFighter.objects.create(
            owner=values["list"].owner,
            **values,
        )

        clone.skills.set(self.skills.all())

        for assignment in self._direct_assignments():
            assignment.clone(list_fighter=clone)

        return clone

    @property
    def archive_with(self):
        return ListFighter.objects.filter(linked_fighter__list_fighter=self)

    class Meta:
        verbose_name = "List Fighter"
        verbose_name_plural = "List Fighters"

    def __str__(self):
        cf = self.content_fighter
        return f"{self.name} – {cf.type} ({cf.category})"

    def clean_fields(self, exclude=None):
        super().clean_fields()
        if "list" not in exclude:
            cf = self.content_fighter
            cf_house = cf.house
            list_house = self.list.content_house
            if cf_house != list_house and not cf_house.generic:
                raise ValidationError(
                    f"{cf.type} cannot be a member of {list_house} list"
                )

    objects = ListFighterManager.from_queryset(ListFighterQuerySet)()


@receiver(
    post_save, sender=ListFighter, dispatch_uid="create_linked_fighter_assignment"
)
def create_linked_fighter_assignment(sender, instance, **kwargs):
    # Find the default assignments where the equipment has a fighter profile
    default_assigns = instance.content_fighter.default_assignments.exclude(
        equipment__contentequipmentfighterprofile__isnull=True
    )
    for assign in default_assigns:
        # Find disabled default assignments
        is_disabled = instance.disabled_default_assignments.contains(assign)
        # Find assignments on this fighter of that equipment
        assigned = (
            instance._direct_assignments()
            .filter(content_equipment=assign.equipment)
            .exists()
        )

        if not is_disabled and not assigned:
            # Disable the default assignment and assign the equipment directly
            # This will trigger the ListFighterEquipmentAssignment logic to
            # create the linked ListFighter
            instance.toggle_default_assignment(assign, enable=False)
            ListFighterEquipmentAssignment(
                list_fighter=instance,
                content_equipment=assign.equipment,
                cost_override=0,
            ).save()


class ListFighterEquipmentAssignment(Base, Archived):
    """A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."""

    help_text = "A ListFighterEquipmentAssignment is a link between a ListFighter and an Equipment."
    list_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Fighter",
        help_text="The ListFighter that this equipment assignment is linked to.",
    )
    content_equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Equipment",
        help_text="The ContentEquipment that this assignment is linked to.",
    )

    cost_override = models.IntegerField(
        null=True,
        blank=True,
        help_text="If set, this will be the cost of this assignment, ignoring equipment list and trading post costs",
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

    weapon_accessories_field = models.ManyToManyField(
        ContentWeaponAccessory,
        blank=True,
        related_name="weapon_accessories",
        verbose_name="weapon accessories",
        help_text="Select the weapon accessories to assign to this equipment.",
    )

    linked_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="linked_fighter",
        help_text="The ListFighter that this Equipment assignment is linked to (e.g. Exotic Beast, Vehicle).",
    )

    history = HistoricalRecords()

    # Information & Display

    def name(self):
        profile_name = self.weapon_profiles_names()
        return f"{self.content_equipment}" + (
            f" ({profile_name})" if profile_name else ""
        )

    def is_weapon(self):
        return self.content_equipment.is_weapon()

    def base_name(self):
        return f"{self.content_equipment}"

    def __str__(self):
        return f"{self.list_fighter} – {self.name()}"

    # Profiles

    def assign_profile(self, profile):
        """Assign a weapon profile to this equipment."""
        if profile.equipment != self.content_equipment:
            raise ValueError(f"{profile} is not a profile for {self.content_equipment}")
        self.weapon_profiles_field.add(profile)

    def weapon_profiles(self):
        return list(self.weapon_profiles_field.all())

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

    def weapon_profiles_names(self):
        profile_names = [p.name for p in self.weapon_profiles()]
        return ", ".join(profile_names)

    # Accessories

    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    # Costs

    def base_cost_int(self):
        return self._equipment_cost_with_override()

    def base_cost_display(self):
        return f"{self.base_cost_int()}¢"

    def weapon_profiles_cost_int(self):
        return self._profile_cost_with_override()

    def weapon_profiles_cost_display(self):
        return f"+{self.weapon_profiles_cost_int()}¢"

    def weapon_accessories_cost_int(self):
        return self._accessories_cost_with_override()

    def weapon_accessories_cost_display(self):
        return f"+{self.weapon_accessories_cost_int()}¢"

    @admin.display(description="Total Cost of Assignment")
    def cost_int(self):
        return (
            self.base_cost_int()
            + self.weapon_profiles_cost_int()
            + self.weapon_accessories_cost_int()
        )

    def cost_display(self):
        return f"{self.cost_int()}¢"

    def _equipment_cost_with_override(self):
        # The assignment can have an assigned cost which takes priority
        if self.cost_override is not None:
            return self.cost_override

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

    def _accessories_cost_with_override(self):
        accessories = self.weapon_accessories()
        if not accessories:
            return 0

        after_overrides = [self._accessory_cost_with_override(a) for a in accessories]
        return sum(after_overrides)

    def _accessory_cost_with_override(self, accessory):
        if hasattr(accessory, "cost_for_fighter"):
            return accessory.cost_for_fighter_int()

        try:
            override = ContentFighterEquipmentListWeaponAccessory.objects.get(
                fighter=self.list_fighter.content_fighter,
                weapon_accessory=accessory,
            )
            return override.cost_int()
        except ContentFighterEquipmentListWeaponAccessory.DoesNotExist:
            return accessory.cost_int()

    def accessory_cost_int(self, accessory):
        return self._accessory_cost_with_override(accessory)

    def accessory_cost_display(self, accessory):
        return f"+{self.accessory_cost_int(accessory)}¢"

    #  Behaviour

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


@receiver(
    post_save,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="create_linked_fighter",
)
def create_related_objects(sender, instance, **kwargs):
    equipment_fighter_profile = ContentEquipmentFighterProfile.objects.filter(
        equipment=instance.content_equipment,
    )
    if equipment_fighter_profile.exists() and not instance.linked_fighter:
        if equipment_fighter_profile.count() > 1:
            raise ValueError(
                f"Equipment {instance.content_equipment} has multiple fighter profiles"
            )

        profile = equipment_fighter_profile.first()

        if profile.content_fighter == instance.list_fighter.content_fighter:
            raise ValueError(
                f"Equipment {instance.content_equipment} has a fighter profile for the same fighter"
            )

        lf = ListFighter.objects.create(
            name=profile.content_fighter.type,
            content_fighter=profile.content_fighter,
            list=instance.list_fighter.list,
            owner=instance.list_fighter.list.owner,
        )
        instance.linked_fighter = lf
        lf.save()
        instance.save()


@receiver(
    post_delete,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="delete_linked_fighter",
)
def delete_linked_fighter(sender, instance, **kwargs):
    if instance.linked_fighter:
        instance.linked_fighter.delete()


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
    profiles: QuerySetOf[ContentWeaponProfile] = field(default_factory=list)
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
        return (
            self.base_cost_int()
            + self._profiles_cost_int()
            + self._accessories_cost_int()
        )

    def cost_display(self):
        """
        Return a formatted string of the total cost with the '¢' suffix.
        """
        return f"{self.cost_int()}¢"

    def _profiles_cost_int(self):
        """
        Return the integer cost for all weapon profiles, factoring in fighter overrides.
        """
        if not self._assignment:
            return sum([profile.cost_for_fighter_int() for profile in self.profiles])

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.weapon_profiles_cost_int()

    def _accessories_cost_int(self):
        """
        Return the integer cost for all weapon accessories.
        """
        if not self._assignment:
            # TOOO: Support fighter cost for weapon accessories
            return 0

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.weapon_accessories_cost_int()

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

    def weapon_profiles(self):
        """
        Return all weapon profiles for this equipment.
        """
        if not self._assignment:
            return [profile for profile in self.profiles if profile.cost_int() > 0]

        return self._assignment.weapon_profiles()

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
            for profile in self.weapon_profiles()
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

    def weapon_accessories(self):
        if not self._assignment:
            return []

        return self._assignment.weapon_accessories()

    def weapon_accessories_display(self):
        return [
            {
                "accessory": accessory,
                "cost_int": self._weapon_accessory_cost(accessory),
                "cost_display": f"+{self._weapon_accessory_cost(accessory)}¢",
            }
            for accessory in self.weapon_accessories()
        ]

    def _weapon_accessory_cost(self, accessory):
        if not self._assignment:
            return accessory.cost_for_fighter_int()

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.accessory_cost_int(accessory)
