import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Union

from django.conf import settings
from django.contrib import admin
from django.contrib.postgres.aggregates import ArrayAgg
from django.core import validators
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import (
    Case,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat, JSONObject
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentFighterHouseOverride,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModStatApplyMixin,
    ContentPsykerPower,
    ContentSkill,
    ContentStat,
    ContentStatline,
    ContentStatlineTypeStat,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    RulelineDisplay,
    StatlineDisplay,
    VirtualWeaponProfile,
)
from gyrinx.core.models.action import ListAction
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.history_aware_manager import HistoryAwareManager
from gyrinx.core.models.history_mixin import HistoryMixin
from gyrinx.core.models.util import ModContext
from gyrinx.models import (
    Archived,
    Base,
    FighterCategoryChoices,
    QuerySetOf,
    format_cost_display,
)
from gyrinx.tracker import track

logger = logging.getLogger(__name__)
pylist = list

# Define allowed category overrides
ALLOWED_CATEGORY_OVERRIDES = [
    FighterCategoryChoices.LEADER,
    FighterCategoryChoices.CHAMPION,
    FighterCategoryChoices.GANGER,
    FighterCategoryChoices.JUVE,
    FighterCategoryChoices.PROSPECT,
    FighterCategoryChoices.SPECIALIST,
]


def validate_category_override(value):
    """Validator to ensure category_override is in allowed list."""
    if value and value not in ALLOWED_CATEGORY_OVERRIDES:
        raise ValidationError(
            f"Category override must be one of: {', '.join([c.label for c in ALLOWED_CATEGORY_OVERRIDES])}"
        )


##
## Application Models
##


class ListQuerySet(models.QuerySet):
    def with_related_data(self, with_fighters=False):
        """
        Optimize queries by selecting related content_house and owner,
        and prefetching fighters with their related data.
        """
        qs = self.select_related(
            "content_house",
            "owner",
            "campaign",
            "original_list",
        ).prefetch_related(
            Prefetch(
                "listattributeassignment_set",
                queryset=ListAttributeAssignment.objects.filter(
                    archived=False
                ).select_related("attribute_value", "attribute_value__attribute"),
                to_attr="active_attribute_assignments",
            ),
            Prefetch(
                "campaign_clones",
                queryset=List.objects.filter(
                    status=List.CAMPAIGN_MODE, campaign__status=Campaign.IN_PROGRESS
                ),
                to_attr="active_campaign_clones",
            ),
            Prefetch(
                "actions",
                queryset=ListAction.objects.order_by(
                    "list_id", "-created", "-id"
                ).distinct("list_id"),
                to_attr="latest_actions",
            ),
        )

        if with_fighters:
            qs = qs.with_fighter_data()

        return qs

    def with_fighter_data(self):
        """
        Prefetch related fighter data for each list.
        """
        return self.prefetch_related(
            Prefetch(
                "listfighter_set",
                queryset=ListFighter.objects.with_group_keys().with_related_data(),
            ),
        )


class ListManager(HistoryAwareManager):
    pass


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
        max_length=255, validators=[validators.MinLengthValidator(1)]
    )
    content_house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=False, blank=False
    )
    public = models.BooleanField(
        default=True, help_text="Public lists are visible to all users.", db_index=True
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
        db_index=True,
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

    # Wealth tracking fields

    rating_current = models.PositiveIntegerField(
        default=0,
        help_text="Current rating of the list",
    )

    stash_current = models.PositiveIntegerField(
        default=0,
        help_text="Current stash value of the list",
    )

    credits_current = models.IntegerField(
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

    #
    # Wealth, Rating, Credits Behaviour
    #

    @admin.display(description="Cost / Wealth")
    def cost_int(self):
        """
        Calculate the total wealth of the list.

        Calling this 'cost' is a bit of a misnomer: it actually represents the total wealth of the list,
        i.e., the sum of all fighter costs plus stash (also a fighter because reasons) plus current credits.

        Note: we do _not_ want to used cached versions here because this method
        can be used to calculate the cost in real-time, reflecting any changes
        made to the fighters or their attributes.
        """
        rating = sum(
            [f.cost_int() for f in self.fighters() if not f.content_fighter.is_stash]
        )
        stash_fighter_cost_int = (
            self.stash_fighter.cost_int() if self.stash_fighter else 0
        )
        wealth = rating + stash_fighter_cost_int + self.credits_current
        self.check_wealth_sync(wealth)
        return wealth

    @cached_property
    def cost_int_cached(self):
        """
        Max-in-memory-cached version of cost_int().

        This should preferably be used, as it is expected to be accessed multiple times
        during typical request handling.
        """
        cache = caches["core_list_cache"]
        cache_key = self.cost_cache_key()
        cached = cache.get(cache_key)
        if cached:
            return cached

        rating = sum([f.cost_int_cached for f in self.active_fighters])
        wealth = rating + self.stash_fighter_cost_int + self.credits_current
        cache.set(cache_key, wealth, settings.CACHE_LIST_TTL)
        return wealth

    def cost_display(self):
        return format_cost_display(self.cost_int_cached)

    @cached_property
    def rating(self):
        return sum([f.cost_int_cached for f in self.active_fighters])

    @cached_property
    def rating_display(self):
        return format_cost_display(self.rating)

    @cached_property
    def stash_fighter_cost_int(self):
        return self.stash_fighter.cost_int() if self.stash_fighter else 0

    @cached_property
    def stash_fighter_cost_display(self):
        return format_cost_display(self.stash_fighter_cost_int)

    @cached_property
    def credits_current_display(self):
        return format_cost_display(self.credits_current)

    @cached_property
    def wealth_current(self):
        return self.rating_current + self.stash_current + self.credits_current

    def check_wealth_sync(self, wealth_calculated):
        """
        Check if the stored rating_current and latest action match the calculated cost.

        This is temporary and will be removed once we fully rely on rating_current and actions to track list costs.
        """

        # This is conditioned on having a latest action to avoid false positives before we have any actions in place.
        # We refetch in the case where latest_action is not prefetched.
        la = self.latest_action

        if la:
            calculated_current_delta = wealth_calculated - self.wealth_current
            calculated_action_delta = wealth_calculated - la.wealth_after
            if calculated_current_delta != 0 or calculated_action_delta != 0:
                track(
                    "list_cost_out_of_sync",
                    list_id=str(self.id),
                    wealth_calculated=wealth_calculated,
                    wealth_current=self.wealth_current,
                    rating_current=self.rating_current,
                    stash_current=self.stash_current,
                    credits_current=self.credits_current,
                    latest_action_wealth_after=la.wealth_after,
                    latest_action_rating_after=la.rating_after,
                    latest_action_stash_after=la.stash_after,
                    latest_action_credits_after=la.credits_after,
                )

    #
    # Fighter & other properties
    #

    def fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.with_related_data().filter(archived=False)

    def archived_fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.with_related_data().filter(archived=True)

    @cached_property
    def fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.fighters()

    @cached_property
    def archived_fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.archived_fighters()

    @cached_property
    def fighters_minimal_cached(self):
        return self.listfighter_set.filter(archived=False).values("id", "name")

    @cached_property
    def active_fighters(self) -> QuerySetOf["ListFighter"]:
        """Get all fighters that could participate in a battle."""
        return self.fighters().exclude(content_fighter__is_stash=True)

    @cached_property
    def stash_fighter(self):
        """Get the stash fighter for this list, if it exists."""
        return self.fighters().filter(content_fighter__is_stash=True).first()

    @cached_property
    def owner_cached(self):
        return self.owner

    @cached_property
    def content_house_cached(self):
        """Cache the content_house object to prevent repeated queries."""
        return self.content_house

    @cached_property
    def content_house_name(self):
        """Cache the house name which is frequently accessed in templates."""
        return self.content_house.name if self.content_house_id else ""

    @cached_property
    def content_house_id_cached(self):
        """Cache the house ID to prevent object access."""
        return self.content_house_id

    @property
    def is_list_building(self):
        return self.status == self.LIST_BUILDING

    @property
    def is_campaign_mode(self):
        return self.status == self.CAMPAIGN_MODE

    @cached_property
    def active_attributes_cached(self):
        if hasattr(self, "active_attribute_assignments"):
            return self.active_attribute_assignments

        # If not prefetched, filter directly
        return self.listattributeassignment_set.filter(archived=False).select_related(
            "attribute_value", "attribute_value__attribute"
        )

    @cached_property
    def all_attributes(self):
        # Build a map of attribute_id to value names

        assignment_map = defaultdict(list)
        # Performance: upstream of this, active_attribute_assignments has been prefetched
        # so we can iterate directly without hitting the database again.
        for attribute_assign in self.active_attributes_cached:
            attr_id = attribute_assign.attribute_value.attribute_id
            assignment_map[attr_id].append(attribute_assign.attribute_value.name)

        # Get all available attributes in a single query using values to avoid object queries
        available_attributes = list(
            ContentAttribute.objects.filter(
                Q(restricted_to__isnull=True) | Q(restricted_to=self.content_house)
            )
            .distinct()
            .order_by("name")
            .values("id", "name")
        )

        # Build result as list of dicts to prevent template object access
        attributes = []
        for attribute in available_attributes:
            attr_data = {
                "id": attribute["id"],
                "name": attribute["name"],
                "assignments": assignment_map.get(attribute["id"], []),
            }
            attributes.append(attr_data)

        return attributes

    @cached_property
    def fighter_type_summary(self):
        """
        Returns a summary of fighter types and their counts for active fighters.

        Performance: This must use prefetched listfighter_set data from with_related_data,
        so it doesn't issue any additional queries.

        Returns:
            List of dicts with 'type', 'category' and 'count' keys.
        """

        # Use OrderedDict to maintain the order fighters are encountered
        type_counts = OrderedDict()

        # Iterate over prefetched listfighter_set and filter in memory to avoid queries
        active_fighters = [
            f
            for f in self.listfighter_set.all()
            if not f.archived and not f.content_fighter.is_stash
        ]
        for fighter in active_fighters:
            # We use a compound key of (type, category) to differentiate types with same name but different categories,
            # and so we can extract both later for the output.
            fighter_type = (fighter.content_fighter.type, fighter.get_category_label())
            type_counts[fighter_type] = type_counts.get(fighter_type, 0) + 1

        # Convert to the expected format while preserving order
        summary = [
            {"type": fighter_type, "category": category, "count": count}
            for (fighter_type, category), count in type_counts.items()
        ]

        return summary

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

    @cached_property
    def latest_action(self) -> Optional[ListAction]:
        """Get the latest ListAction for this list, if any.

        Performance: This requires prefetching latest_actions via with_related_data().
        """
        if hasattr(self, "latest_actions") and self.latest_actions:
            return self.latest_actions[0]

        return ListAction.objects.latest_for_list(self.id)

    def create_action(
        self, update_credits: bool = False, **kwargs
    ) -> Optional[ListAction]:
        """
        Create a ListAction to track changes to this list.

        Args:
            update_credits: If True, applies credits_delta to the list's credits_current.
                           This works regardless of whether the feature flag is enabled -
                           credits are always updated when this is True.
            **kwargs: Additional fields for the ListAction (action_type, description,
                     rating_delta, stash_delta, credits_delta, etc.)

        Returns:
            The created ListAction if feature flag is enabled, None otherwise.
            Note: Even when returning None, credits are still updated if update_credits=True.
        """
        # Don't run this if we haven't yet got a latest_action. We'll run a backfill
        # to ensure there is at least one action for each list, with the correct values, later.
        if self.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
            user = kwargs.pop("user", None)

            # Make sure we have values for the key fields
            rating_before = kwargs.pop("rating_before", self.rating_current)
            stash_before = kwargs.pop("stash_before", self.stash_current)
            credits_before = kwargs.pop("credits_before", self.credits_current)

            # We create the action first, with applied=False, so that we can track if the update failed
            la = ListAction.objects.create(
                user=user or self.owner,
                owner=self.owner,
                list=self,
                applied=False,
                rating_before=rating_before,
                stash_before=stash_before,
                credits_before=credits_before,
                **kwargs,
            )
            la.save()

            track_args = {
                "list": str(self.id),
                "action_id": str(la.id),
                "update_credits": update_credits,
                "rating_before": rating_before,
                "stash_before": stash_before,
                "credits_before": credits_before,
                **kwargs,
            }

            track(
                "list_action_created",
                **track_args,
            )

            # Update key fields
            # Currently we don't apply credits delta by default in actions because spend_credits exists
            # but we should refactor in that direction later.
            rating_delta = kwargs.get("rating_delta", 0)
            stash_delta = kwargs.get("stash_delta", 0)
            credits_delta = kwargs.get("credits_delta", 0) if update_credits else 0

            try:
                self.rating_current = max(0, self.rating_current + rating_delta)
                self.stash_current = max(0, self.stash_current + stash_delta)
                self.credits_current += credits_delta
                self.credits_earned += max(0, credits_delta)
                self.save(
                    update_fields=[
                        "rating_current",
                        "stash_current",
                        "credits_current",
                        "credits_earned",
                    ]
                )
            except Exception as e:
                logger.error(
                    f"Failed to update list {self.id} cost fields after action creation: {e}"
                )
                track(
                    "list_action_apply_failed",
                    **track_args,
                    error=str(e),
                )
                # Don't refresh_from_db() here - causes TransactionManagementError when
                # called within an atomic transaction after an error
                return la

            track(
                "list_action_apply_succeeded",
                **track_args,
            )

            la.applied = True
            la.save(update_fields=["applied"])
            return la

        else:
            track(
                "list_action_skipped_no_latest_action",
                list=str(self.id),
                **kwargs,
            )

            # Even when actions are disabled, allow credit updates for refunds
            if update_credits:
                credits_delta = kwargs.get("credits_delta", 0)
                if credits_delta != 0:
                    self.credits_current += credits_delta
                    self.credits_earned += max(0, credits_delta)
                    self.save(update_fields=["credits_current", "credits_earned"])
                    track(
                        "list_credits_updated_without_action",
                        list=str(self.id),
                        credits_current=self.credits_current,
                        credits_earned=self.credits_earned,
                        **kwargs,
                    )

        return None

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

    def spend_credits(self, amount, description="Purchase"):
        """Spend credits from this list's available credits.

        Args:
            amount: The number of credits to spend
            description: Description of what the credits are being spent on (for error messages)

        Returns:
            True if the credits were successfully spent

        Raises:
            ValidationError: If the list doesn't have enough credits
        """
        if amount < 0:
            raise ValidationError("Cannot spend negative credits")

        if self.credits_current < amount:
            raise ValidationError(
                f"Insufficient credits. {description} costs {amount}¢, "
                f"but you only have {self.credits_current}¢ available."
            )

        self.credits_current -= amount
        self.save(update_fields=["credits_current"])
        return True

    def clone(self, name=None, owner=None, for_campaign=None, **kwargs) -> "List":
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
            "rating_current": self.rating_current,
            "stash_current": self.stash_current,
            "credits_current": self.credits_current,
            "credits_earned": self.credits_earned,
            **kwargs,
        }

        clone = List.objects.create(
            name=name,
            content_house=self.content_house,
            owner=owner,
            **values,
        )

        # Create initial ListAction for if feature flag enabled
        la = None
        if settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
            from gyrinx.core.models.action import ListAction, ListActionType

            la = ListAction.objects.create(
                user=owner,
                owner=owner,
                list=clone,
                action_type=ListActionType.CREATE,
                description=f"Cloned from '{self.name}'",
                applied=True,
                rating_before=0,
                stash_before=0,
                credits_before=0,
                rating_delta=self.rating_current,
                stash_delta=self.stash_current,
                credits_delta=self.credits_current,
            )

            track(
                "list_clone_initial_action_created",
                original_list=str(self.id),
                cloned_list=str(clone.id),
                action=str(la.id),
            )
        else:
            track(
                "list_clone_initial_action_skipped",
                original_list=str(self.id),
                cloned_list=str(clone.id),
            )

        # Clone fighters, but skip linked fighters and stash fighters
        for fighter in self.fighters():
            # Skip if this fighter is linked to an equipment assignment
            is_linked = (
                hasattr(fighter, "source_assignment")
                and fighter.source_assignment.exists()
            )
            # Skip if this is a stash fighter
            is_stash = fighter.content_fighter.is_stash

            if not is_linked and not is_stash:
                fighter.clone(list=clone)

        # Clone stash fighter
        original_stash = self.listfighter_set.filter(
            content_fighter__is_stash=True
        ).first()

        # For campaign mode, always ensure a stash exists
        if for_campaign or original_stash:
            new_stash = clone.ensure_stash(owner=owner)
            # Clone equipment from original stash if it existed
            if original_stash:
                for assignment in original_stash._direct_assignments():
                    assignment.clone(list_fighter=new_stash)

        # Clone attributes
        for attribute_assignment in self.listattributeassignment_set.filter(
            archived=False
        ):
            ListAttributeAssignment.objects.create(
                list=clone,
                attribute_value=attribute_assignment.attribute_value,
            )

        # Simulate prefetching latest_actions for the clone
        if la:
            # Clear any cached None value from the @cached_property
            clone.__dict__.pop("latest_action", None)
            # Set the prefetch list that latest_action property will check
            setattr(clone, "latest_actions", [la])

        track(
            "list_cloned",
            original_list=str(self.id),
            cloned_list=str(clone.id),
            for_campaign=str(for_campaign.id) if for_campaign else "",
            action=str(la.id) if la else "",
        )

        return clone

    class Meta:
        verbose_name = "List"
        verbose_name_plural = "Lists"
        ordering = ["name"]

    def __str__(self):
        return self.name

    objects = ListManager.from_queryset(ListQuerySet)()


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
                    When(source_assignment__isnull=False, then=True),
                    default=False,
                ),
                _category_order=Case(
                    *[
                        When(
                            # Use category_override if set, otherwise use content_fighter__category
                            # Put linked fighters in the same category as their parent
                            Q(category_override=category)
                            | Q(
                                category_override__isnull=True,
                                content_fighter__category=category,
                            )
                            | Q(
                                source_assignment__list_fighter__category_override=category,
                                # Only consider linked fighters that are not stash fighters
                                source_assignment__list_fighter__content_fighter__is_stash=False,
                            )
                            | Q(
                                source_assignment__list_fighter__category_override__isnull=True,
                                source_assignment__list_fighter__content_fighter__category=category,
                                # Only consider linked fighters that are not stash fighters
                                source_assignment__list_fighter__content_fighter__is_stash=False,
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
                    # Gang Terrain always sorts last
                    When(
                        Q(category_override=FighterCategoryChoices.GANG_TERRAIN)
                        | Q(
                            category_override__isnull=True,
                            content_fighter__category=FighterCategoryChoices.GANG_TERRAIN,
                        ),
                        then=999,
                    ),
                    # Other categories (including ALLY) sort in the middle, undefined
                    default=50,
                ),
                _sort_key=Case(
                    # If this is a beast linked to a fighter, sort after the owner
                    # Check category_override first, then content_fighter__category
                    When(
                        Q(_is_linked=True)
                        & (
                            Q(category_override=FighterCategoryChoices.EXOTIC_BEAST)
                            | Q(
                                category_override__isnull=True,
                                content_fighter__category=FighterCategoryChoices.EXOTIC_BEAST,
                            )
                        ),
                        then=Concat(
                            "source_assignment__list_fighter__name", Value("~2")
                        ),
                    ),
                    # If this is a vehicle linked to a fighter, sort with the parent but come first
                    # Note: Vehicle cannot be an override category, only content_fighter__category
                    When(
                        Q(_is_linked=True)
                        & Q(
                            content_fighter__category=FighterCategoryChoices.VEHICLE,
                        ),
                        then=Concat(
                            "source_assignment__list_fighter__name", Value("~0")
                        ),
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
                # Note: Vehicle cannot be an override category, only content_fighter__category
                When(
                    Q(source_assignment__isnull=False)
                    & Q(
                        content_fighter__category=FighterCategoryChoices.VEHICLE,
                    )
                    & Q(
                        source_assignment__list_fighter__content_fighter__is_stash=True
                    ),
                    then=F("id"),
                ),
                # If this fighter is linked, and we are a vehicle, use the linked fighter's id
                When(
                    Q(source_assignment__isnull=False)
                    & Q(
                        content_fighter__category=FighterCategoryChoices.VEHICLE,
                    ),
                    then=F("source_assignment__list_fighter__id"),
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

    def with_related_data(self):
        """
        Optimize queries by selecting related content_fighter and list,
        and prefetching injuries and equipment assignments.

        This is the standard optimization pattern used throughout views
        to reduce N+1 query issues.
        """
        return (
            self.select_related(
                "content_fighter",
                "content_fighter__house",
                "content_fighter__custom_statline",
                "legacy_content_fighter",
                "legacy_content_fighter__house",
                "capture_info",
                "capture_info__capturing_list",
            )
            .prefetch_related(
                "injuries",
                "skills",
                "disabled_skills",
                "disabled_rules",
                "disabled_default_assignments",
                "advancements",
                "stat_overrides",
                "listfighterequipmentassignment_set__content_equipment__contentweaponprofile_set",
                "listfighterequipmentassignment_set__weapon_accessories_field__modifiers",
                "listfighterequipmentassignment_set__content_equipment__modifiers",
                "listfighterequipmentassignment_set__upgrades_field__modifiers",
                "content_fighter__skills",
                "content_fighter__rules",
                "content_fighter__house",
                "content_fighter__default_assignments__equipment__contentweaponprofile_set",
                "source_assignment",
                "source_assignment__list_fighter",
                Prefetch(
                    "list",
                    # DO NOT add with_fighters=True here, it will cause infinite recursion
                    queryset=List.objects.with_related_data(),
                ),
            )
            .annotate(
                prefetched=Value(True),
                annotated_category_terms=Subquery(
                    ListFighter.objects.sq_category_terms()
                ),
                annotated_house_cost_override=Subquery(
                    ListFighter.objects.sq_house_cost_override()
                ),
                annotated_advancement_total_cost=Coalesce(
                    Subquery(self.sq_advancement_cost_sum()),
                    Value(0),
                ),
                annotated_content_fighter_statline=self.sq_content_fighter_statline(),
                annotated_stat_overrides=self.sq_stat_overrides(),
            )
        )

    def sq_category_terms(self):
        """
        Subquery to get category terms for this fighter.
        This is used to annotate the main queryset with category terms.
        """
        return (
            ContentFighterCategoryTerms.objects.filter(
                categories__contains=OuterRef("content_fighter__category")
            )
            .annotate(
                obj=JSONObject(
                    singular=F("singular"),
                    proximal_demonstrative=F("proximal_demonstrative"),
                    injury_singular=F("injury_singular"),
                    injury_plural=F("injury_plural"),
                    recovery_singular=F("recovery_singular"),
                )
            )
            .values("obj")[:1]
        )

    def sq_house_cost_override(self):
        return (
            ContentFighterHouseOverride.objects.filter(
                fighter_id=OuterRef("content_fighter_id"),
                house=OuterRef("list__content_house"),
                cost__isnull=False,
            )
            .annotate(obj=JSONObject(cost=F("cost")))
            .values("obj")[:1]
        )

    def sq_advancement_cost_sum(self):
        """
        Subquery to sum non-archived advancement cost increases.
        This avoids JOIN duplication issues with direct Sum annotations.
        """
        return (
            ListFighterAdvancement.objects.filter(
                fighter_id=OuterRef("pk"),
                archived=False,
            )
            .values("fighter_id")
            .annotate(total=models.Sum("cost_increase"))
            .values("total")[:1]
        )

    def sq_content_fighter_statline(self):
        """
        Subquery to get custom statline stats as JSON array.
        This avoids JOIN duplication issues with direct ArrayAgg annotations.
        """
        return Subquery(
            ContentStatline.objects.filter(
                content_fighter_id=OuterRef("content_fighter_id")
            )
            .annotate(
                stats_array=ArrayAgg(
                    JSONObject(
                        field_name=F("stats__statline_type_stat__stat__field_name"),
                        name=F("stats__statline_type_stat__stat__short_name"),
                        value=F("stats__value"),
                        highlight=F("stats__statline_type_stat__is_highlighted"),
                        first_of_group=F(
                            "stats__statline_type_stat__is_first_of_group"
                        ),
                    ),
                    ordering=F("stats__statline_type_stat__position").asc(),
                )
            )
            .values("stats_array")[:1]
        )

    def sq_stat_overrides(self):
        """
        Subquery to get stat overrides as JSON array.
        This avoids JOIN duplication issues with direct ArrayAgg annotations.
        """
        return Subquery(
            ListFighterStatOverride.objects.filter(
                list_fighter_id=OuterRef("pk"), archived=False
            )
            .values("list_fighter_id")
            .annotate(
                overrides_array=ArrayAgg(
                    JSONObject(
                        field_name=F("content_stat__stat__field_name"),
                        value=F("value"),
                    ),
                    distinct=True,
                )
            )
            .values("overrides_array")[:1]
        )


class ListFighter(AppBase):
    """A Fighter is a member of a List."""

    help_text = "A ListFighter is a member of a List, linked to a Content Fighter archetype to give base stats and equipment."
    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(1)]
    )
    content_fighter = models.ForeignKey(
        ContentFighter, on_delete=models.CASCADE, null=False, blank=False, db_index=True
    )
    legacy_content_fighter = models.ForeignKey(
        ContentFighter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="list_fighter_legacy",
        help_text="This supports a ListFighter having a Content Fighter legacy which provides access to (and costs from) the legacy fighter's equipment list.",
    )
    list = models.ForeignKey(
        List, on_delete=models.CASCADE, null=False, blank=False, db_index=True
    )
    category_override = models.CharField(
        max_length=255,
        choices=[(c, c.label) for c in ALLOWED_CATEGORY_OVERRIDES],
        blank=True,
        null=True,
        validators=[validate_category_override],
        help_text="Override the fighter's category without changing their type. Limited to Leader, Champion, Ganger, Juve, Prospect, and Specialist.",
    )

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

    # Skill overrides
    disabled_skills = models.ManyToManyField(
        "content.ContentSkill",
        blank=True,
        related_name="disabled_for_fighters",
        help_text="Default skills from the ContentFighter that have been disabled for this fighter.",
    )

    # Rule overrides
    disabled_rules = models.ManyToManyField(
        "content.ContentRule",
        blank=True,
        related_name="disabled_by_fighters",
        help_text="Default rules from the ContentFighter that have been disabled for this fighter.",
    )
    custom_rules = models.ManyToManyField(
        "content.ContentRule",
        blank=True,
        related_name="custom_for_fighters",
        help_text="Custom rules added to this fighter beyond their default rules.",
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
    IN_REPAIR = "in_repair"

    INJURY_STATE_CHOICES = [
        (ACTIVE, "Active"),
        (RECOVERY, "Recovery"),
        (CONVALESCENCE, "Convalescence"),
        (DEAD, "Dead"),
        (IN_REPAIR, "In Repair"),
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
    def _category_terms(self):
        if not hasattr(self, "annotated_category_terms"):
            return ContentFighterCategoryTerms.objects.filter(
                categories__contains=self.content_fighter_cached.category
            ).first()

        return (
            ContentFighterCategoryTerms(**self.annotated_category_terms)
            if self.annotated_category_terms
            else None
        )

    @cached_property
    def proximal_demonstrative(self) -> str:
        """
        Returns a user-friendly proximal demonstrative for this fighter (e.g., "this" or "that").
        For backward compatibility, calls term_proximal_demonstrative.
        """
        return self.term_proximal_demonstrative

    @cached_property
    def term_singular(self) -> str:
        """
        Returns the singular term for this fighter, using custom terms if available.
        """
        if self._category_terms:
            return self._category_terms.singular

        # Default to "fighter" if no custom term is found
        return "Fighter"

    @cached_property
    def term_proximal_demonstrative(self) -> str:
        """
        Returns the proximal demonstrative for this fighter, using custom terms if available.
        """
        # Import here to avoid circular imports

        # Check if this fighter's category has custom terms
        if self._category_terms:
            return self._category_terms.proximal_demonstrative

        # Fall back to default logic
        if self.is_stash:
            return "The stash"

        if self.is_vehicle:
            return "The vehicle"

        return "This fighter"

    @cached_property
    def term_injury_singular(self) -> str:
        """
        Returns the singular form of injury for this fighter, using custom terms if available.
        """
        # Import here to avoid circular imports

        # Check if this fighter's category has custom terms
        if self._category_terms:
            return self._category_terms.injury_singular

        # Default
        return "Injury"

    @cached_property
    def term_injury_plural(self) -> str:
        """
        Returns the plural form of injury for this fighter, using custom terms if available.
        """
        # Import here to avoid circular imports

        # Check if this fighter's category has custom terms
        if self._category_terms:
            return self._category_terms.injury_plural

        # Default
        return "Injuries"

    @cached_property
    def term_recovery_singular(self) -> str:
        """
        Returns the singular form of recovery for this fighter, using custom terms if available.
        """
        # Check if this fighter's category has custom terms
        if self._category_terms:
            return self._category_terms.recovery_singular

        # Default
        return "Recovery"

    def get_category(self):
        """
        Returns the effective category for this fighter, using override if set.
        """
        if self.category_override:
            return self.category_override
        return self.content_fighter_cached.category

    def get_category_label(self):
        """
        Returns the label for the effective category.
        """
        category = self.get_category()
        return FighterCategoryChoices[category].label

    @cached_property
    def fully_qualified_name(self) -> str:
        """
        Returns the fully qualified name of the fighter, including type and category.
        """
        if self.is_stash:
            return "Stash"

        # Use overridden category if set
        cf = self.content_fighter_cached
        if self.category_override:
            # Format with overridden category
            category_label = FighterCategoryChoices[self.category_override].label
            return f"{self.name} - {cf.type} ({category_label})"
        else:
            # Use normal content fighter name
            return f"{self.name} - {cf.name()}"

    @admin.display(description="Total Cost with Equipment")
    def cost_int(self):
        # Captured or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            return 0

        # Include advancement cost increases (excluding archived)
        advancement_cost = (
            self.advancements.filter(archived=False).aggregate(
                total=models.Sum("cost_increase")
            )["total"]
            or 0
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

        return (
            self._base_cost_int
            + self._advancement_cost_int
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

        # Or if it's linked to a parent via an assignment...
        if self.is_child_fighter:
            return 0

        return self._base_cost_before_override()

    def _base_cost_before_override(self):
        # Or by the house...
        # Is this an override? Yes, but not set on the fighter itself.
        cost_override = None
        if hasattr(self, "annotated_house_cost_override"):
            cost_override = self.annotated_house_cost_override
        else:
            cost_override_qs = (
                ContentFighterHouseOverride.objects.filter(
                    fighter=self.content_fighter_cached,
                    house=self.list.content_house,
                    cost__isnull=False,
                )
                .values("cost")
                .first()
            )
            cost_override = cost_override_qs

        if cost_override:
            return cost_override["cost"]

        # But if neither of those are set, we just use the base cost from the content fighter
        return self.content_fighter_cached.cost_int()

    def base_cost_display(self):
        return format_cost_display(self._base_cost_int)

    def base_cost_before_override_display(self):
        return format_cost_display(self._base_cost_before_override())

    @cached_property
    def _advancement_cost_int(self):
        if hasattr(self, "annotated_advancement_total_cost"):
            return self.annotated_advancement_total_cost

        return (
            self.advancements.filter(archived=False).aggregate(
                total=models.Sum("cost_increase")
            )["total"]
            or 0
        )

    @cached_property
    def advancement_cost_display(self):
        return format_cost_display(self._advancement_cost_int)

    def cost_display(self):
        return format_cost_display(self.cost_int_cached)

    @cached_property
    def is_active(self):
        """
        Returns True if this fighter is active and can participate in battles.
        """
        return self.injury_state == ListFighter.ACTIVE

    @cached_property
    def is_injured(self):
        return self.injury_state in [
            ListFighter.RECOVERY,
            ListFighter.CONVALESCENCE,
            ListFighter.IN_REPAIR,
        ]

    @cached_property
    def is_dead(self):
        return self.injury_state == ListFighter.DEAD

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
            for injury in self.injuries.all():
                injury_mods.extend(injury.injury.modifiers.all())

        # Add advancement mods for stat advancements using the mod system
        # (not legacy override fields)
        # Note: Use .all() with Python filtering to leverage prefetched data.
        # Using .filter() would bypass the prefetch cache and cause N+1 queries.
        advancement_mods = [
            AdvancementStatMod(adv.stat_increased)
            for adv in self.advancements.all()
            if (
                not adv.archived
                and adv.advancement_type == "stat"
                and adv.stat_increased is not None
                and adv.uses_mod_system
            )
        ]

        return equipment_mods + injury_mods + advancement_mods

    def _apply_mods(
        self,
        stat: str,
        value: str,
        mods: pylist[ContentModFighterStat],
        mod_ctx: Optional[ModContext] = None,
    ):
        current_value = value
        for mod in mods:
            try:
                current_value = mod.apply(current_value, mod_ctx=mod_ctx)
            except (ValueError, TypeError) as e:
                logger.exception(
                    f"Error applying mod {mod} (mode={mod.mode}, value={mod.value}) "
                    f"to {stat}={current_value}: {e}"
                )
        return current_value

    def get_primary_skill_categories(self):
        """
        Get primary skill categories for this fighter, including equipment modifications.
        """
        from gyrinx.content.models import ContentModSkillTreeAccess

        # Start with base primary skill categories from content fighter
        categories = set(self.content_fighter.primary_skill_categories.all())

        # Apply equipment modifications
        for mod in self._mods:
            if isinstance(mod, ContentModSkillTreeAccess):
                if mod.mode == "add_primary":
                    categories.add(mod.skill_category)
                elif mod.mode == "remove_primary":
                    categories.discard(mod.skill_category)
                elif mod.mode == "disable":
                    categories.discard(mod.skill_category)

        return categories

    def get_secondary_skill_categories(self):
        """
        Get secondary skill categories for this fighter, including equipment modifications.
        """
        from gyrinx.content.models import ContentModSkillTreeAccess

        # Start with base secondary skill categories from content fighter
        categories = set(self.content_fighter.secondary_skill_categories.all())

        # Apply equipment modifications
        for mod in self._mods:
            if isinstance(mod, ContentModSkillTreeAccess):
                if mod.mode == "add_secondary":
                    categories.add(mod.skill_category)
                elif mod.mode == "remove_secondary":
                    categories.discard(mod.skill_category)
                elif mod.mode == "disable":
                    categories.discard(mod.skill_category)

        return categories

    def get_available_psyker_disciplines(self):
        """
        Get available psyker disciplines for this fighter, including equipment modifications.
        """
        from gyrinx.content.models import ContentModPsykerDisciplineAccess

        # Start with base disciplines from ContentFighter
        # Access the psyker_disciplines through the assignment model
        base_assignments = self.content_fighter.psyker_disciplines.all()
        disciplines = set(assignment.discipline for assignment in base_assignments)

        # Apply equipment modifications
        for mod in self._mods:
            if isinstance(mod, ContentModPsykerDisciplineAccess):
                if mod.mode == "add":
                    disciplines.add(mod.discipline)
                elif mod.mode == "remove":
                    disciplines.discard(mod.discipline)

        return disciplines

    def _statmods(self, stat: str):
        """
        Get the stat mods for this fighter.

        Includes both ContentModFighterStat (from equipment/injuries) and
        AdvancementStatMod (from stat advancements using the mod system).
        """
        return [
            mod
            for mod in self._mods
            if isinstance(mod, (ContentModFighterStat, AdvancementStatMod))
            and mod.stat == stat
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

        There are two statline systems:
        1. one simple, legacy version that has a base list of stats on the content fighter, and `_override` fields
           for each stat on the list fighter
        2. a more complex, newer version that allows custom statline types to be created and assigned to content
           fighters, with overrides stored separately, and with specific underlying stats reused across statline types

        In either case, the flow goes something like this:
        1. Get the statline for the underlying content fighter
        2. Apply any overrides from the list fighter
        3. Apply any mods from the list fighter

        The more complex system is, without optimisation, massively more expensive to compute.
        """
        stats = []

        # Check if the fighter has a custom statline
        has_custom_statline = hasattr(self.content_fighter_cached, "custom_statline")

        # Get stat overrides for this fighter
        stat_overrides = {}
        # Performance: use the annotated version if it exists
        if (
            hasattr(self, "annotated_stat_overrides")
            and self.annotated_stat_overrides is not None
        ):
            stat_overrides = {
                override["field_name"]: override["value"]
                for override in self.annotated_stat_overrides
            }
        elif has_custom_statline and self.stat_overrides.exists():
            stat_overrides = {
                override.content_stat.field_name: override.value
                for override in self.stat_overrides.all()
            }

        # Prefetch all stats because we're going to use them later
        # This is better than querying each stat individually
        mod_ctx = ModContext(
            all_stats={
                stat["field_name"]: stat for stat in ContentStat.objects.all().values()
            }
        )

        for stat in self.content_fighter_statline:
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
            statmods = self._statmods(stat["field_name"])
            value = self._apply_mods(
                stat["field_name"],
                input_value,
                statmods,
                mod_ctx,
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
    def content_fighter_statline(self) -> pylist[dict]:
        """
        Get the base statline for the content fighter.

        Performance: we try to use the annotated version if it exists, which is added by `get_related_data`.
        """
        stats = (
            self.annotated_content_fighter_statline
            if (
                hasattr(self, "annotated_content_fighter_statline")
                and self.annotated_content_fighter_statline is not None
            )
            # Performance: we don't want to repeat look-for the custom statline, so we force-skip
            # this check on the fallback call.
            else self.content_fighter_cached.statline(
                ignore_custom=hasattr(self, "annotated_content_fighter_statline")
            )
        )

        return [
            {**stat, "classes": "border-start" if stat["first_of_group"] else ""}
            for stat in stats
        ]

    @cached_property
    def ruleline(self):
        """
        Get the ruleline for this fighter.
        """
        # Start with default rules from ContentFighter
        rules = list(self.content_fighter_cached.rules.all())
        modded = []

        # Remove disabled rules
        disabled_rules_set = set(self.disabled_rules.all())
        rules = [r for r in rules if r not in disabled_rules_set]

        # Apply modifications from equipment/items
        for mod in self._rulemods:
            if mod.mode == "add" and mod.rule not in rules:
                rules.append(mod.rule)
                modded.append(mod.rule)
            elif mod.mode == "remove" and mod.rule in rules:
                rules.remove(mod.rule)

        # Add custom rules
        for custom_rule in self.custom_rules.all():
            if custom_rule not in rules:
                rules.append(custom_rule)
                modded.append(custom_rule)

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
        return self.listfighterequipmentassignment_set.all()

    @cached_property
    def _default_assignments(self):
        # Performance: this is done in Python because when we prefetch these, these queries are
        # already optimized and won't hit the database again.
        return [
            a
            for a in self.content_fighter_cached.default_assignments.all()
            if a not in self.disabled_default_assignments.all()
        ]

    def assignments(self) -> pylist["VirtualListFighterEquipmentAssignment"]:
        return [
            VirtualListFighterEquipmentAssignment.from_assignment(a)
            for a in self._direct_assignments()
        ] + [
            VirtualListFighterEquipmentAssignment.from_default_assignment(a, self)
            for a in self._default_assignments
        ]

    @cached_property
    def assignments_cached(self) -> pylist["VirtualListFighterEquipmentAssignment"]:
        return self.assignments()

    @cached_property
    def is_child_fighter(self: "ListFighter") -> bool:
        """
        Check if this fighter is a child fighter (spawned by an equipment assignment).

        The relation self.source_assignment is a related name from the assignment, so is_child_fighter
        is true for the *child* fighter, not the parent.
        """
        return self.source_assignment.exists()

    @cached_property
    def parent_list_fighter(self):
        """
        Returns the actual parent fighter object for this child fighter, if it exists.

        This is used from the *child* fighter's perspective, so it returns the parent
        ListFighter that is linked to this fighter via the ListFighterEquipmentAssignment.
        """
        # Performance: This MUST use .all() to avoid hitting the database: we are using
        # prefetch_related in the queryset to load source_assignment.
        # If we use .first() or .get(), it will hit the database again.
        source_assignments = self.source_assignment.all()
        if source_assignments:
            # Return the first assignment's list_fighter, assuming only one is linked
            return source_assignments[0].list_fighter
        return None

    def skilline(self):
        # Start with default skills from ContentFighter
        default_skills = list(self.content_fighter_cached.skills.all())

        # Remove disabled skills
        disabled_skills_set = set(self.disabled_skills.all())
        default_skills = [s for s in default_skills if s not in disabled_skills_set]

        # Combine with user-added skills
        skills = set(default_skills + list(self.skills.all()))

        # Apply modifications from equipment/items
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
        """
        Check if this fighter has access to house-restricted or expansion equipment categories.
        This includes:
        1. House restricted categories
        2. Equipment from expansions
        3. Actual assigned gear from restricted categories
        """
        # Check house restricted categories
        if self.content_fighter_cached.house.restricted_equipment_categories.exists():
            return True

        # Check if any expansions apply that provide equipment
        from gyrinx.content.models_.expansion import (
            ContentEquipmentListExpansion,
            ExpansionRuleInputs,
        )

        rule_inputs = ExpansionRuleInputs(list=self.list, fighter=self)
        applicable_expansions = ContentEquipmentListExpansion.get_applicable_expansions(
            rule_inputs
        )
        if len(applicable_expansions) > 0:
            return True

        # Check if fighter has actual assigned gear from restricted categories
        for assignment in self.assignments_cached:
            if assignment.is_house_additional:
                return True

        return False

    @cached_property
    def house_additional_gearline_display(self):
        """
        Get display info for house-restricted and expansion equipment categories.
        Includes:
        1. restricted_equipment_categories on the house
        2. actual assigned gear categories
        3. available categories as a result of expansions
        """
        from gyrinx.content.models_.expansion import (
            ContentEquipmentListExpansion,
            ExpansionRuleInputs,
        )

        gearlines = []
        seen_categories = set()

        # 1. House restricted categories
        for (
            cat
        ) in self.content_fighter_cached.house.restricted_equipment_categories.all():
            seen_categories.add(cat.id)
            assignments = self.house_additional_assignments(cat)

            # Check if this category should be visible
            if cat.visible_only_if_in_equipment_list:
                # Only show if the fighter has equipment in this category
                # Check direct assignments, equipment list items, and expansions
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

                    # Also check expansion equipment
                    if not has_equipment_in_category:
                        rule_inputs = ExpansionRuleInputs(list=self.list, fighter=self)
                        expansion_equipment = (
                            ContentEquipmentListExpansion.get_expansion_equipment(
                                rule_inputs
                            )
                        )
                        if expansion_equipment.filter(category=cat).exists():
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

        # 2. Categories from actual assigned gear
        for assignment in self.assignments_cached:
            if (
                assignment.is_house_additional
                and assignment.content_equipment.category_id not in seen_categories
            ):
                cat = assignment.content_equipment.category
                seen_categories.add(cat.id)

                # Get all assignments for this category
                cat_assignments = self.house_additional_assignments(cat)

                gearlines.append(
                    {
                        "category": cat.name,
                        "id": cat.id,
                        "assignments": cat_assignments,
                        "filter": "equipment-list"
                        if cat.visible_only_if_in_equipment_list
                        else "all",
                    }
                )

        # 3. Categories from expansions
        rule_inputs = ExpansionRuleInputs(list=self.list, fighter=self)
        expansion_equipment = ContentEquipmentListExpansion.get_expansion_equipment(
            rule_inputs
        )
        for equipment in expansion_equipment.select_related("category"):
            cat = equipment.category
            if cat.id not in seen_categories and cat.restricted_to.exists():
                seen_categories.add(cat.id)

                # Get assignments for this category (including expansion items)
                assignments = self.house_additional_assignments(cat)

                # For visible_only_if_in_equipment_list categories, check if equipment exists
                if cat.visible_only_if_in_equipment_list:
                    # Equipment from expansion counts as being in equipment list
                    has_equipment_in_category = (
                        True  # We know there's expansion equipment
                    )

                    if not assignments and not has_equipment_in_category:
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

    @property
    def active_advancement_count(self):
        """Return count of non-archived advancements."""
        return self.advancements.filter(archived=False).count()

    def has_overridden_cost(self):
        return self.cost_override is not None or self.should_have_zero_cost

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
        assignment: ContentFighterDefaultAssignment = next(
            (da for da in self._default_assignments if da.id == assign.id), None
        )
        if assignment is None:
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

    def copy_attributes_to(self, target_fighter, include_equipment=True):
        """Copy attributes from this fighter to another fighter.

        Args:
            target_fighter: The fighter to copy attributes to
            include_equipment: Whether to copy equipment assignments (default True)
        """
        # Copy stat overrides
        target_fighter.cost_override = self.cost_override
        target_fighter.movement_override = self.movement_override
        target_fighter.weapon_skill_override = self.weapon_skill_override
        target_fighter.ballistic_skill_override = self.ballistic_skill_override
        target_fighter.strength_override = self.strength_override
        target_fighter.toughness_override = self.toughness_override
        target_fighter.wounds_override = self.wounds_override
        target_fighter.initiative_override = self.initiative_override
        target_fighter.attacks_override = self.attacks_override
        target_fighter.leadership_override = self.leadership_override
        target_fighter.cool_override = self.cool_override
        target_fighter.willpower_override = self.willpower_override
        target_fighter.intelligence_override = self.intelligence_override

        # Copy XP
        target_fighter.xp_current = self.xp_current
        target_fighter.xp_total = self.xp_total

        # Copy narrative
        target_fighter.narrative = self.narrative

        target_fighter.save()

        # Copy ManyToMany relationships
        target_fighter.skills.set(self.skills.all())
        target_fighter.disabled_skills.set(self.disabled_skills.all())
        target_fighter.disabled_rules.set(self.disabled_rules.all())
        target_fighter.custom_rules.set(self.custom_rules.all())

        # Copy disabled default assignments (considering conversions)
        disabled_defaults_to_copy = []
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
                disabled_defaults_to_copy.append(disabled_default)

        target_fighter.disabled_default_assignments.set(disabled_defaults_to_copy)
        target_fighter.disabled_pskyer_default_powers.set(
            self.disabled_pskyer_default_powers.all()
        )

        if include_equipment:
            # Copy equipment assignments that weren't converted from default assignments
            for assignment in self._direct_assignments():
                if assignment.from_default_assignment is not None:
                    # Skip assignments that were converted from default assignments
                    continue
                cloned_assignment = assignment.clone(list_fighter=target_fighter)

                # Handle nested linked fighters recursively
                if assignment.child_fighter:
                    original_child_fighter = assignment.child_fighter
                    cloned_child_fighter = cloned_assignment.child_fighter

                    if cloned_child_fighter:
                        # Recursively copy all attributes to the nested linked fighter
                        original_child_fighter.copy_attributes_to(
                            cloned_child_fighter, include_equipment=True
                        )

        # Copy psyker power assignments
        for power_assignment in self.psyker_powers.all():
            ListFighterPsykerPowerAssignment.objects.create(
                list_fighter=target_fighter,
                psyker_power=power_assignment.psyker_power,
            )

        # Copy advancements
        for advancement in self.advancements.all():
            # Create a new advancement for the target fighter
            ListFighterAdvancement.objects.create(
                fighter=target_fighter,
                advancement_type=advancement.advancement_type,
                stat_increased=advancement.stat_increased,
                skill=advancement.skill,
                equipment_assignment=advancement.equipment_assignment,
                description=advancement.description,
                xp_cost=advancement.xp_cost,
                cost_increase=advancement.cost_increase,
                owner=target_fighter.owner,
            )

        # Copy stat overrides (new ListFighterStatOverride model)
        for stat_override in self.stat_overrides.all():
            ListFighterStatOverride.objects.create(
                list_fighter=target_fighter,
                content_stat=stat_override.content_stat,
                value=stat_override.value,
                owner=target_fighter.owner,
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
        clone.disabled_skills.set(self.disabled_skills.all())
        clone.disabled_rules.set(self.disabled_rules.all())
        clone.custom_rules.set(self.custom_rules.all())

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
        # or assignments that were auto-created from equipment-equipment links
        for assignment in self._direct_assignments():
            if assignment.from_default_assignment is not None:
                # Skip assignments that were converted from default assignments
                # The clone will get these as default assignments instead
                continue
            if assignment.linked_equipment_parent is not None:
                # Skip assignments that were auto-created from equipment-equipment links
                # The clone will get these via the signal when the parent equipment is cloned
                continue
            cloned_assignment = assignment.clone(list_fighter=clone)

            # If the original assignment has a linked fighter (e.g., vehicle, exotic beast),
            # we need to copy all attributes from that linked fighter to the new linked fighter
            if assignment.child_fighter:
                original_child_fighter = assignment.child_fighter
                cloned_child_fighter = cloned_assignment.child_fighter

                if cloned_child_fighter:
                    # Copy all attributes (including equipment) from the original linked fighter
                    original_child_fighter.copy_attributes_to(
                        cloned_child_fighter, include_equipment=True
                    )

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

        # Clone stat overrides (new ListFighterStatOverride model)
        for stat_override in self.stat_overrides.all():
            ListFighterStatOverride.objects.create(
                list_fighter=clone,
                content_stat=stat_override.content_stat,
                value=stat_override.value,
                owner=clone.owner,
            )

        return clone

    @property
    def archive_with(self):
        return ListFighter.objects.filter(source_assignment__list_fighter=self)

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

        indexes = [
            # Postgres partial index to help with active fighter queries
            models.Index(
                name="idx_listfighter_list_active",
                fields=["list_id", "id"],
                condition=Q(archived=False),
            ),
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


class ListFighterEquipmentAssignmentQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ListFighterEquipmentAssignment`.
    """

    def with_related_data(self):
        """
        Optimize queries by selecting related content_equipment and list_fighter,
        and prefetching weapon profiles, accessories, and upgrades.

        This is the standard optimization pattern used throughout views
        to reduce N+1 query issues.
        """
        return self.select_related(
            "content_equipment", "list_fighter"
        ).prefetch_related(
            "weapon_profiles_field", "weapon_accessories_field", "upgrades_field"
        )


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
        db_index=True,
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

    upgrades_field = models.ManyToManyField(
        ContentEquipmentUpgrade,
        blank=True,
        related_name="fighter_equipment_assignments",
        help_text="The upgrades that this equipment assignment has.",
    )

    child_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="source_assignment",
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
        # TODO: There is nothing in the prefetch cache here
        return [
            VirtualWeaponProfile(p, self._mods)
            for p in self.content_equipment.contentweaponprofile_set.all()
            if p.cost == 0
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
        mods = [m for a in self.weapon_accessories_cached for m in a.modifiers.all()]
        mods += list(self.content_equipment_cached.modifiers.all())
        mods += [m for u in self.upgrades_field.all() for m in u.modifiers.all()]
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

    def calculated_cost_int(self):
        """Calculate the assignment's cost without any total_cost_override.

        This returns the sum of base cost, weapon profiles, accessories, and upgrades,
        ignoring the total_cost_override field. Useful for calculating cost deltas
        when the override is set or cleared.
        """
        return (
            self.base_cost_int_cached
            + self.weapon_profiles_cost_int_cached
            + self.weapon_accessories_cost_int_cached
            + self.upgrade_cost_int_cached
        )

    def has_total_cost_override(self):
        return self.total_cost_override is not None

    def cost_display(self):
        return format_cost_display(self.cost_int_cached)

    def _get_expansion_cost_override(
        self, content_equipment, weapon_profile, expansion_inputs
    ):
        """Helper method to get expansion cost override for equipment or weapon profile."""
        from gyrinx.content.models_.expansion import (
            ContentEquipmentListExpansion,
        )

        found_items = (
            ContentEquipmentListExpansion.get_applicable_expansion_items_for_equipment(
                expansion_inputs,
                content_equipment,
                weapon_profile,
                cost__isnull=False,
            )
        )

        if found_items and found_items[0].cost is not None:
            return found_items[0].cost

        return None

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

        # Check for expansion cost overrides first
        from gyrinx.content.models_.expansion import ExpansionRuleInputs

        expansion_inputs = ExpansionRuleInputs(
            list=self.list_fighter.list, fighter=self.list_fighter
        )
        expansion_cost = self._get_expansion_cost_override(
            content_equipment=self.content_equipment,
            weapon_profile=None,  # Base equipment cost, not profile
            expansion_inputs=expansion_inputs,
        )

        # If expansion has cost override, use it
        if expansion_cost is not None:
            return expansion_cost

        # Otherwise check normal equipment list overrides
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
            cost = profile.profile.cost_for_fighter_int()
            self._profile_cost_with_override_for_profile_cache[profile.profile.id] = (
                cost
            )
            return cost

        # Check for expansion cost overrides first
        from gyrinx.content.models_.expansion import ExpansionRuleInputs

        expansion_inputs = ExpansionRuleInputs(
            list=self.list_fighter.list, fighter=self.list_fighter
        )
        expansion_cost = self._get_expansion_cost_override(
            content_equipment=self.content_equipment,
            weapon_profile=profile.profile,
            expansion_inputs=expansion_inputs,
        )

        # If expansion has cost override, use it
        if expansion_cost is not None:
            cost = expansion_cost
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

    objects = ListFighterEquipmentAssignmentQuerySet.as_manager()

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
    if equipment_fighter_profile.exists() and not instance.child_fighter:
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
        instance.child_fighter = lf
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
    if instance.child_fighter:
        instance.child_fighter.delete()


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
    for prop in ["cost_int_cached", "assignments_cached", "_mods"]:
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
            # TODO: Expensive!
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

        # Check if the psyker power's discipline is available to this fighter
        available_disciplines = self.list_fighter.get_available_psyker_disciplines()
        if (
            not self.psyker_power.discipline.generic
            and self.psyker_power.discipline not in available_disciplines
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


class AdvancementStatMod(ContentModStatApplyMixin):
    """
    Virtual mod object that wraps a stat advancement.

    This allows stat advancements to be applied via the mod system rather than
    mutating fighter override fields. The mod is computed on-the-fly from the
    advancement data.

    Stat advancements always improve the stat by 1.
    """

    def __init__(self, stat_increased: str):
        self.stat = stat_increased
        self.mode = "improve"  # Advancements always improve stats
        self.value = "1"  # Always by 1

    def __repr__(self):
        return (
            f"<AdvancementStatMod stat={self.stat} mode={self.mode} value={self.value}>"
        )


class ListFighterAdvancement(AppBase):
    """Track advancements purchased by fighters using XP in campaign mode."""

    # Types of advancements
    ADVANCEMENT_STAT = "stat"
    ADVANCEMENT_SKILL = "skill"
    ADVANCEMENT_EQUIPMENT = "equipment"
    ADVANCEMENT_OTHER = "other"

    ADVANCEMENT_TYPE_CHOICES = [
        (ADVANCEMENT_STAT, "Characteristic Increase"),
        (ADVANCEMENT_SKILL, "New Skill"),
        (ADVANCEMENT_EQUIPMENT, "New Equipment"),
        (ADVANCEMENT_OTHER, "Other"),
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

    advancement_choice = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="The option selected in the advancement form",
    )

    # For stat advancements
    stat_increased = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        # Choices will be dynamically generated in the form
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

    # For equipment advancements
    equipment_assignment = models.ForeignKey(
        "content.ContentAdvancementAssignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="For equipment advancements, which assignment configuration was selected.",
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

    # Mod system flag - determines whether this advancement uses the mod system
    # or the legacy override fields for stat modifications.
    # New advancements default to True (use mods), existing advancements are False.
    uses_mod_system = models.BooleanField(
        default=True,
        help_text=(
            "If True, stat advancements use the mod system (computed at display time). "
            "If False, uses legacy override fields (mutates fighter state)."
        ),
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
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            return f"{self.fighter.name} - {self.skill.name}"
        elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT:
            if self.equipment_assignment:
                return f"{self.fighter.name} - {str(self.equipment_assignment)}"
        elif self.advancement_type == self.ADVANCEMENT_OTHER and self.description:
            return f"{self.fighter.name} - {self.description}"
        return f"{self.fighter.name} - Advancement"

    def get_stat_increased_display(self):
        # Import here to avoid circular imports
        from gyrinx.core.forms.advancement import AdvancementTypeForm

        return AdvancementTypeForm.all_stat_choices().get(
            f"stat_{self.stat_increased}", "Unknown"
        )

    @property
    def display_description(self):
        """Return a human-readable description of what this advancement provides."""
        if self.advancement_type == self.ADVANCEMENT_STAT:
            return self.get_stat_increased_display()
        elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
            return self.skill.name
        elif (
            self.advancement_type
            in (self.ADVANCEMENT_OTHER, self.ADVANCEMENT_EQUIPMENT)
            and self.description
        ):
            return self.description
        return "Advancement"

    def apply_advancement(self):
        """Apply this advancement to the fighter."""
        if self.advancement_type == self.ADVANCEMENT_STAT and self.stat_increased:
            # For mod-based advancements, skip setting override fields.
            # The stat improvement will be computed via the mod system at display time.
            if not self.uses_mod_system:
                # Legacy behavior: Apply stat increase via override fields
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
                        base_numeric = (
                            int(base_value.replace('"', "")) if base_value else 0
                        )
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
        elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT:
            if self.equipment_assignment:
                # Create equipment assignment with upgrades from advancement assignment
                assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=self.fighter,
                    content_equipment=self.equipment_assignment.equipment,
                )
                # Add the upgrades from the advancement assignment
                assignment.upgrades_field.set(
                    self.equipment_assignment.upgrades_field.all()
                )
        elif self.advancement_type == self.ADVANCEMENT_OTHER:
            # For "other" advancements, nothing specific to apply
            # The description is just stored for display purposes
            pass

        # If this is a promotion, use the category override to set the fighter's category
        if (
            self.advancement_choice
            and self.advancement_choice == "skill_promote_specialist"
        ):
            self.fighter.category_override = FighterCategoryChoices.SPECIALIST
            self.fighter.save()

        if (
            self.advancement_choice
            and self.advancement_choice == "skill_promote_champion"
        ):
            self.fighter.category_override = FighterCategoryChoices.CHAMPION
            self.fighter.save()

        # Deduct XP cost from fighter
        self.fighter.xp_current -= self.xp_cost
        self.fighter.save()

    def clean(self):
        """Validate the advancement."""
        if self.advancement_type == self.ADVANCEMENT_STAT and not self.stat_increased:
            raise ValidationError("Stat advancement requires a stat to be selected.")
        if self.advancement_type == self.ADVANCEMENT_SKILL and not self.skill:
            raise ValidationError("Skill advancement requires a skill to be selected.")
        if (
            self.advancement_type == self.ADVANCEMENT_EQUIPMENT
            and not self.equipment_assignment
        ):
            raise ValidationError(
                "Equipment advancement requires equipment assignment to be selected."
            )
        if self.advancement_type == self.ADVANCEMENT_OTHER and not self.description:
            raise ValidationError("Other advancement requires a description.")

        # Ensure only appropriate fields are set
        if self.advancement_type == self.ADVANCEMENT_STAT and (
            self.skill or self.equipment_assignment
        ):
            raise ValidationError(
                "Stat advancement should not have skill or equipment selected."
            )
        if self.advancement_type == self.ADVANCEMENT_SKILL and (
            self.stat_increased or self.equipment_assignment
        ):
            raise ValidationError(
                "Skill advancement should not have stat or equipment selected."
            )
        if self.advancement_type == self.ADVANCEMENT_EQUIPMENT and (
            self.stat_increased or self.skill
        ):
            raise ValidationError(
                "Equipment advancement should not have stat or skill selected."
            )
        if self.advancement_type == self.ADVANCEMENT_OTHER and (
            self.stat_increased or self.skill or self.equipment_assignment
        ):
            raise ValidationError(
                "Other advancement should not have stat, skill, or equipment selected."
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
