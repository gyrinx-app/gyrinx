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
    ContentAttributeValue,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
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
    ContentStatlineTypeStat,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    RulelineDisplay,
    StatlineDisplay,
    VirtualWeaponProfile,
)
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.history_mixin import HistoryMixin
from gyrinx.models import (
    Archived,
    Base,
    FighterCategoryChoices,
    QuerySetOf,
    format_cost_display,
)

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

    theme_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Theme color for this gang in hex format (e.g., #FF0000).",
        validators=[
            validators.RegexValidator(
                r"^#(?:[0-9a-fA-F]{3}){1,2}$|^$",
                "Enter a valid hex color code (e.g., #FF0000) or leave empty.",
            )
        ],
    )

    # Credit tracking
    credits_current = models.PositiveIntegerField(
        default=0,
        help_text="Current credits available",
    )
    credits_earned = models.PositiveIntegerField(
        default=0,
        help_text="Total credits ever earned",
    )

    # Gang attributes (Alignment, Alliance, Affiliation, etc.)
    attributes = models.ManyToManyField(
        ContentAttributeValue,
        through="ListAttributeAssignment",
        blank=True,
        through_fields=("list", "attribute_value"),
        help_text="Gang attributes like Alignment, Alliance, Affiliation",
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost_int(self):
        fighters_cost = sum([f.cost_int() for f in self.fighters()])
        # Include current credits in total cost
        return fighters_cost + self.credits_current

    @cached_property
    def cost_int_cached(self):
        cache = caches["core_list_cache"]
        cache_key = self.cost_cache_key()
        cached = cache.get(cache_key)
        if cached:
            return cached

        fighters_cost = sum([f.cost_int_cached for f in self.fighters_cached])
        # Include current credits in total cost
        cost = fighters_cost + self.credits_current
        cache.set(cache_key, cost, settings.CACHE_LIST_TTL)
        return cost

    def cost_display(self):
        return format_cost_display(self.cost_int_cached)

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
    def active_fighters(self) -> QuerySetOf["ListFighter"]:
        """Get all fighters that could participate in a battle."""
        return self.fighters().filter(archived=False, content_fighter__is_stash=False)

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
        # Also clear the cached property from the instance
        if "cost_int_cached" in self.__dict__:
            del self.__dict__["cost_int_cached"]

    def ensure_stash(self, owner=None):
        """Ensure this list has a stash fighter, creating one if needed.

        Args:
            owner: Owner for the stash fighter (defaults to list owner)

        Returns:
            ListFighter: The stash fighter for this list
        """
        # Check if there's already a stash fighter
        existing_stash = self.listfighter_set.filter(
            content_fighter__is_stash=True
        ).first()

        if existing_stash:
            return existing_stash

        if not owner:
            owner = self.owner

        # Get or create a stash ContentFighter for this house
        stash_fighter, created = ContentFighter.objects.get_or_create(
            house=self.content_house,
            is_stash=True,
            defaults={
                "type": "Stash",
                "category": FighterCategoryChoices.STASH,
                "base_cost": 0,
            },
        )

        # Create the stash ListFighter
        new_stash = ListFighter.objects.create(
            name="Stash",
            content_fighter=stash_fighter,
            list=self,
            owner=owner,
        )

        return new_stash

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
        else:
            # Regular clones get a suffix
            if not name:
                name = f"{self.name} (Clone)"

        if not owner:
            owner = self.owner

        values = {
            "public": self.public,
            "narrative": self.narrative,
            "theme_color": self.theme_color,
            **kwargs,
        }

        clone = List.objects.create(
            name=name,
            content_house=self.content_house,
            owner=owner,
            **values,
        )

        # Clone fighters, but skip linked fighters and stash fighters
        for fighter in self.fighters():
            # Skip if this fighter is linked to an equipment assignment
            is_linked = (
                hasattr(fighter, "linked_fighter") and fighter.linked_fighter.exists()
            )
            # Skip if this is a stash fighter
            is_stash = fighter.content_fighter.is_stash

            if not is_linked and not is_stash:
                fighter.clone(list=clone)

        # Add a stash fighter if cloning for a campaign
        if for_campaign:
            new_stash = clone.ensure_stash(owner=owner)

            # Clone equipment from original stash if it exists
            original_stash = self.listfighter_set.filter(
                content_fighter__is_stash=True
            ).first()

            if original_stash:
                # Clone all equipment assignments from the original stash
                for assignment in original_stash._direct_assignments():
                    assignment.clone(list_fighter=new_stash)

        # Clone attributes
        for attribute_assignment in self.listattributeassignment_set.all():
            ListAttributeAssignment.objects.create(
                list=clone,
                attribute_value=attribute_assignment.attribute_value,
            )

        return clone

    class Meta:
        verbose_name = "List"
        verbose_name_plural = "Lists"
        ordering = ["name"]

    def __str__(self):
        return self.name


@receiver(
    [post_save, m2m_changed],
    sender=List,
    dispatch_uid="update_list_cost_cache_from_list_change",
)
def update_list_cost_cache_from_list_change(sender, instance: List, **kwargs):
    instance.update_cost_cache()


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
                                linked_fighter__list_fighter__content_fighter__category=category,
                                # Only consider linked fighters that are not stash fighters
                                linked_fighter__list_fighter__content_fighter__is_stash=False,
                            ),
                            then=index,
                        )
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
                    default=99,
                ),
                _sort_key=Case(
                    # If this is a beast linked to a fighter, sort after the owner
                    When(
                        _is_linked=True,
                        content_fighter__category=FighterCategoryChoices.EXOTIC_BEAST,
                        then=Concat("linked_fighter__list_fighter__name", Value("~2")),
                    ),
                    # If this is a vehicle linked to a fighter, sort with the parent but come first
                    When(
                        _is_linked=True,
                        content_fighter__category=FighterCategoryChoices.VEHICLE,
                        then=Concat("linked_fighter__list_fighter__name", Value("~0")),
                    ),
                    # Default: regular fighters sort by their own name with a middle priority
                    default=Concat(F("name"), Value("~1")),
                    output_field=models.CharField(),
                ),
            )
            .order_by(
                "list",
                Case(
                    # First sort: captured/sold fighters (2), then dead fighters (1), then active (0)
                    When(
                        Q(capture_info__isnull=False)
                        & (
                            Q(capture_info__sold_to_guilders=True)
                            | Q(capture_info__sold_to_guilders=False)
                        ),
                        then=2,
                    ),
                    When(injury_state="dead", then=1),
                    default=0,
                ),
                "_category_order",
                "_sort_key",
            )
        )

    def with_group_keys(self):
        """
        Annotate fighters with group keys for display grouping.

        - Vehicles and their crew share the same group key (the crew's ID)
        - Vehicles linked to stash use their own ID (don't group with stash)
        - All other fighters have unique group keys (their own ID)
        """
        return self.get_queryset().annotate(
            group_key=Case(
                # If this fighter is linked to stash and is a vehicle, use own ID
                When(
                    linked_fighter__isnull=False,
                    content_fighter__category=FighterCategoryChoices.VEHICLE,
                    linked_fighter__list_fighter__content_fighter__is_stash=True,
                    then=F("id"),
                ),
                # If this fighter is linked, and we are a vehicle, use the linked fighter's id
                When(
                    linked_fighter__isnull=False,
                    # TODO: De-special-case this, so that we check something like
                    #       content_fighter__category__groups_with_linked_fighter
                    content_fighter__category=FighterCategoryChoices.VEHICLE,
                    then=F("linked_fighter__list_fighter__id"),
                ),
                # Default: use fighter's own ID
                default=F("id"),
                output_field=models.UUIDField(),
            ),
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

    # Fighter image/portrait
    image = models.ImageField(
        upload_to="fighter-images/",
        blank=True,
        null=True,
        help_text="Fighter portrait or image (appears in Info section)",
    )

    # Save roll field
    save_roll = models.CharField(
        max_length=10,
        blank=True,
        help_text="Fighter's typical save roll (e.g. '5+' or '4+ inv')",
    )

    # Private notes (only visible to list owner)
    private_notes = models.TextField(
        blank=True,
        help_text="Notes about the fighter (only visible to you)",
    )

    # Injury state choices
    ACTIVE = "active"
    RECOVERY = "recovery"
    CONVALESCENCE = "convalescence"
    DEAD = "dead"

    INJURY_STATE_CHOICES = [
        (ACTIVE, "Active"),
        (RECOVERY, "Recovery"),
        (CONVALESCENCE, "Convalescence"),
        (DEAD, "Dead"),
    ]

    injury_state = models.CharField(
        max_length=20,
        choices=INJURY_STATE_CHOICES,
        default=ACTIVE,
        help_text="The current injury state of the fighter in campaign mode.",
    )

    # Experience tracking
    xp_current = models.PositiveIntegerField(
        default=0,
        help_text="Current XP available to spend",
    )
    xp_total = models.PositiveIntegerField(
        default=0,
        help_text="Total XP ever earned",
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

    @cached_property
    def equipment_list_fighters(self):
        """
        Return a list of fighters whose equipment lists should be considered.
        When a legacy fighter exists, returns both legacy and base fighters
        to allow combining their equipment lists.
        """
        if self.legacy_content_fighter:
            return [self.legacy_content_fighter, self.content_fighter]
        return [self.content_fighter]

    @cached_property
    def is_stash(self):
        """
        Returns True if this fighter is a stash fighter.
        """
        return self.content_fighter_cached.is_stash

    @cached_property
    def is_vehicle(self):
        """
        Returns True if this fighter is a vehicle.
        """
        return self.content_fighter_cached.is_vehicle

    @cached_property
    def proximal_demonstrative(self) -> str:
        """
        Returns a user-friendly proximal demonstrative for this fighter (e.g., "this" or "that").
        """
        if self.is_stash:
            return "The stash"

        if self.is_vehicle:
            return "The vehicle"

        return "This fighter"

    @cached_property
    def fully_qualified_name(self) -> str:
        """
        Returns the fully qualified name of the fighter, including type and category.
        """
        if self.is_stash:
            return "Stash"
        cf = self.content_fighter_cached
        return f"{self.name} - {cf.name()}"

    @admin.display(description="Total Cost with Equipment")
    def cost_int(self):
        # Captured or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            return 0

        # Include advancement cost increases
        advancement_cost = (
            self.advancements.aggregate(total=models.Sum("cost_increase"))["total"] or 0
        )
        return (
            self._base_cost_int
            + advancement_cost
            + sum([e.cost_int() for e in self.assignments()])
        )

    @cached_property
    def cost_int_cached(self):
        # Captured or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            return 0

        # Include advancement cost increases
        advancement_cost = (
            self.advancements.aggregate(total=models.Sum("cost_increase"))["total"] or 0
        )
        return (
            self._base_cost_int
            + advancement_cost
            + sum([e.cost_int() for e in self.assignments_cached])
        )

    @cached_property
    def _base_cost_int(self):
        # Captured or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            return 0

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
        return format_cost_display(self._base_cost_int)

    def base_cost_before_override_display(self):
        return format_cost_display(self._base_cost_before_override())

    def cost_display(self):
        return format_cost_display(self.cost_int_cached)

    # Stats & rules

    @cached_property
    def _mods(self):
        # Remember: virtual and needs flattening!
        equipment_mods = [
            mod for assign in self.assignments_cached for mod in assign.mods
        ]

        # Add injury mods if in campaign mode
        injury_mods = []
        if self.list.is_campaign_mode:
            for injury in self.injuries.select_related("injury").prefetch_related(
                "injury__modifiers"
            ):
                injury_mods.extend(injury.injury.modifiers.all())

        return equipment_mods + injury_mods

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

        # Check if the fighter has a custom statline
        has_custom_statline = hasattr(self.content_fighter_cached, "custom_statline")

        # Get stat overrides for this fighter
        stat_overrides = {}
        if has_custom_statline and self.stat_overrides.exists():
            stat_overrides = {
                override.content_stat.field_name: override.value
                for override in self.stat_overrides.select_related("content_stat")
            }

        for stat in self.content_fighter_cached.statline():
            input_value = stat["value"]

            # Check for overrides
            if has_custom_statline and stat["field_name"] in stat_overrides:
                # Use ListFighterStatOverride if we have a custom statline
                input_value = stat_overrides[stat["field_name"]]
            else:
                # Fall back to legacy _override fields
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
    def has_linked_fighter(self: "ListFighter") -> bool:
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
        return sorted(
            [e for e in self.assignments_cached if e.is_weapon_cached],
            key=lambda e: e.name(),
        )

    @cached_property
    def weapons_cached(self):
        return self.weapons()

    def wargear(self):
        # For stash fighters, show all non-weapon gear regardless of restrictions
        if self.is_stash:
            return [
                e
                for e in self.assignments_cached
                if not e.is_weapon_cached and not e.is_house_additional
            ]

        # Get categories that have fighter restrictions
        restricted_category_ids = (
            ContentEquipmentCategoryFighterRestriction.objects.values_list(
                "equipment_category_id", flat=True
            ).distinct()
        )

        return [
            e
            for e in self.assignments_cached
            if not e.is_weapon_cached
            and not e.is_house_additional
            and e.content_equipment.category_id not in restricted_category_ids
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
        gearlines = []
        for (
            cat
        ) in self.content_fighter_cached.house.restricted_equipment_categories.all():
            assignments = self.house_additional_assignments(cat)
            # Check if this category should be visible
            if cat.visible_only_if_in_equipment_list:
                # Only show if the fighter has equipment in this category
                # Check both direct assignments and equipment list items
                has_equipment_in_category = False

                # Check if any assignments exist for this category
                if assignments:
                    has_equipment_in_category = True
                else:
                    # Check equipment list items for this fighter
                    equipment_list_items = (
                        ContentFighterEquipmentListItem.objects.filter(
                            fighter__in=self.equipment_list_fighters,
                            equipment__category=cat,
                        ).exists()
                    )
                    if equipment_list_items:
                        has_equipment_in_category = True

                # Skip this category if no equipment found
                if not has_equipment_in_category:
                    continue

            gearlines.append(
                {
                    "category": cat.name,
                    "id": cat.id,
                    "assignments": assignments,
                    "filter": "equipment-list"
                    if cat.visible_only_if_in_equipment_list
                    else "all",
                }
            )

        return gearlines

    def house_additional_assignments(self, category: ContentEquipmentCategory):
        return [
            e
            for e in self.assignments_cached
            if e.is_house_additional and e.category == category.name
        ]

    @cached_property
    def has_category_restricted_gear(self):
        """Check if this fighter has access to any category-restricted equipment."""

        # Stash fighters can see all categories
        if self.is_stash:
            return ContentEquipmentCategoryFighterRestriction.objects.exists()

        fighter_category = self.content_fighter_cached.category
        return ContentEquipmentCategoryFighterRestriction.objects.filter(
            fighter_category=fighter_category
        ).exists()

    @cached_property
    def category_restricted_gearline_display(self):
        """Returns equipment categories restricted to this fighter's category."""

        gearlines = []
        fighter_category = self.content_fighter_cached.category

        # Get all categories restricted to this fighter's category
        # Stash fighters can see all restricted categories
        if self.is_stash:
            restricted_categories = ContentEquipmentCategory.objects.filter(
                fighter_restrictions__isnull=False
            ).distinct()
        else:
            restricted_categories = ContentEquipmentCategory.objects.filter(
                fighter_restrictions__fighter_category=fighter_category
            ).distinct()

        for cat in restricted_categories:
            assignments = self.category_restricted_assignments(cat)
            # Check if this category should be visible
            if cat.visible_only_if_in_equipment_list:
                # Only show if the fighter has equipment in this category
                has_equipment_in_category = False

                # Check if any assignments exist for this category
                if assignments:
                    has_equipment_in_category = True
                else:
                    # Check equipment list items for this fighter
                    equipment_list_items = (
                        ContentFighterEquipmentListItem.objects.filter(
                            fighter=self.equipment_list_fighter, equipment__category=cat
                        ).exists()
                    )
                    if equipment_list_items:
                        has_equipment_in_category = True

                # Skip this category if no equipment found
                if not has_equipment_in_category:
                    continue

            # Get limit for this category and fighter if it exists
            from gyrinx.content.models import ContentFighterEquipmentCategoryLimit

            limit_obj = ContentFighterEquipmentCategoryLimit.objects.filter(
                fighter=self.content_fighter_cached, equipment_category=cat
            ).first()

            # Build category display string with limit if applicable
            category_display = cat.name
            category_limit = ""
            # If there's a limit, show current count and limit
            if limit_obj:
                current_count = len(assignments)
                category_display = f"{cat.name}"
                category_limit = f"({current_count}/{limit_obj.limit})"

            gearlines.append(
                {
                    "category": category_display,
                    "category_limit": category_limit,
                    "id": cat.id,
                    "assignments": assignments,
                    "filter": "equipment-list"
                    if cat.visible_only_if_in_equipment_list
                    else "all",
                }
            )

        return gearlines

    def category_restricted_assignments(self, category: ContentEquipmentCategory):
        """Get assignments for a category-restricted equipment category."""
        return [
            e
            for e in self.assignments_cached
            if e.category == category.name
            # Check both house AND category restrictions (AND rule)
            and (
                not e.is_house_additional
                or (
                    e.is_house_additional
                    and self.content_fighter_cached.house
                    in category.restricted_to.all()
                )
            )
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

    @property
    def is_psyker(self):
        """
        Check if this fighter is a psyker by examining their full rules list
        including modifications from equipment and injuries.
        """
        # Get the full list of rules after modifications
        rules = self.ruleline

        # Check if any rule indicates the fighter is a psyker
        psyker_rules = {"psyker", "non-sanctioned psyker", "sanctioned psyker"}
        return any(rule.value.lower() in psyker_rules for rule in rules)

    @property
    def should_have_zero_cost(self):
        """Check if this fighter should contribute 0 to gang total cost."""
        return self.is_captured or self.is_sold_to_guilders

    def has_overriden_cost(self):
        return self.cost_override is not None or self.should_have_zero_cost

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
            "legacy_content_fighter": self.legacy_content_fighter,
            "narrative": self.narrative,
            "list": self.list,
            "cost_override": self.cost_override,
            "movement_override": self.movement_override,
            "weapon_skill_override": self.weapon_skill_override,
            "ballistic_skill_override": self.ballistic_skill_override,
            "strength_override": self.strength_override,
            "toughness_override": self.toughness_override,
            "wounds_override": self.wounds_override,
            "initiative_override": self.initiative_override,
            "attacks_override": self.attacks_override,
            "leadership_override": self.leadership_override,
            "cool_override": self.cool_override,
            "willpower_override": self.willpower_override,
            "intelligence_override": self.intelligence_override,
            "xp_current": self.xp_current,
            "xp_total": self.xp_total,
            **kwargs,
        }

        clone = ListFighter.objects.create(
            owner=values["list"].owner,
            **values,
        )

        # Clone ManyToMany relationships
        clone.skills.set(self.skills.all())
        clone.additional_rules.set(self.additional_rules.all())

        # Don't clone disabled default assignments if they've been converted to direct assignments
        disabled_defaults_to_clone = []
        for disabled_default in self.disabled_default_assignments.all():
            # Check if this disabled default has been converted to a direct assignment
            has_direct_assignment = (
                self._direct_assignments()
                .filter(
                    content_equipment=disabled_default.equipment,
                    from_default_assignment=disabled_default,
                )
                .exists()
            )
            if not has_direct_assignment:
                disabled_defaults_to_clone.append(disabled_default)

        clone.disabled_default_assignments.set(disabled_defaults_to_clone)
        clone.disabled_pskyer_default_powers.set(
            self.disabled_pskyer_default_powers.all()
        )

        # Don't clone equipment assignments that were converted from default assignments
        for assignment in self._direct_assignments():
            if assignment.from_default_assignment is not None:
                # Skip assignments that were converted from default assignments
                # The clone will get these as default assignments instead
                continue
            assignment.clone(list_fighter=clone)

        # Clone psyker power assignments
        for power_assignment in self.psyker_powers.all():
            ListFighterPsykerPowerAssignment.objects.create(
                list_fighter=clone,
                psyker_power=power_assignment.psyker_power,
            )

        # Clone advancements
        for advancement in self.advancements.all():
            # Use Django model instance copying
            advancement.pk = None  # Clear primary key
            advancement.fighter = clone  # Set to the new fighter
            advancement.campaign_action = None  # Clear campaign action reference
            advancement.save()

        return clone

    @property
    def archive_with(self):
        return ListFighter.objects.filter(linked_fighter__list_fighter=self)

    @property
    def is_captured(self):
        """Check if this fighter is currently captured."""
        return hasattr(self, "capture_info") and not self.capture_info.sold_to_guilders

    @property
    def is_sold_to_guilders(self):
        """Check if this fighter has been sold to guilders."""
        return hasattr(self, "capture_info") and self.capture_info.sold_to_guilders

    @property
    def captured_state(self):
        """Return the capture state of the fighter."""
        if not hasattr(self, "capture_info"):
            return None
        elif self.capture_info.sold_to_guilders:
            return "sold"
        else:
            return "captured"

    def can_participate(self):
        """Check if the fighter can participate in battles."""
        # Dead fighters can't participate
        if self.injury_state == self.DEAD:
            return False
        # Captured or sold fighters can't participate for their original gang
        if self.is_captured or self.is_sold_to_guilders:
            return False
        # Recovery and convalescence fighters can't participate
        if self.injury_state in [self.RECOVERY, self.CONVALESCENCE]:
            return False
        return True

    def has_info_content(self):
        """Check if the fighter has any content in the Info tab fields."""
        return bool(self.image or self.save_roll or self.private_notes)

    def has_lore_content(self):
        """Check if the fighter has any content in the Lore tab."""
        return bool(self.narrative)

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

        # Check if this is a stash fighter and if there's already one in the list
        if self.content_fighter.is_stash:
            existing_stash = (
                ListFighter.objects.filter(
                    list=self.list,
                    content_fighter__is_stash=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if existing_stash:
                raise ValidationError("Each list can only have one stash fighter.")

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


class ListFighterEquipmentAssignment(HistoryMixin, Base, Archived):
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
        return f"{self.list_fighter} – {self.base_name()}"

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
        return format_cost_display(self.base_cost_int_cached)

    def weapon_profiles_cost_int(self):
        return self._profile_cost_with_override_cached

    @cached_property
    def weapon_profiles_cost_int_cached(self):
        return self.weapon_profiles_cost_int()

    def weapon_profiles_cost_display(self):
        return format_cost_display(self.weapon_profiles_cost_int_cached, show_sign=True)

    def weapon_accessories_cost_int(self):
        return self._accessories_cost_with_override()

    @cached_property
    def weapon_accessories_cost_int_cached(self):
        return self.weapon_accessories_cost_int()

    def weapon_accessories_cost_display(self):
        return format_cost_display(self.weapon_accessories_cost_int(), show_sign=True)

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
        return format_cost_display(self.cost_int_cached)

    def _equipment_cost_with_override(self):
        # The assignment can have an assigned cost which takes priority
        if self.cost_override is not None:
            return self.cost_override

        # If this is a linked assignment and is the child, then the cost is zero
        if self.linked_equipment_parent is not None:
            return 0

        if hasattr(self.content_equipment, "cost_for_fighter"):
            return self.content_equipment.cost_for_fighter_int()

        # Get all fighters whose equipment lists we should check
        fighters = self.list_fighter.equipment_list_fighters

        overrides = ContentFighterEquipmentListItem.objects.filter(
            # Check equipment lists from both legacy and base fighters
            fighter__in=fighters,
            equipment=self.content_equipment,
            # None here is very important: it means we're looking for the base equipment cost.
            weapon_profile=None,
        )
        if not overrides.exists():
            return self.content_equipment.cost_int()

        # If there are multiple overrides (from legacy and base), prefer legacy
        if overrides.count() > 1:
            # Log warning if there are multiple overrides but only one fighter (shouldn't happen normally)
            if len(fighters) == 1:
                logger.warning(
                    f"Multiple overrides for {self.content_equipment} on {self.list_fighter}"
                )

            # If we have a legacy fighter, try to get the legacy override first
            if self.list_fighter.legacy_content_fighter:
                legacy_override = overrides.filter(
                    fighter=self.list_fighter.legacy_content_fighter
                ).first()
                if legacy_override:
                    return legacy_override.cost_int()

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

        # Get all fighters whose equipment lists we should check
        fighters = self.list_fighter.equipment_list_fighters

        overrides = ContentFighterEquipmentListItem.objects.filter(
            fighter__in=fighters,
            equipment=self.content_equipment,
            weapon_profile=profile.profile,
        )

        if overrides.exists():
            # If there are multiple overrides (from legacy and base), prefer legacy
            if overrides.count() > 1 and self.list_fighter.legacy_content_fighter:
                legacy_override = overrides.filter(
                    fighter=self.list_fighter.legacy_content_fighter
                ).first()
                if legacy_override:
                    cost = legacy_override.cost_int()
                else:
                    cost = overrides.first().cost_int()
            else:
                cost = overrides.first().cost_int()
        else:
            cost = profile.cost_int()

        self._profile_cost_with_override_for_profile_cache[profile.profile.id] = cost
        return cost

    def profile_cost_int(self, profile):
        return self._profile_cost_with_override_for_profile(profile)

    def profile_cost_display(self, profile):
        return format_cost_display(self.profile_cost_int(profile), show_sign=True)

    def _accessories_cost_with_override(self):
        accessories = self.weapon_accessories_cached
        if not accessories:
            return 0

        after_overrides = [self._accessory_cost_with_override(a) for a in accessories]
        return sum(after_overrides)

    def _accessory_cost_with_override(self, accessory: "ContentWeaponAccessory"):
        if self.from_default_assignment:
            # If this is a default assignment and the default assignment contains this accessory,
            # then we don't need to check for an override: it's free.
            if self.from_default_assignment.weapon_accessories_field.contains(
                accessory
            ):
                return 0

        # Check for cost expression first, as it takes precedence over simple cost overrides
        if hasattr(accessory, "cost_expression") and accessory.cost_expression:
            weapon_base_cost = self.base_cost_int_cached
            return accessory.calculate_cost_for_weapon(weapon_base_cost)

        if hasattr(accessory, "cost_for_fighter"):
            return accessory.cost_for_fighter_int()

        # Get all fighters whose equipment lists we should check
        fighters = self.list_fighter.equipment_list_fighters

        overrides = ContentFighterEquipmentListWeaponAccessory.objects.filter(
            fighter__in=fighters,
            weapon_accessory=accessory,
        )

        if overrides.exists():
            # If there are multiple overrides (from legacy and base), prefer legacy
            if overrides.count() > 1 and self.list_fighter.legacy_content_fighter:
                legacy_override = overrides.filter(
                    fighter=self.list_fighter.legacy_content_fighter
                ).first()
                if legacy_override:
                    return legacy_override.cost_int()
            return overrides.first().cost_int()
        else:
            return accessory.cost_int()

    def accessory_cost_int(self, accessory):
        return self._accessory_cost_with_override(accessory)

    def accessory_cost_display(self, accessory):
        return format_cost_display(self.accessory_cost_int(accessory), show_sign=True)

    def _upgrade_cost_with_override(self, upgrade):
        """Calculate upgrade cost with fighter-specific overrides, respecting cumulative costs."""
        # For MULTI mode, just return the individual cost (with override if present)
        if upgrade.equipment.upgrade_mode == ContentEquipment.UpgradeMode.MULTI:
            if hasattr(upgrade, "cost_for_fighter"):
                return upgrade.cost_for_fighter

            # Get all fighters whose equipment lists we should check
            fighters = self.list_fighter.equipment_list_fighters

            overrides = ContentFighterEquipmentListUpgrade.objects.filter(
                fighter__in=fighters,
                upgrade=upgrade,
            )

            if overrides.exists():
                # If there are multiple overrides (from legacy and base), prefer legacy
                if overrides.count() > 1 and self.list_fighter.legacy_content_fighter:
                    legacy_override = overrides.filter(
                        fighter=self.list_fighter.legacy_content_fighter
                    ).first()
                    if legacy_override:
                        return legacy_override.cost_int()
                return overrides.first().cost_int()
            else:
                return upgrade.cost

        # For SINGLE mode, calculate cumulative cost with overrides
        # Get all upgrades up to this position
        upgrades = upgrade.equipment.upgrades.filter(
            position__lte=upgrade.position
        ).order_by("position")

        # Get all fighters whose equipment lists we should check
        fighters = self.list_fighter.equipment_list_fighters

        cumulative_cost = 0
        for u in upgrades:
            # Check for fighter-specific override
            overrides = ContentFighterEquipmentListUpgrade.objects.filter(
                fighter__in=fighters,
                upgrade=u,
            )

            if overrides.exists():
                # If there are multiple overrides (from legacy and base), prefer legacy
                if overrides.count() > 1 and self.list_fighter.legacy_content_fighter:
                    legacy_override = overrides.filter(
                        fighter=self.list_fighter.legacy_content_fighter
                    ).first()
                    if legacy_override:
                        cumulative_cost += legacy_override.cost_int()
                    else:
                        cumulative_cost += overrides.first().cost_int()
                else:
                    cumulative_cost += overrides.first().cost_int()
            else:
                cumulative_cost += u.cost

        return cumulative_cost

    def upgrade_cost_int(self):
        if not self.upgrades_field.exists():
            return 0

        return sum(
            [
                self._upgrade_cost_with_override(upgrade)
                for upgrade in self.upgrades_field.all()
            ]
        )

    @cached_property
    def upgrade_cost_int_cached(self):
        return self.upgrade_cost_int()

    def upgrade_cost_display(self, upgrade: ContentEquipmentUpgrade):
        return format_cost_display(
            self._upgrade_cost_with_override(upgrade), show_sign=True
        )

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
    [post_delete, post_save],
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="update_list_cache_for_assignment",
)
def update_list_cache_for_assignment(
    sender, instance: ListFighterEquipmentAssignment, **kwargs
):
    # Clear the fighter's cached properties that depend on assignments
    fighter = instance.list_fighter
    for prop in ["cost_int_cached", "assignments_cached"]:
        if prop in fighter.__dict__:
            del fighter.__dict__[prop]
    # Update the list's cost cache (which also clears its cached property)
    fighter.list.update_cost_cache()


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
        return format_cost_display(self.base_cost_int())

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
        return format_cost_display(self.cost_int())

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
                "cost_display": format_cost_display(
                    self._weapon_profile_cost(profile), show_sign=True
                ),
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
                "cost_display": format_cost_display(
                    self._weapon_accessory_cost(accessory), show_sign=True
                ),
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

        # Get the first upgrade with fighter-specific cost override
        equipment_list_fighter = self.fighter.equipment_list_fighter
        return self._assignment.upgrades_field.with_cost_for_fighter(
            equipment_list_fighter
        ).first()

    @cached_property
    def active_upgrade_cached(self):
        return self.active_upgrade()

    @cached_property
    def active_upgrade_cost_int(self):
        """
        Return the cumulative cost for the active upgrade, respecting fighter-specific overrides.
        """
        if not self.active_upgrade_cached:
            return 0
        return self._calculate_cumulative_upgrade_cost(self.active_upgrade_cached)

    @cached_property
    def active_upgrade_cost_display(self):
        """
        Return the formatted cost display for the active upgrade.
        """
        return format_cost_display(self.active_upgrade_cost_int, show_sign=True)

    def active_upgrades(self):
        """
        Return the active upgrades for this equipment assignment.
        """
        if not self._assignment:
            return None

        if not hasattr(self._assignment, "upgrades_field"):
            return None

        # Get upgrades with fighter-specific cost overrides
        equipment_list_fighter = self.fighter.equipment_list_fighter
        return self._assignment.upgrades_field.with_cost_for_fighter(
            equipment_list_fighter
        ).all()

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
                "cost_int": self._calculate_cumulative_upgrade_cost(upgrade),
                "cost_display": format_cost_display(
                    self._calculate_cumulative_upgrade_cost(upgrade), show_sign=True
                ),
            }
            for upgrade in self.active_upgrades_cached
        ]

    # Note that this is about *available* upgrades, not the *active* upgrade.

    def upgrades(self) -> QuerySetOf[ContentEquipmentUpgrade]:
        if not self.equipment.upgrades:
            return []

        # Use equipment list fighter for overrides (handles legacy fighters)
        equipment_list_fighter = self.fighter.equipment_list_fighter
        return self.equipment.upgrades.with_cost_for_fighter(equipment_list_fighter)

    @cached_property
    def upgrades_cached(self):
        return self.upgrades()

    def _calculate_cumulative_upgrade_cost(self, upgrade):
        """Calculate cumulative cost for an upgrade with fighter-specific overrides."""
        # For MULTI mode, just return the individual cost
        if upgrade.equipment.upgrade_mode == ContentEquipment.UpgradeMode.MULTI:
            return getattr(upgrade, "cost_for_fighter", upgrade.cost)

        # For SINGLE mode, calculate cumulative cost with overrides
        cumulative_cost = 0

        # Get all upgrades up to this position
        for u in self.upgrades_cached:
            if u.position > upgrade.position:
                break
            # Use cost_for_fighter if available (already annotated by with_cost_for_fighter)
            cumulative_cost += getattr(u, "cost_for_fighter", u.cost)

        return cumulative_cost

    def upgrades_display(self):
        return [
            {
                "upgrade": upgrade,
                "cost_int": self._calculate_cumulative_upgrade_cost(upgrade),
                "cost_display": format_cost_display(
                    self._calculate_cumulative_upgrade_cost(upgrade),
                    show_sign=True,
                ),
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
        if not self.list_fighter.is_psyker:
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


class ListFighterInjury(AppBase):
    """Track injuries for fighters in campaign mode."""

    help_text = "Tracks lasting injuries sustained by a fighter during campaign play."

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="injuries",
        help_text="The fighter who has sustained this injury.",
    )
    injury = models.ForeignKey(
        "content.ContentInjury",
        on_delete=models.CASCADE,
        help_text="The specific injury sustained.",
    )
    date_received = models.DateTimeField(
        auto_now_add=True,
        help_text="When this injury was sustained.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about how this injury was received.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_received"]
        verbose_name = "Fighter Injury"
        verbose_name_plural = "Fighter Injuries"

    def __str__(self):
        return f"{self.fighter.name} - {self.injury.name}"

    def clean(self):
        # Only allow injuries on campaign mode fighters
        if self.fighter.list.status != List.CAMPAIGN_MODE:
            raise ValidationError(
                "Injuries can only be added to fighters in campaign mode."
            )


class ListFighterAdvancement(AppBase):
    """Track advancements purchased by fighters using XP in campaign mode."""

    # Types of advancements
    ADVANCEMENT_STAT = "stat"
    ADVANCEMENT_SKILL = "skill"
    ADVANCEMENT_OTHER = "other"

    ADVANCEMENT_TYPE_CHOICES = [
        (ADVANCEMENT_STAT, "Characteristic Increase"),
        (ADVANCEMENT_SKILL, "New Skill"),
        (ADVANCEMENT_OTHER, "Other"),
    ]

    STAT_CHOICES = [
        ("movement", "Movement"),
        ("weapon_skill", "Weapon Skill"),
        ("ballistic_skill", "Ballistic Skill"),
        ("strength", "Strength"),
        ("toughness", "Toughness"),
        ("wounds", "Wounds"),
        ("initiative", "Initiative"),
        ("attacks", "Attacks"),
        ("leadership", "Leadership"),
        ("cool", "Cool"),
        ("willpower", "Willpower"),
        ("intelligence", "Intelligence"),
    ]

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="advancements",
        help_text="The fighter who purchased this advancement.",
    )

    advancement_type = models.CharField(
        max_length=10,
        choices=ADVANCEMENT_TYPE_CHOICES,
        help_text="The type of advancement purchased.",
    )

    # For stat advancements
    stat_increased = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=STAT_CHOICES,
        help_text="For stat increases, which characteristic was improved.",
    )

    # For skill advancements
    skill = models.ForeignKey(
        ContentSkill,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="For skill advancements, which skill was gained.",
    )

    # For other advancements
    description = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="For 'other' advancements, a free text description.",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="The XP cost of this advancement.",
    )

    cost_increase = models.IntegerField(
        default=0,
        help_text="The increase in fighter cost from this advancement.",
    )

    # Link to campaign action if dice were rolled
    campaign_action = models.OneToOneField(
        "CampaignAction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advancement",
        help_text="The campaign action recording the dice roll for this advancement.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["fighter", "created"]
        verbose_name = "Fighter Advancement"
        verbose_name_plural = "Fighter Advancements"

    def __str__(self):
        if self.advancement_type == self.ADVANCEMENT_STAT:
            return f"{self.fighter.name} - {self.get_stat_increased_display()}"
        elif self.skill:
            return f"{self.fighter.name} - {self.skill.name}"
        elif self.advancement_type == self.ADVANCEMENT_OTHER and self.description:
            return f"{self.fighter.name} - {self.description}"
        return f"{self.fighter.name} - Advancement"

    def apply_advancement(self):
        """Apply this advancement to the fighter."""
        if self.advancement_type == self.ADVANCEMENT_STAT and self.stat_increased:
            # Apply stat increase
            override_field = f"{self.stat_increased}_override"

            # Get the base value from content_fighter
            base_value = getattr(self.fighter.content_fighter, self.stat_increased)

            # Get current override value, defaulting to None if not set
            current_override = getattr(self.fighter, override_field)

            # Stats are stored as strings like "3+" or "4", we need to handle numeric increases
            # For stats like WS/BS/Initiative with "+", extract the numeric part
            if base_value and "+" in base_value:
                base_numeric = int(base_value.replace("+", ""))
                if current_override is None:
                    # First advancement: improve by 1 (e.g., "4+" becomes "3+")
                    new_value = f"{base_numeric - 1}+"
                else:
                    # Further advancements: extract numeric from override and improve
                    current_numeric = int(current_override.replace("+", ""))
                    new_value = f"{current_numeric - 1}+"
            else:
                # For stats without "+" (like S, T, W), just add 1
                try:
                    base_numeric = int(base_value.replace('"', "")) if base_value else 0
                    if current_override is None:
                        new_value = str(base_numeric + 1)
                    else:
                        current_numeric = int(current_override.replace('"', ""))
                        new_value = str(current_numeric + 1)
                except (ValueError, TypeError):
                    # If we can't parse it as a number, just use the base value
                    new_value = base_value

            if '"' in base_value:
                # If the base value is a distance (e.g., "4\""), ensure we keep the format
                new_value = f'{new_value}"'

            setattr(self.fighter, override_field, new_value)
            self.fighter.save()
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            # Add skill to fighter
            self.fighter.skills.add(self.skill)
        elif self.advancement_type == self.ADVANCEMENT_OTHER:
            # For "other" advancements, nothing specific to apply
            # The description is just stored for display purposes
            pass

        # Deduct XP cost from fighter
        self.fighter.xp_current -= self.xp_cost
        self.fighter.save()

    def clean(self):
        """Validate the advancement."""
        if self.advancement_type == self.ADVANCEMENT_STAT and not self.stat_increased:
            raise ValidationError("Stat advancement requires a stat to be selected.")
        if self.advancement_type == self.ADVANCEMENT_SKILL and not self.skill:
            raise ValidationError("Skill advancement requires a skill to be selected.")
        if self.advancement_type == self.ADVANCEMENT_OTHER and not self.description:
            raise ValidationError("Other advancement requires a description.")
        if self.advancement_type == self.ADVANCEMENT_STAT and self.skill:
            raise ValidationError("Stat advancement should not have a skill selected.")
        if self.advancement_type == self.ADVANCEMENT_SKILL and self.stat_increased:
            raise ValidationError("Skill advancement should not have a stat selected.")
        if self.advancement_type == self.ADVANCEMENT_OTHER and (
            self.stat_increased or self.skill
        ):
            raise ValidationError(
                "Other advancement should not have a stat or skill selected."
            )


class ListAttributeAssignment(Base, Archived):
    """
    Through model that links a List to ContentAttributeValues.
    """

    help_text = "Associates gang attributes (like Alignment, Alliance, Affiliation) with a list."

    list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        help_text="The list this attribute is assigned to.",
    )
    attribute_value = models.ForeignKey(
        ContentAttributeValue,
        on_delete=models.CASCADE,
        help_text="The attribute value assigned to the list.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "List Attribute Assignment"
        verbose_name_plural = "List Attribute Assignments"
        unique_together = [["list", "attribute_value"]]

    def __str__(self):
        return f"{self.list.name} - {self.attribute_value.attribute.name}: {self.attribute_value.name}"

    def clean(self):
        """Validate that single-select attributes only have one value per list."""
        if self.attribute_value and self.list:
            attribute = self.attribute_value.attribute
            if attribute.is_single_select:
                # Check if there's already an assignment for this attribute
                existing = (
                    ListAttributeAssignment.objects.filter(
                        list=self.list,
                        attribute_value__attribute=attribute,
                        archived=False,  # Only check active assignments
                    )
                    .exclude(pk=self.pk)
                    .exists()
                )
                if existing:
                    raise ValidationError(
                        f"The attribute '{attribute.name}' is single-select and already has a value assigned to this list."
                    )

    def save(self, *args, **kwargs):
        """Override save to call full_clean() for validation."""
        self.full_clean()
        super().save(*args, **kwargs)


class CapturedFighter(AppBase):
    """Tracks a fighter being held captive by another gang."""

    # The captured fighter
    fighter = models.OneToOneField(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="capture_info",
        help_text="The fighter who has been captured",
    )

    # The gang holding the fighter captive
    capturing_list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        related_name="captured_fighters",
        help_text="The gang currently holding this fighter captive",
    )

    # When they were captured
    captured_at = models.DateTimeField(
        auto_now_add=True, help_text="When the fighter was captured"
    )

    # Track if sold to guilders
    sold_to_guilders = models.BooleanField(
        default=False, help_text="Whether the fighter has been sold to guilders"
    )
    sold_at = models.DateTimeField(
        null=True, blank=True, help_text="When the fighter was sold to guilders"
    )

    # Credits exchanged (if any)
    ransom_amount = models.IntegerField(
        null=True,
        blank=True,
        help_text="Credits paid as ransom or received for selling",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Captured Fighter"
        verbose_name_plural = "Captured Fighters"
        ordering = ["-captured_at"]

    def __str__(self):
        status = "sold to guilders" if self.sold_to_guilders else "captured"
        return f"{self.fighter.name} ({status} by {self.capturing_list.name})"

    def sell_to_guilders(self, credits=None):
        """Mark the fighter as sold to guilders."""
        from django.utils import timezone

        self.sold_to_guilders = True
        self.sold_at = timezone.now()
        if credits is not None:
            self.ransom_amount = credits
        self.save()

    def return_to_owner(self, credits=None):
        """Return the fighter to their original gang and delete the capture record."""
        if credits is not None:
            self.ransom_amount = credits
            self.save()

        # Delete the capture record, which returns the fighter to their original gang
        self.delete()

    def get_original_list(self):
        """Get the original gang this fighter belongs to."""
        return self.fighter.list


class ListFighterStatOverride(AppBase):
    """
    Allows overriding individual stat values for a ListFighter
    when they have a custom statline.
    """

    help_text = (
        "Represents a stat override for a ListFighter with a custom statline. "
        "This allows overriding individual stat values from the base ContentStatline."
    )

    list_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
        help_text="The ListFighter this override applies to",
    )
    content_stat = models.ForeignKey(
        ContentStatlineTypeStat,
        on_delete=models.CASCADE,
        help_text="The stat being overridden",
    )
    value = models.CharField(
        max_length=10,
        help_text="The overridden stat value (e.g., '5\"', '12', '4+', '-')",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "List Fighter Stat Override"
        verbose_name_plural = "List Fighter Stat Overrides"
        unique_together = ["list_fighter", "content_stat"]
        ordering = ["content_stat__position"]

    def __str__(self):
        return (
            f"{self.list_fighter.name} - {self.content_stat.short_name}: {self.value}"
        )
