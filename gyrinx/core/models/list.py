import logging
import uuid
from dataclasses import dataclass, field
from typing import Union

from django.contrib import admin
from django.core import validators
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Concat
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx import settings
from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterHouseOverride,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentHouseAdditionalRule,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentPsykerPower,
    ContentSkill,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    RulelineDisplay,
    StatlineDisplay,
    VirtualWeaponProfile,
)
from gyrinx.core.models.base import AppBase
from gyrinx.models import Archived, Base, QuerySetOf

logger = logging.getLogger(__name__)
pylist = list


##
## Application Models
##


class List(AppBase):
    """A List is a reusable collection of fighters."""

    # Status choices
    LIST_BUILDING = "list_building"
    CAMPAIGN_MODE = "campaign_mode"

    STATUS_CHOICES = [
        (LIST_BUILDING, "List Building"),
        (CAMPAIGN_MODE, "Campaign Mode"),
    ]

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
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=LIST_BUILDING,
        help_text="Current status of the list.",
    )

    # Track the original list if this is a campaign clone
    original_list = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_clones",
        help_text="The original list this was cloned from for a campaign.",
    )

    # Track which campaign this list is associated with (if in campaign mode)
    campaign = models.ForeignKey(
        "Campaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_lists",
        help_text="The campaign this list is participating in (if in campaign mode).",
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        return sum([f.cost_int() for f in self.fighters()])

    @cached_property
    def cost_int_cached(self):
        cache = caches["core_list_cache"]
        cache_key = self.cost_cache_key()
        cached = cache.get(cache_key)
        if cached:
            return cached

        cost = sum([f.cost_int_cached for f in self.fighters_cached])
        cache.set(cache_key, cost, settings.CACHE_LIST_TTL)
        return cost

    def cost_display(self):
        return f"{self.cost_int_cached}¢"

    def fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.filter(archived=False)

    def archived_fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.filter(archived=True)

    @cached_property
    def fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.fighters()

    @cached_property
    def archived_fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.archived_fighters()

    @cached_property
    def owner_cached(self):
        return self.owner

    @property
    def is_list_building(self):
        return self.status == self.LIST_BUILDING

    @property
    def is_campaign_mode(self):
        return self.status == self.CAMPAIGN_MODE

    @property
    def active_campaign_clones(self):
        """Get campaign clones that are in active (in-progress) campaigns."""
        from .campaign import Campaign

        return self.campaign_clones.filter(
            status=self.CAMPAIGN_MODE, campaign__status=Campaign.IN_PROGRESS
        )

    def cost_cache_key(self):
        return f"list_cost_{self.id}"

    def update_cost_cache(self):
        cache = caches["core_list_cache"]
        cache_key = self.cost_cache_key()
        cache.delete(cache_key)
        cache.set(cache_key, self.cost_int(), settings.CACHE_LIST_TTL)

    def clone(self, name=None, owner=None, for_campaign=None, **kwargs):
        """Clone the list, creating a new list with the same fighters.

        Args:
            name: Name for the clone (defaults to original name + suffix)
            owner: Owner of the clone (defaults to original owner)
            for_campaign: If provided, creates a campaign mode clone for this campaign
            **kwargs: Additional fields to set on the clone
        """
        if for_campaign:
            # Campaign clones keep the same name but go into campaign mode
            if not name:
                name = self.name
            kwargs["status"] = self.CAMPAIGN_MODE
            kwargs["original_list"] = self
            kwargs["campaign"] = for_campaign
            kwargs["public"] = False  # Campaign lists are always private
        else:
            # Regular clones get a suffix
            if not name:
                name = f"{self.name} (Clone)"

        if not owner:
            owner = self.owner

        values = {
            "public": self.public if for_campaign is None else False,
            "narrative": self.narrative,
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
        ordering = ["name"]

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
    legacy_content_fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="list_fighter_legacy",
        help_text="This supports a ListFighter having a Content Fighter legacy which provides access to (and costs from) the legacy fighter's equipment list.",
    )
    list = models.ForeignKey(List, on_delete=models.CASCADE, null=False, blank=False)

    # Stat overrides

    movement_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="M"
    )
    weapon_skill_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="WS"
    )
    ballistic_skill_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="BS"
    )
    strength_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="S"
    )
    toughness_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="T"
    )
    wounds_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="W"
    )
    initiative_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="I"
    )
    attacks_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="A"
    )
    leadership_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="Ld"
    )
    cool_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="Cl"
    )
    willpower_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="Wil"
    )
    intelligence_override = models.CharField(
        max_length=12, blank=True, null=True, verbose_name="Int"
    )

    # Cost

    cost_override = models.IntegerField(
        null=True,
        blank=True,
        help_text="If set, this will be base cost of this fighter.",
    )

    # Assigments

    equipment = models.ManyToManyField(
        ContentEquipment,
        through="ListFighterEquipmentAssignment",
        blank=True,
        through_fields=("list_fighter", "content_equipment"),
    )

    disabled_default_assignments = models.ManyToManyField(
        ContentFighterDefaultAssignment, blank=True
    )
    disabled_pskyer_default_powers = models.ManyToManyField(
        ContentFighterPsykerPowerDefaultAssignment, blank=True
    )

    skills = models.ManyToManyField(ContentSkill, blank=True)
    additional_rules = models.ManyToManyField(
        ContentHouseAdditionalRule,
        blank=True,
        help_text="Additional rules for this fighter. Must be from the same house as the fighter.",
    )

    # Other

    narrative = models.TextField(
        "about",
        blank=True,
        help_text="Narrative description of the Fighter: their history and how to play them.",
    )

    history = HistoricalRecords()

    @cached_property
    def content_fighter_cached(self):
        return self.content_fighter

    @cached_property
    def legacy_content_fighter_cached(self):
        return self.legacy_content_fighter

    @cached_property
    def can_take_legacy(self):
        return self.content_fighter.can_take_legacy

    @cached_property
    def equipment_list_fighter(self):
        return self.legacy_content_fighter or self.content_fighter

    @admin.display(description="Total Cost with Equipment")
    def cost_int(self):
        return self._base_cost_int + sum([e.cost_int() for e in self.assignments()])

    @cached_property
    def cost_int_cached(self):
        return self._base_cost_int + sum(
            [e.cost_int() for e in self.assignments_cached]
        )

    @cached_property
    def _base_cost_int(self):
        # Our cost can be overridden by the user...
        if self.cost_override is not None:
            return self.cost_override

        # Or if it's linked...
        if self.has_linked_fighter:
            return 0

        return self._base_cost_before_override()

    def _base_cost_before_override(self):
        # Or by the house...
        # Is this an override? Yes, but not set on the fighter itself.
        cost_override = ContentFighterHouseOverride.objects.filter(
            fighter=self.content_fighter_cached,
            house=self.list.content_house,
            cost__isnull=False,
        ).first()
        if cost_override:
            return cost_override.cost

        # But if neither of those are set, we just use the base cost from the content fighter
        return self.content_fighter_cached.cost_int()

    def base_cost_display(self):
        return f"{self._base_cost_int}¢"

    def base_cost_before_override_display(self):
        return f"{self._base_cost_before_override()}¢"

    def cost_display(self):
        return f"{self.cost_int_cached}¢"

    # Stats & rules

    @cached_property
    def _mods(self):
        # Remember: virtual and needs flattening!
        return [mod for assign in self.assignments_cached for mod in assign.mods]

    def _apply_mods(self, stat: str, value: str, mods: pylist[ContentModFighterStat]):
        for mod in mods:
            value = mod.apply(value)
        return value

    def _statmods(self, stat: str):
        """
        Get the stat mods for this fighter.
        """
        return [
            mod
            for mod in self._mods
            if isinstance(mod, ContentModFighterStat) and mod.stat == stat
        ]

    @cached_property
    def _rulemods(self):
        """
        Get the rule mods for this fighter.
        """
        return [mod for mod in self._mods if isinstance(mod, ContentModFighterRule)]

    @cached_property
    def _skillmods(self):
        """
        Get the skill mods for this fighter.
        """
        return [mod for mod in self._mods if isinstance(mod, ContentModFighterSkill)]

    @cached_property
    def statline(self) -> pylist[StatlineDisplay]:
        """
        Get the statline for this fighter.
        """
        stats = []
        for stat in self.content_fighter_cached.statline():
            input_value = stat["value"]

            # Check for overrides
            value_override = getattr(self, f"{stat['field_name']}_override", None)
            if value_override is not None:
                input_value = value_override

            # Apply the mods
            value = self._apply_mods(
                stat["field_name"],
                input_value,
                self._statmods(stat["field_name"]),
            )
            modded = value != stat["value"]
            sd = StatlineDisplay(
                name=stat["name"],
                field_name=stat["field_name"],
                classes=stat["classes"],
                highlight=stat["highlight"],
                value=value,
                modded=modded,
            )
            stats.append(sd)

        return stats

    @cached_property
    def ruleline(self):
        """
        Get the ruleline for this fighter.
        """
        rules = list(self.content_fighter_cached.rules.all())
        modded = []
        for mod in self._rulemods:
            if mod.mode == "add" and mod.rule not in rules:
                rules.append(mod.rule)
                modded.append(mod.rule)
            elif mod.mode == "remove" and mod.rule in rules:
                rules.remove(mod.rule)

        return [RulelineDisplay(rule.name, rule in modded) for rule in rules]

    # Assignments

    def assign(
        self,
        equipment,
        weapon_profiles: pylist[ContentWeaponProfile] | None = None,
        weapon_accessories: pylist[ContentWeaponAccessory] | None = None,
        from_default_assignment: ContentFighterDefaultAssignment | None = None,
        cost_override: int | None = None,
    ) -> "ListFighterEquipmentAssignment":
        """
        Assign equipment to the fighter, optionally with weapon profiles and accessories.

        The typical way things are assigned does not use this method:
        - We create a "virtual" assignment with main and profile fields
        - The data from the virtual assignment is POSTed back each time equipment is added
        - This allows us to create an instance of ListFighterEquipmentAssignment with the correct
            weapon profiles and accessories each time equipment is added.
        """
        # We create the assignment directly because Django does not use the through_defaults
        # if you .add() equipment that is already in the list, which prevents us from
        # assigning the same equipment multiple times, once with a weapon profile and once without.
        assign = ListFighterEquipmentAssignment(
            list_fighter=self, content_equipment=equipment
        )
        assign.save()

        if weapon_profiles:
            for profile in weapon_profiles:
                assign.assign_profile(profile)

        if weapon_accessories:
            for accessory in weapon_accessories:
                assign.weapon_accessories_field.add(accessory)

        if from_default_assignment:
            assign.from_default_assignment = from_default_assignment

        if cost_override is not None:
            assign.cost_override = cost_override

        assign.save()
        return assign

    def _direct_assignments(self) -> QuerySetOf["ListFighterEquipmentAssignment"]:
        return self.equipment.through.objects.filter(list_fighter=self)

    @cached_property
    def _default_assignments(self):
        return self.content_fighter_cached.default_assignments.exclude(
            Q(pk__in=self.disabled_default_assignments.all())
        )

    def assignments(self) -> pylist["VirtualListFighterEquipmentAssignment"]:
        return [
            VirtualListFighterEquipmentAssignment.from_assignment(a)
            for a in self._direct_assignments().order_by("list_fighter__name")
        ] + [
            VirtualListFighterEquipmentAssignment.from_default_assignment(a, self)
            for a in self._default_assignments
        ]

    @cached_property
    def assignments_cached(self) -> pylist["VirtualListFighterEquipmentAssignment"]:
        return self.assignments()

    @cached_property
    def has_linked_fighter(self):
        return self.linked_fighter.exists()

    def skilline(self):
        skills = set(
            list(self.content_fighter_cached.skills.all()) + list(self.skills.all())
        )
        for mod in self._skillmods:
            if mod.mode == "add" and mod.skill not in skills:
                skills.add(mod.skill)
            elif mod.mode == "remove" and mod.skill in skills:
                skills.remove(mod.skill)
        return [s.name for s in skills]

    @cached_property
    def skilline_cached(self):
        return self.skilline()

    def weapons(self):
        return [e for e in self.assignments_cached if e.is_weapon_cached]

    @cached_property
    def weapons_cached(self):
        return self.weapons()

    def wargear(self):
        return [
            e
            for e in self.assignments_cached
            if not e.is_weapon_cached and not e.is_house_additional
        ]

    @cached_property
    def wargear_cached(self):
        return self.wargear()

    def wargearline(self):
        return [e.content_equipment.name for e in self.wargear_cached]

    @cached_property
    def wargearline_cached(self):
        return self.wargearline()

    @cached_property
    def has_house_additional_gear(self):
        return (
            self.content_fighter_cached.house.restricted_equipment_categories.exists()
        )

    @cached_property
    def house_additional_gearline_display(self):
        return [
            {
                "category": cat.name,
                "id": cat.id,
                "assignments": self.house_additional_assignments(cat),
            }
            for cat in self.content_fighter_cached.house.restricted_equipment_categories.all()
        ]

    def house_additional_assignments(self, category: ContentEquipmentCategory):
        return [
            e
            for e in self.assignments_cached
            if e.is_house_additional and e.category == category.name
        ]

    def powers(self):
        """
        Get the psyker powers assigned to this fighter.
        """
        default_powers = self.psyker_default_powers()
        assigned_powers = self.psyker_assigned_powers()

        return list(default_powers + assigned_powers)

    @cached_property
    def powers_cached(self):
        return self.powers()

    def psyker_default_powers(self):
        default_powers = self.content_fighter_cached.default_psyker_powers.exclude(
            Q(pk__in=self.disabled_pskyer_default_powers.all())
        )
        return [
            VirtualListFighterPsykerPowerAssignment.from_default_assignment(p, self)
            for p in default_powers
        ]

    @cached_property
    def psyker_default_powers_cached(self):
        return self.psyker_default_powers()

    def psyker_assigned_powers(self):
        return [
            VirtualListFighterPsykerPowerAssignment.from_assignment(p)
            for p in self.psyker_powers.all()
        ]

    @cached_property
    def psyker_assigned_powers_cached(self):
        return self.psyker_assigned_powers()

    def has_overriden_cost(self):
        return self.cost_override is not None

    @cached_property
    def linked_list_fighter(self):
        return self.linked_fighter.get().list_fighter

    def toggle_default_assignment(
        self, assign: ContentFighterDefaultAssignment, enable=False
    ):
        """
        Turn off a specific default assignment for this Fighter.
        """
        exists = self.content_fighter_cached.default_assignments.contains(assign)
        already_disabled = self.disabled_default_assignments.contains(assign)
        if enable and already_disabled:
            self.disabled_default_assignments.remove(assign)
        elif not enable and exists:
            self.disabled_default_assignments.add(assign)

        self.save()

    def convert_default_assignment(
        self,
        assign: "VirtualListFighterEquipmentAssignment | ContentFighterDefaultAssignment",
    ):
        """
        Convert a default assignment to a direct assignment.
        """
        try:
            assignment: ContentFighterDefaultAssignment = self._default_assignments.get(
                id=assign.id
            )
        except ContentFighterDefaultAssignment.DoesNotExist:
            raise ValueError(
                f"Default assignment {assign} not found on {self.content_fighter}"
            )

        self.toggle_default_assignment(assignment, enable=False)
        self.assign(
            equipment=assignment.equipment,
            weapon_profiles=assignment.weapon_profiles_field.all(),
            weapon_accessories=assignment.weapon_accessories_field.all(),
            from_default_assignment=assignment,
            cost_override=0,
        )

    def clone(self, **kwargs):
        """Clone the fighter, creating a new fighter with the same equipment."""

        values = {
            "name": self.name,
            "content_fighter": self.content_fighter,
            "narrative": self.narrative,
            "list": self.list,
            "cost_override": self.cost_override,
            **kwargs,
        }

        clone = ListFighter.objects.create(
            owner=values["list"].owner,
            **values,
        )

        clone.skills.set(self.skills.all())

        for assignment in self._direct_assignments():
            if assignment.from_default_assignment is not None:
                # We don't want to clone stuff that was created from a default assignment
                # TODO: This is "safe" behaviour but not strictly correct. We should be able to
                #       to clone an assignment that was created from a default assignment correctly.
                #       Gotchas are there around linked fighters and the like.
                continue
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

        if self.legacy_content_fighter and not self.content_fighter.can_take_legacy:
            raise ValidationError(
                {
                    "legacy_content_fighter": f"Fighters of type {self.content_fighter.type} cannot take a legacy fighter.",
                }
            )

        if (
            self.legacy_content_fighter
            and not self.legacy_content_fighter.can_be_legacy
        ):
            raise ValidationError(
                {
                    "legacy_content_fighter": f"Fighters of type {self.legacy_content_fighter.type} cannot be used as the legacy fighter.",
                }
            )

    objects = ListFighterManager.from_queryset(ListFighterQuerySet)()


@receiver(post_save, sender=ListFighter, dispatch_uid="create_linked_objects")
def create_linked_objects(sender, instance, **kwargs):
    # Find the default assignments where the equipment has a fighter profile
    default_assigns = instance.content_fighter.default_assignments.exclude(
        Q(equipment__contentequipmentfighterprofile__isnull=True)
        & Q(equipment__contentequipmentequipmentprofile__isnull=True)
    )
    for assign in default_assigns:
        # Find disabled default assignments
        is_disabled = instance.disabled_default_assignments.contains(assign)

        # Find assignments on this fighter of that equipment
        exists = (
            instance._direct_assignments()
            .filter(content_equipment=assign.equipment, from_default_assignment=assign)
            .exists()
        )

        if not is_disabled and not exists:
            # Disable the default assignment and assign the equipment directly
            # This will trigger the ListFighterEquipmentAssignment logic to
            # create the linked objects
            instance.toggle_default_assignment(assign, enable=False)
            new_assign = ListFighterEquipmentAssignment(
                list_fighter=instance,
                content_equipment=assign.equipment,
                cost_override=0,
                from_default_assignment=assign,
            )
            new_assign.save()


@receiver(
    [pre_delete, post_save, m2m_changed],
    sender=ListFighter,
    dispatch_uid="update_list_cost_cache",
)
def update_list_cost_cache(sender, instance: ListFighter, **kwargs):
    instance.list.update_cost_cache()


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
        help_text="If set, this will be the cost of the base equipment of this assignment, ignoring equipment list and trading post costs",
    )

    total_cost_override = models.IntegerField(
        null=True,
        blank=True,
        help_text="If set, this will be the total cost of this assignment, ignoring profiles, accessories, and upgrades",
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

    upgrade = models.ForeignKey(
        ContentEquipmentUpgrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The upgrade that this equipment assignment is set to.",
    )

    upgrades_field = models.ManyToManyField(
        ContentEquipmentUpgrade,
        blank=True,
        related_name="fighter_equipment_assignments",
        help_text="The upgrades that this equipment assignment has.",
    )

    linked_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="linked_fighter",
        help_text="The ListFighter that this Equipment assignment is linked to (e.g. Exotic Beast, Vehicle).",
    )

    linked_equipment_parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="linked_equipment_children",
        help_text="The parent equipment assignment that this assignment is linked to.",
    )

    from_default_assignment = models.ForeignKey(
        ContentFighterDefaultAssignment,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        help_text="The default assignment that this equipment assignment was created from",
    )

    history = HistoricalRecords()

    # Cache

    @cached_property
    def content_equipment_cached(self):
        return self.content_equipment

    @cached_property
    def list_fighter_cached(self):
        return self.list_fighter

    # Information & Display

    def name(self):
        profile_name = self.weapon_profiles_names()
        return f"{self.content_equipment_cached}" + (
            f" ({profile_name})" if profile_name else ""
        )

    def is_weapon(self):
        return self.content_equipment_cached.is_weapon_cached

    def base_name(self):
        return f"{self.content_equipment_cached}"

    def __str__(self):
        return f"{self.list_fighter} – {self.name()}"

    # Profiles

    def assign_profile(self, profile: "ContentWeaponProfile"):
        """Assign a weapon profile to this equipment."""
        if profile.equipment != self.content_equipment_cached:
            raise ValueError(
                f"{profile} is not a profile for {self.content_equipment_cached}"
            )
        self.weapon_profiles_field.add(profile)

    def weapon_profiles(self):
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in self.weapon_profiles_field.all()
        ]

    @cached_property
    def weapon_profiles_cached(self):
        return self.weapon_profiles()

    def weapon_profiles_display(self):
        """Return a list of dictionaries with the weapon profiles and their costs."""
        return [
            dict(
                profile=p,
                cost_int=self.profile_cost_int(p),
                cost_display=self.profile_cost_display(p),
            )
            for p in self.weapon_profiles_cached
        ]

    def all_profiles(self) -> list["VirtualWeaponProfile"]:
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

    @cached_property
    def all_profiles_cached(self) -> list["VirtualWeaponProfile"]:
        return self.all_profiles()

    def standard_profiles(self):
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in ContentWeaponProfile.objects.filter(
                equipment=self.content_equipment, cost=0
            )
        ]

    @cached_property
    def standard_profiles_cached(self):
        return self.standard_profiles()

    def weapon_profiles_names(self):
        profile_names = [p.name for p in self.weapon_profiles_cached]
        return ", ".join(profile_names)

    # Accessories

    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    @cached_property
    def weapon_accessories_cached(self):
        return self.weapon_accessories()

    # Mods

    @cached_property
    def _mods(self):
        """
        Get the mods for this assignment.

        Mods come from:
        - the equipment itself
        - accessories
        - upgrades
        """
        accessories = self.weapon_accessories_cached
        mods = [m for a in accessories for m in a.modifiers.all()]
        mods += list(self.content_equipment_cached.modifiers.all())
        for upgrade in self.upgrades_field.all():
            mods += list(upgrade.modifiers.all())
        return mods

    # Costs

    def base_cost_int(self):
        return self._equipment_cost_with_override_cached

    @cached_property
    def base_cost_int_cached(self):
        return self.base_cost_int()

    def base_cost_display(self):
        return f"{self.base_cost_int_cached}¢"

    def weapon_profiles_cost_int(self):
        return self._profile_cost_with_override_cached

    @cached_property
    def weapon_profiles_cost_int_cached(self):
        return self.weapon_profiles_cost_int()

    def weapon_profiles_cost_display(self):
        return f"+{self.weapon_profiles_cost_int_cached}¢"

    def weapon_accessories_cost_int(self):
        return self._accessories_cost_with_override()

    @cached_property
    def weapon_accessories_cost_int_cached(self):
        return self.weapon_accessories_cost_int()

    def weapon_accessories_cost_display(self):
        return f"+{self.weapon_accessories_cost_int()}¢"

    @admin.display(description="Total Cost of Assignment")
    def cost_int(self):
        if self.has_total_cost_override():
            return self.total_cost_override

        return (
            self.base_cost_int_cached
            + self.weapon_profiles_cost_int_cached
            + self.weapon_accessories_cost_int_cached
            + self.upgrade_cost_int_cached
        )

    @cached_property
    def cost_int_cached(self):
        return self.cost_int()

    def has_total_cost_override(self):
        return self.total_cost_override is not None

    def cost_display(self):
        return f"{self.cost_int_cached}¢"

    def _equipment_cost_with_override(self):
        # The assignment can have an assigned cost which takes priority
        if self.cost_override is not None:
            return self.cost_override

        # If this is a linked assignment and is the child, then the cost is zero
        if self.linked_equipment_parent is not None:
            return 0

        if hasattr(self.content_equipment, "cost_for_fighter"):
            return self.content_equipment.cost_for_fighter_int()

        overrides = ContentFighterEquipmentListItem.objects.filter(
            # We use the "equipment list fighter" which, under the hood, picks between the
            # "legacy" content fighter, if set, or the more typical content fighter. This is for
            # Venators, which can have the Gang Legacy rule.
            fighter=self._equipment_list_fighter,
            equipment=self.content_equipment,
            # None here is very important: it means we're looking for the base equipment cost.
            weapon_profile=None,
        )
        if not overrides.exists():
            return self.content_equipment.cost_int()

        if overrides.count() > 1:
            logger.warning(
                f"Multiple overrides for {self.content_equipment} on {self.list_fighter}"
            )

        override = overrides.first()
        return override.cost_int()

    @cached_property
    def _equipment_cost_with_override_cached(self):
        return self._equipment_cost_with_override()

    def _profile_cost_with_override(self):
        profiles = self.weapon_profiles_cached
        if not profiles:
            return 0

        after_overrides = [
            self._profile_cost_with_override_for_profile(p) for p in profiles
        ]
        return sum(after_overrides)

    @cached_property
    def _profile_cost_with_override_cached(self):
        return self._profile_cost_with_override()

    def _profile_cost_with_override_for_profile(self, profile: "VirtualWeaponProfile"):
        # Cache the results of this method for each profile so we don't have to recalculate
        # by fetching the override each time.
        # TODO: There is almost certainly a utility method for this somewhere.
        if not hasattr(self, "_profile_cost_with_override_for_profile_cache"):
            self._profile_cost_with_override_for_profile_cache = {}
        else:
            try:
                return self._profile_cost_with_override_for_profile_cache[
                    profile.profile.id
                ]
            except KeyError:
                pass

        if (
            self.from_default_assignment
            and self.from_default_assignment.weapon_profiles_field.contains(
                profile.profile
            )
        ):
            # If this is a default assignment and the default assignment contains this profile,
            # then we don't need to check for an override: it's free.
            cost = 0
            self._profile_cost_with_override_for_profile_cache[profile.profile.id] = (
                cost
            )
            return cost

        if hasattr(profile.profile, "cost_for_fighter"):
            cost = profile.cost_for_fighter_int()
            self._profile_cost_with_override_for_profile_cache[profile.profile.id] = (
                cost
            )
            return cost

        try:
            override = ContentFighterEquipmentListItem.objects.get(
                # We use the "equipment list fighter" which, under the hood, picks between the
                # "legacy" content fighter, if set, or the more typical content fighter. This is for
                # Venators, which can have the Gang Legacy rule.
                fighter=self._equipment_list_fighter,
                equipment=self.content_equipment,
                weapon_profile=profile.profile,
            )
            cost = override.cost_int()
        except ContentFighterEquipmentListItem.DoesNotExist:
            cost = profile.cost_int()

        self._profile_cost_with_override_for_profile_cache[profile.profile.id] = cost
        return cost

    def profile_cost_int(self, profile):
        return self._profile_cost_with_override_for_profile(profile)

    def profile_cost_display(self, profile):
        return f"+{self.profile_cost_int(profile)}¢"

    def _accessories_cost_with_override(self):
        accessories = self.weapon_accessories_cached
        if not accessories:
            return 0

        after_overrides = [self._accessory_cost_with_override(a) for a in accessories]
        return sum(after_overrides)

    def _accessory_cost_with_override(self, accessory):
        if self.from_default_assignment:
            # If this is a default assignment and the default assignment contains this accessory,
            # then we don't need to check for an override: it's free.
            if self.from_default_assignment.weapon_accessories_field.contains(
                accessory
            ):
                return 0

        if hasattr(accessory, "cost_for_fighter"):
            return accessory.cost_for_fighter_int()

        try:
            override = ContentFighterEquipmentListWeaponAccessory.objects.get(
                # We use the "equipment list fighter" which, under the hood, picks between the
                # "legacy" content fighter, if set, or the more typical content fighter. This is for
                # Venators, which can have the Gang Legacy rule.
                fighter=self._equipment_list_fighter,
                weapon_accessory=accessory,
            )
            return override.cost_int()
        except ContentFighterEquipmentListWeaponAccessory.DoesNotExist:
            return accessory.cost_int()

    def accessory_cost_int(self, accessory):
        return self._accessory_cost_with_override(accessory)

    def accessory_cost_display(self, accessory):
        return f"+{self.accessory_cost_int(accessory)}¢"

    def upgrade_cost_int(self):
        if not self.upgrades_field.exists():
            return 0

        return sum([upgrade.cost_int() for upgrade in self.upgrades_field.all()])

    @cached_property
    def upgrade_cost_int_cached(self):
        return self.upgrade_cost_int()

    @cached_property
    def _content_fighter(self):
        return self.list_fighter.content_fighter

    @cached_property
    def _equipment_list_fighter(self):
        return self.list_fighter.equipment_list_fighter

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

        for accessory in self.weapon_accessories_field.all():
            clone.weapon_accessories_field.add(accessory)

        for upgrade in self.upgrades_field.all():
            clone.upgrades_field.add(upgrade)

        if self.total_cost_override is not None:
            clone.total_cost_override = self.total_cost_override

        clone.save()

        return clone

    def clean(self):
        for upgrade in self.upgrades_field.all():
            if upgrade.equipment != self.content_equipment:
                raise ValidationError(
                    {
                        "upgrade": f"Upgrade {upgrade} is not for equipment {self.content_equipment}"
                    }
                )

    class Meta:
        verbose_name = "Fighter Equipment Assignment"
        verbose_name_plural = "Fighter Equipment Assignments"


@receiver(
    post_save,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="create_related_objects",
)
def create_related_objects(sender, instance, **kwargs):
    equipment_fighter_profile = ContentEquipmentFighterProfile.objects.filter(
        equipment=instance.content_equipment,
    )
    # If there is a profile and we aren't already linked
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

    equipment_equipment_profile = ContentEquipmentEquipmentProfile.objects.filter(
        equipment=instance.content_equipment,
    )
    existing_linked_assignments = ListFighterEquipmentAssignment.objects.filter(
        linked_equipment_parent=instance
    )
    for profile in equipment_equipment_profile:
        equip_to_create = profile.linked_equipment
        # Don't allow us to create ourselves again
        if equip_to_create == instance.content_equipment:
            raise ValueError(
                f"Equipment {instance.content_equipment} has a equipment profile for the same equipment"
            )

        # Check if the profile is already linked to this assignment
        if existing_linked_assignments.filter(
            content_equipment=equip_to_create
        ).exists():
            continue

        ListFighterEquipmentAssignment.objects.create(
            list_fighter=instance.list_fighter,
            content_equipment=equip_to_create,
            linked_equipment_parent=instance,
        )


@receiver(
    pre_delete,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="delete_related_objects_pre_delete",
)
def delete_related_objects_pre_delete(sender, instance, **kwargs):
    for child in instance.linked_equipment_children.all():
        child.delete()


@receiver(
    post_delete,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="delete_related_objects_post_delete",
)
def delete_related_objects_post_delete(sender, instance, **kwargs):
    if instance.linked_fighter:
        instance.linked_fighter.delete()


@receiver(
    [pre_delete, post_save],
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="update_list_cache_for_assignment",
)
def update_list_cache_for_assignment(
    sender, instance: ListFighterEquipmentAssignment, **kwargs
):
    instance.list_fighter.list.update_cost_cache()


@receiver(
    m2m_changed,
    sender=ListFighterEquipmentAssignment.weapon_profiles_field.through,
    dispatch_uid="update_list_cache_for_weapon_profiles",
)
def update_list_cache_for_weapon_profiles(sender, instance, **kwargs):
    # Update list cost cache
    instance.list_fighter.list.update_cost_cache()


@receiver(
    m2m_changed,
    sender=ListFighterEquipmentAssignment.weapon_accessories_field.through,
    dispatch_uid="update_list_cache_for_weapon_accessories",
)
def update_list_cache_for_weapon_accessories(sender, instance, **kwargs):
    # Clear cached properties that depend on weapon accessories
    instance.list_fighter.list.update_cost_cache()


@receiver(
    m2m_changed,
    sender=ListFighterEquipmentAssignment.upgrades_field.through,
    dispatch_uid="update_list_cache_for_upgrades",
)
def update_list_cache_for_upgrades(sender, instance, **kwargs):
    instance.list_fighter.list.update_cost_cache()


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
            fighter=assignment.list_fighter_cached,
            equipment=assignment.content_equipment_cached,
            profiles=assignment.all_profiles_cached,
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
        return self.equipment.category.name

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

    def is_from_default_assignment(self):
        return (
            self.kind() == "assigned"
            and self._assignment.from_default_assignment is not None
        )

    @cached_property
    def is_linked(self):
        return self.kind() == "assigned" and self.linked_parent is not None

    @cached_property
    def linked_parent(self):
        return self._assignment.linked_equipment_parent

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
        # TODO: this method should almost certainly be refactored to defer to the assignment

        # Walks like duck... vs kind() ... vs polymorphism vs isinstance. Types!
        if self.has_total_cost_override():
            return self._assignment.total_cost_override

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        if isinstance(self._assignment, ListFighterEquipmentAssignment):
            # If this is a direct assignment, we can use the cost directly
            return self._assignment.cost_int()

        return (
            self.base_cost_int()
            + self._profiles_cost_int()
            + self._accessories_cost_int()
            + self._upgrade_cost_int()
        )

    def has_total_cost_override(self):
        if hasattr(self._assignment, "has_total_cost_override"):
            return self._assignment.has_total_cost_override()

        return False

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

        return self._assignment.weapon_profiles_cost_int_cached

    def _accessories_cost_int(self):
        """
        Return the integer cost for all weapon accessories.
        """
        if not self._assignment:
            # TOOO: Support fighter cost for weapon accessories
            return 0

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.weapon_accessories_cost_int_cached

    def _upgrade_cost_int(self):
        """
        Return the integer cost for the upgrade.
        """
        if not self._assignment:
            return 0

        # TODO: Support default assignment upgrades?
        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.upgrade_cost_int_cached

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

        if self._assignment.all_profiles_cached:
            return self._assignment.all_profiles_cached

        return self._assignment.all_profiles()

    @cached_property
    def all_profiles_cached(self):
        return self.all_profiles()

    def standard_profiles(self):
        """
        Return only the standard (cost=0) weapon profiles for this equipment.
        """
        if not self._assignment:
            return [profile for profile in self.profiles if profile.cost == 0]

        if self._assignment.standard_profiles_cached:
            return self._assignment.standard_profiles_cached

        return self._assignment.standard_profiles()

    @cached_property
    def standard_profiles_cached(self):
        return self.standard_profiles()

    def weapon_profiles(self) -> list["VirtualWeaponProfile"]:
        """
        Return all weapon profiles for this equipment.
        """
        if not self._assignment:
            return [profile for profile in self.profiles if profile.cost_int() > 0]

        if self._assignment.weapon_profiles_cached:
            return self._assignment.weapon_profiles_cached

        return self._assignment.weapon_profiles()

    @cached_property
    def weapon_profiles_cached(self):
        return self.weapon_profiles()

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

    @property
    def is_house_additional(self):
        return self.equipment.is_house_additional

    def is_weapon(self):
        return self.equipment.is_weapon()

    @cached_property
    def is_weapon_cached(self):
        return self.is_weapon()

    def weapon_accessories(self):
        if not self._assignment:
            return []

        return self._assignment.weapon_accessories_cached

    @cached_property
    def weapon_accessories_cached(self):
        return self.weapon_accessories()

    def weapon_accessories_display(self):
        return [
            {
                "accessory": accessory,
                "cost_int": self._weapon_accessory_cost(accessory),
                "cost_display": f"+{self._weapon_accessory_cost(accessory)}¢",
            }
            for accessory in self.weapon_accessories_cached
        ]

    @cached_property
    def weapon_accessories_display_cached(self):
        return self.weapon_accessories_display()

    def _weapon_accessory_cost(self, accessory):
        if not self._assignment:
            return accessory.cost_for_fighter_int()

        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            return 0

        return self._assignment.accessory_cost_int(accessory)

    def active_upgrade(self):
        """
        Return the active upgrade for this equipment assignment if the
        equipment is in single upgrade mode.
        """
        if not self._assignment:
            return None

        if not hasattr(self._assignment, "upgrades_field"):
            return None

        if self.equipment.upgrade_mode != ContentEquipment.UpgradeMode.SINGLE:
            return None

        return self._assignment.upgrades_field.first()

    @cached_property
    def active_upgrade_cached(self):
        return self.active_upgrade()

    def active_upgrades(self):
        """
        Return the active upgrades for this equipment assignment.
        """
        if not self._assignment:
            return None

        if not hasattr(self._assignment, "upgrades_field"):
            return None

        return self._assignment.upgrades_field.all()

    @cached_property
    def active_upgrades_cached(self):
        return self.active_upgrades()

    @cached_property
    def active_upgrades_display(self):
        """
        Return a list of dictionaries containing each upgrade and its cost display.
        """
        if not self.active_upgrades_cached:
            return []

        return [
            {
                "upgrade": upgrade,
                "name": upgrade.name,
                "cost_int": upgrade.cost_int_cached,
                "cost_display": f"+{upgrade.cost_int_cached}¢",
            }
            for upgrade in self.active_upgrades_cached
        ]

    # Note that this is about *available* upgrades, not the *active* upgrade.

    def upgrades(self) -> QuerySetOf[ContentEquipmentUpgrade]:
        if not self.equipment.upgrades:
            return []

        return self.equipment.upgrades.all()

    @cached_property
    def upgrades_cached(self):
        return self.upgrades()

    def upgrades_display(self):
        return [
            {
                "upgrade": upgrade,
                "cost_int": upgrade.cost_int_cached,
                "cost_display": f"+{upgrade.cost_int_cached}¢",
            }
            for upgrade in self.upgrades_cached
        ]

    # Mods

    @cached_property
    def mods(self):
        if not self._assignment:
            return []

        return self._assignment._mods


class ListFighterPsykerPowerAssignment(Base, Archived):
    """A ListFighterPsykerPowerAssignment is a link between a ListFighter and a Psyker Power."""

    help_text = "A ListFighterPsykerPowerAssignment is a link between a ListFighter and a Psyker Power."
    list_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Fighter",
        related_name="psyker_powers",
        help_text="The ListFighter that this psyker power assignment is linked to.",
    )
    psyker_power = models.ForeignKey(
        ContentPsykerPower,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Psyker Power",
        related_name="list_fighters",
        help_text="The ContentSkill that this assignment is linked to.",
    )

    history = HistoricalRecords()

    def name(self):
        return f"{self.psyker_power.name} ({self.psyker_power.discipline})"

    def __str__(self):
        return f"{self.list_fighter} – {self.name()}"

    def clean(self):
        # TODO: Find a way to build this generically, rather than special-casing it
        if not self.list_fighter.content_fighter.is_psyker:
            raise ValidationError(
                {
                    "list_fighter": "You can't assign a psyker power to a fighter that is not a psyker."
                }
            )

        if self.list_fighter.content_fighter.default_psyker_powers.filter(
            psyker_power=self.psyker_power
        ).exists():
            raise ValidationError(
                {
                    "psyker_power": "You can't assign a psyker power that is already assigned by default."
                }
            )

        if (
            not self.psyker_power.discipline.generic
            and not self.list_fighter.content_fighter.psyker_disciplines.filter(
                discipline=self.psyker_power.discipline
            ).exists()
        ):
            raise ValidationError(
                {
                    "psyker_power": "You can't assign a psyker power from a non-generic discipline if the fighter is not assigned that discipline."
                }
            )

    class Meta:
        verbose_name = "Fighter Psyker Power Assignment"
        verbose_name_plural = "Fighter Psyker Power Assignments"
        unique_together = ("list_fighter", "psyker_power")


@dataclass
class VirtualListFighterPsykerPowerAssignment:
    """
    A virtual container that groups a :model:`core.ListFighter` with
    :model:`content.ContentPsykerPower`.

    The cases this handles:
    * _assignment is None: Used for generating the add/edit psyker powers page: all the "potential"
        assignments for a fighter.
    * _assignment is a ContentFighterPsykerPowerDefaultAssignment: Used to abstract over the fighter's default
        psyker power assignments so that we can treat them as if they were ListFighterPsykerPowerAssignments.
    * _assignment is a ListFighterPsykerPowerAssignment: Used to abstract over the fighter's specific
        psyker power assignments so that we can handle the above two cases.
    """

    fighter: ListFighter
    psyker_power: ContentPsykerPower
    _assignment: (
        Union[
            ListFighterPsykerPowerAssignment, ContentFighterPsykerPowerDefaultAssignment
        ]
        | None
    ) = None

    @classmethod
    def from_assignment(cls, assignment: ListFighterPsykerPowerAssignment):
        return cls(
            fighter=assignment.list_fighter,
            psyker_power=assignment.psyker_power,
            _assignment=assignment,
        )

    @classmethod
    def from_default_assignment(
        cls,
        assignment: ContentFighterPsykerPowerDefaultAssignment,
        fighter: ListFighter,
    ):
        return cls(
            fighter=fighter,
            psyker_power=assignment.psyker_power,
            _assignment=assignment,
        )

    def id(self):
        if not self._assignment:
            return uuid.uuid4()

        return self._assignment.id

    def name(self):
        if not self._assignment:
            return f"{self.psyker_power.name}"

        return self._assignment.name()

    def kind(self):
        if not self._assignment:
            return "virtual"

        if isinstance(self._assignment, ContentFighterPsykerPowerDefaultAssignment):
            return "default"

        return "assigned"

    @cached_property
    def disc(self):
        return f"{self.psyker_power.discipline.name}"
