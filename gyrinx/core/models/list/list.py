import logging
from collections import OrderedDict, defaultdict
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import (
    Prefetch,
    Q,
    Subquery,
)
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.models.action import ListAction
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.facts import ListFacts
from gyrinx.core.models.history_aware_manager import HistoryAwareManager
from gyrinx.core.tasks import (
    refresh_list_facts,
)
from gyrinx.models import (
    FighterCategoryChoices,
    QuerySetOf,
    format_cost_display,
)
from gyrinx.tracing import span, traced
from gyrinx.tracker import track

if TYPE_CHECKING:
    from gyrinx.core.models.list.fighter import ListFighter

logger = logging.getLogger(__name__)
pylist = list


##
## Application Models
##


class ListQuerySet(models.QuerySet):
    def with_latest_actions(self):
        """
        Prefetch the latest action for each list.

        This enables the facts system by populating the `latest_actions` attribute,
        which is checked by the `can_use_facts` property.

        Use this lightweight method when only the facts prefetch is needed.
        For full optimization with related data, use `with_related_data()`.
        """
        return self.prefetch_related(
            Prefetch(
                "actions",
                queryset=ListAction.objects.order_by(
                    "list_id", "-created", "-id"
                ).distinct("list_id"),
                to_attr="latest_actions",
            ),
        )

    def with_related_data(self, with_fighters=False, packs=None):
        """
        Optimize queries by selecting related content_house and owner,
        and prefetching fighters with their related data.

        Args:
            with_fighters: If True, prefetch fighters with their related data.
            packs: Optional queryset of CustomContentPack. When provided,
                fighter prefetches for skills/rules use with_packs() so that
                ruleline/skilline can read from the prefetch cache instead
                of issuing per-fighter queries.
        """
        from gyrinx.core.models.list.campaign_state import ListAttributeAssignment

        qs = (
            self.with_latest_actions()
            .select_related(
                "content_house",
                "owner",
                "campaign",
                "original_list",
            )
            .prefetch_related(
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
                "packs",
            )
        )

        if with_fighters:
            qs = qs.with_fighter_data(packs=packs)

        return qs

    def with_fighter_data(self, packs=None):
        """
        Prefetch related fighter data for each list.

        Args:
            packs: Optional queryset of CustomContentPack for pack-aware
                skill/rule prefetching.
        """
        from gyrinx.core.models.list.fighter import ListFighter

        return self.prefetch_related(
            Prefetch(
                "listfighter_set",
                queryset=ListFighter.objects.with_group_keys().with_related_data(
                    packs=packs
                ),
            ),
        )


class ListManager(HistoryAwareManager):
    def create_with_facts(self, user=None, **kwargs):
        """
        Create a List and immediately calculate facts from database.

        Use this when the List is complete at creation (no m2m relationships
        need to be added). For Lists needing m2m setup first, use regular
        create() followed by manual facts_from_db().

        Args:
            user: Optional user for history tracking
            **kwargs: Fields for the new List

        Returns:
            The created List with correct cached values and dirty=False

        Note:
            Filters out rating_current, stash_current, and dirty since they're
            calculated fresh. Other *_current fields (like credits_current) are
            preserved. Creation and facts calculation are atomic.
        """
        # Filter out cached fields that we'll recalculate
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("rating_current", "stash_current", "dirty")
        }

        with transaction.atomic():
            # Use parent's create_with_user if user provided
            if user is not None:
                obj = super().create_with_user(user=user, **filtered_kwargs)
            else:
                obj = super().create(**filtered_kwargs)

            # Calculate and cache facts from database
            obj.facts_from_db(update=True)

        return obj


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
        "lore",
        blank=True,
        help_text="Lore for the gang in this list: their history and how to play them.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about the gang in this list.",
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

    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale due to content changes",
    )

    # Gang attributes (Alignment, Alliance, Affiliation, etc.)
    attributes = models.ManyToManyField(
        ContentAttributeValue,
        through="ListAttributeAssignment",
        blank=True,
        through_fields=("list", "attribute_value"),
        help_text="Gang attributes like Alignment, Alliance, Affiliation",
    )

    # Content packs subscribed to this list
    packs = models.ManyToManyField(
        "CustomContentPack",
        blank=True,
        related_name="subscribed_lists",
        help_text="Content packs subscribed to this list.",
    )

    # Per-user pins (private) and stars (public, with a count)
    pinned_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="pinned_lists",
        help_text="Users who have pinned this list to their own home page.",
    )
    starred_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="starred_lists",
        help_text="Users who have starred this list.",
    )

    history = HistoricalRecords()

    #
    # Wealth, Rating, Credits Behaviour
    #

    @admin.display(description="Cost / Wealth")
    @traced("list_cost_int")
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
    @traced("list_cost_int_cached")
    def cost_int_cached(self):
        """
        DEPRECATED: Legacy cache read path - now uses facts_with_fallback().

        This property is being phased out as part of #1215 (remove in-memory cache).
        It now delegates to facts_with_fallback() and emits tracking when called.
        In DEBUG mode, raises an exception to catch unexpected usage.
        """
        # Track that we hit the deprecated cache read path with diagnostic info
        has_prefetch = hasattr(self, "latest_actions")
        track(
            "deprecated_cost_int_cached_read",
            list_id=str(self.pk),
            can_use_facts=self.can_use_facts,
            is_dirty=self.dirty,
            has_latest_actions_prefetch=has_prefetch,
            has_actions=bool(self.latest_actions) if has_prefetch else None,
            facts_returns_none=self.facts() is None,
        )

        # In DEBUG mode, raise to catch unexpected usage during development
        if settings.DEBUG:
            raise RuntimeError(
                f"DEPRECATED: List.cost_int_cached was called for list {self.pk}. "
                "This code path should no longer be reached. "
                "Ensure the view uses with_latest_actions() prefetch so can_use_facts=True. "
                "See issue #1215."
            )

        # Fallback: use facts system instead of in-memory cache
        return self.facts_with_fallback().wealth

    def cost_display(self):
        """Display the list's total wealth (rating + stash + credits)."""
        facts = self.facts()
        if facts is not None:
            return format_cost_display(facts.wealth)
        return format_cost_display(self.facts_with_fallback().wealth)

    @cached_property
    def rating(self):
        return sum([f.cost_int_cached for f in self.active_fighters])

    @cached_property
    def rating_display(self):
        """Display the list's rating (sum of active fighter costs)."""
        if self.can_use_facts:
            facts = self.facts()
            if facts is not None:
                return format_cost_display(facts.rating)
        return format_cost_display(self.rating)

    @cached_property
    def stash_fighter_cost_int(self):
        return self.stash_fighter.cost_int() if self.stash_fighter else 0

    @cached_property
    def stash_fighter_cost_display(self):
        """Display the stash fighter's cost."""
        if self.can_use_facts:
            facts = self.facts()
            if facts is not None:
                return format_cost_display(facts.stash)
        return format_cost_display(self.stash_fighter_cost_int)

    @cached_property
    def credits_current_display(self):
        return format_cost_display(self.credits_current)

    @cached_property
    def wealth_current(self):
        return self.rating_current + self.stash_current + self.credits_current

    def facts(self) -> Optional[ListFacts]:
        """
        Return cached facts about this list.

        Fast O(1) read from cached fields.
        Returns None if dirty=True.
        """
        if self.dirty:
            return None

        return ListFacts(
            rating=self.rating_current,
            stash=self.stash_current,
            credits=self.credits_current,
        )

    def facts_with_fallback(self) -> ListFacts:
        """
        Get facts using cache if clean, otherwise calculate from scratch.

        MIGRATION PERIOD ONLY: This method provides a performance optimization
        during the rollout of the action system. It returns cached facts when
        available (dirty=False), falling back to the original calculation when
        the cache is stale or not yet populated.

        Intended for use in views like the homepage where many lists are
        displayed and we want to use cached values when available without
        forcing a full recalculation via facts_from_db().

        Unlike facts_from_db(), this method does NOT update the cache - it
        simply reads cached values or calculates on the fly without persisting.

        Once all lists have been bootstrapped with initial actions and the
        action system is fully rolled out, this method should be removed.

        Returns:
            ListFacts with rating, stash, and credits values.

        Monitoring:
            Emits 'facts_fallback' track event when fallback is used, allowing
            operators to monitor rollout progress via log aggregation.
        """
        # Try cached facts first (fast path - O(1) field reads)
        cached = self.facts()
        if cached is not None:
            return cached

        # Fallback to calculation (original behavior)
        track("facts_fallback", list_id=str(self.pk))

        # Enqueue a background refresh (fire-and-forget, doesn't block page loads)
        if settings.FEATURE_FACTS_FALLBACK_ENQUEUE:
            try:
                refresh_list_facts.enqueue(list_id=str(self.pk))
            except Exception as e:
                # Task system is new - don't break facts_with_fallback if it fails
                logger.warning(
                    f"Failed to enqueue facts refresh for list {self.pk}: {e}"
                )
                track("task_enqueue_failed", list_id=str(self.pk), error=str(e))

        return ListFacts(
            rating=self.rating,
            stash=self.stash_fighter_cost_int,
            credits=self.credits_current,
        )

    @property
    def debug_facts_in_sync(self) -> bool:
        """
        Check if cached facts match calculated values.

        Used by debug menu to show red flag when out of sync.
        """
        facts = self.facts()
        if facts is None:
            return False  # Dirty state means not in sync

        return (
            facts.rating == self.rating
            and facts.credits == self.credits_current
            and facts.stash == self.stash_fighter_cost_int
            and facts.wealth == self.wealth_current
        )

    @traced("list_set_dirty")
    def set_dirty(self, save: bool = True) -> None:
        """
        Mark this list as dirty.

        This is the terminal propagation point - List does not propagate further.

        Args:
            save: If True, immediately saves the dirty flag to the database.
                  Uses QuerySet.update() to bypass signals and avoid thrashing.
        """
        if not self.dirty:
            self.dirty = True
            if save:
                List.objects.filter(pk=self.pk).update(dirty=True)

    @traced("list_facts_from_db")
    def facts_from_db(self, update: bool = True) -> ListFacts:
        """
        Recalculate facts from database with lazy child evaluation.

        Args:
            update: If True, updates rating_current, stash_current and clears dirty flag.
                    Also passed to child fighters for recursive updates.

        Returns:
            ListFacts with recalculated values.

        Uses lazy evaluation: tries fighter.facts() first, only calling
        fighter.facts_from_db(update) if facts() returns None (dirty).
        This minimizes DB writes when fighter subtrees are already clean.

        Optimized to use prefetched data when available (e.g., after
        with_related_data(with_fighters=True)).
        """
        rating = 0
        stash = 0

        # Use prefetched fighters if available to avoid additional queries
        use_prefetch = (
            hasattr(self, "_prefetched_objects_cache")
            and "listfighter_set" in self._prefetched_objects_cache
        )

        if use_prefetch:
            # Filter in Python to preserve prefetched data
            fighters = [
                f
                for f in self._prefetched_objects_cache["listfighter_set"]
                if not f.archived
            ]
        else:
            # Fall back to queryset
            fighters = self.fighters()

        # Walk all fighters and calculate with lazy evaluation
        for fighter in fighters:
            # Try cached facts first
            fighter_facts = fighter.facts()
            if fighter_facts is None:
                # Dirty - recalculate and optionally update
                fighter_facts = fighter.facts_from_db(update=update)

            fighter_cost = fighter_facts.rating

            if fighter.content_fighter.is_stash:
                stash += fighter_cost
            else:
                rating += fighter_cost

        # Optionally update cache
        if update:
            # Clamp to non-negative — rating_current and stash_current are both
            # PositiveIntegerField. Aggregates can drift negative when an
            # individual fighter's cached rating_current goes negative (e.g.
            # stash drift after a kill, see handlers/fighter/kill.py).
            # Clamping is defence in depth; the per-fighter handlers are
            # expected to keep the underlying caches consistent.
            rating_value = max(0, rating)
            stash_value = max(0, stash)
            if stash < 0:
                track(
                    "list_stash_clamped_to_zero",
                    list_id=str(self.id),
                    raw_stash=stash,
                )
            # Use QuerySet.update() to bypass signals - facts_from_db is already
            # computing correct values with the latest data
            List.objects.filter(pk=self.pk).update(
                rating_current=rating_value,
                stash_current=stash_value,
                dirty=False,
            )
            # Update instance to reflect DB changes
            self.rating_current = rating_value
            self.stash_current = stash_value
            self.dirty = False

        return ListFacts(
            rating=rating,
            stash=stash,
            credits=self.credits_current,
        )

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

    @cached_property
    @traced("list_subscribed_packs_cached")
    def subscribed_packs_cached(self):
        """The content packs this list is subscribed to, as a list.

        Cached so repeated fighter queries (fighters/archived_fighters and
        their derived properties) share a single lightweight pack lookup.
        This is a subscriber read path, so it must NOT filter archived packs
        out — archived packs still apply to already-subscribed lists.
        """
        return list(self.packs.all())

    @traced("list_fighters")
    def fighters(self) -> QuerySetOf["ListFighter"]:
        # Pass the subscribed packs so skill/rule prefetches are pack-aware,
        # letting ruleline()/skilline() read from the prefetch cache instead
        # of issuing ~6 fallback queries per fighter.
        return self.listfighter_set.with_related_data(
            packs=self.subscribed_packs_cached
        ).filter(archived=False)

    @traced("list_archived_fighters")
    def archived_fighters(self) -> QuerySetOf["ListFighter"]:
        return self.listfighter_set.with_related_data(
            packs=self.subscribed_packs_cached
        ).filter(archived=True)

    @cached_property
    @traced("list_fighters_cached")
    def fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.fighters()

    @cached_property
    @traced("list_archived_fighters_cached")
    def archived_fighters_cached(self) -> QuerySetOf["ListFighter"]:
        return self.archived_fighters()

    @cached_property
    @traced("list_archived_fighters_count_cached")
    def archived_fighters_count_cached(self) -> int:
        """Number of archived fighters, as a single memoised COUNT.

        Avoids running a COUNT against the heavy annotated default-manager
        queryset multiple times when a template needs the count more than
        once (e.g. for a conditional plus the label).
        """
        return self.listfighter_set.filter(archived=True).count()

    @cached_property
    @traced("list_fighters_minimal_cached")
    def fighters_minimal_cached(self):
        return self.listfighter_set.filter(archived=False).values("id", "name")

    @cached_property
    @traced("list_active_fighters_minimal_cached")
    def active_fighters_minimal_cached(self):
        """Lightweight list of active (non-stash, non-archived) fighters.

        Returns just the fields needed to render navigation/switcher UI
        (id, name, content fighter type/category for its display name) as a
        single ``.values()`` query, preserving the default manager's
        category/sort ordering. Use this instead of ``active_fighters`` when
        you only need names and links — it avoids evaluating the full
        ~30-relation prefetch suite.

        Each row exposes ``content_fighter_name``, the same composite the
        ``ContentFighter.name`` property produces ("Type (Category)").
        """
        rows = (
            self.listfighter_set.filter(archived=False)
            .exclude(content_fighter__is_stash=True)
            .values(
                "id",
                "name",
                "content_fighter__type",
                "content_fighter__category",
            )
        )
        result = []
        for row in rows:
            category = row["content_fighter__category"]
            try:
                label = FighterCategoryChoices[category].label
            except KeyError:
                label = category
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "content_fighter_name": f"{row['content_fighter__type']} ({label})",
                }
            )
        return result

    @cached_property
    @traced("list_active_fighters")
    def active_fighters(self) -> QuerySetOf["ListFighter"]:
        """Get all fighters that could participate in a battle."""
        return self.fighters().exclude(content_fighter__is_stash=True)

    @cached_property
    @traced("list_stash_fighter")
    def stash_fighter(self):
        """Get the stash fighter for this list, if it exists.

        Uses prefetched data when available to avoid additional queries.
        """
        # Use prefetched fighters if available
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "listfighter_set" in self._prefetched_objects_cache
        ):
            for f in self._prefetched_objects_cache["listfighter_set"]:
                if not f.archived and f.content_fighter.is_stash:
                    return f
            return None

        # Fall back to queryset
        return self.fighters().filter(content_fighter__is_stash=True).first()

    @cached_property
    @traced("list_owner_cached")
    def owner_cached(self):
        return self.owner

    @cached_property
    @traced("list_pack_mods_by_target")
    def pack_mods_by_target(self) -> dict:
        """
        Pack-scoped house-rule mods that apply to this list, grouped by target.

        Returns a dict keyed by ``(content_type_id, object_id)`` to a list of
        polymorphic ``ContentMod`` instances. Empty when the list subscribes
        to no packs.

        Pack scoping is enforced strictly via ``CustomContentPackItem``: only
        applications attached to one of this list's packs (and not archived)
        are returned. We deliberately do not use ``with_packs()`` here — that
        helper also includes "base content" (rows not linked to any pack),
        which would let an admin- or fixture-created ``ContentModApplication``
        leak globally to every list.

        At most two queries when packs are subscribed: one to fetch the
        applications (via a subquery on ``CustomContentPackItem``), and a
        second to re-fetch the polymorphic ``ContentMod`` instances when any
        applications exist.

        Consumers (``ListFighter._mods``, ``ListFighterEquipmentAssignment._mods``,
        ``VirtualWeaponProfile`` construction sites) look up the dict by their
        target's ``(content_type_id, object_id)`` and union the returned mods
        into their existing mod list.

        Performance: uses ``self.packs.all()`` (not ``values_list``) so the
        ``packs`` prefetch from ``with_related_data`` is honoured.
        """

        from gyrinx.content.models import ContentMod, ContentModApplication
        from gyrinx.core.models.pack import CustomContentPackItem

        result: dict = defaultdict(list)
        # Use .all() so the with_related_data prefetch cache is honoured.
        # values_list() would bypass the cache and issue a new query.
        packs = list(self.packs.all())
        if not packs:
            return result

        pack_ids = [p.pk for p in packs]
        # Filter on content_type__app_label/model rather than calling
        # ContentType.objects.get_for_model(), to avoid an extra DB query
        # for the CT row (matches the pattern used by with_packs()).
        pack_application_ids = CustomContentPackItem.objects.filter(
            pack_id__in=pack_ids,
            archived=False,
            content_type__app_label="content",
            content_type__model="contentmodapplication",
        ).values("object_id")
        applications = (
            ContentModApplication.objects.all_content()
            .filter(pk__in=Subquery(pack_application_ids))
            .select_related("modifier", "target_content_type")
        )
        # ``modifier`` is a polymorphic FK — re-fetch as polymorphic instances
        # so isinstance(mod, ContentModStat/...) works downstream.
        mod_ids = [a.modifier_id for a in applications]
        polymorphic_mods = {m.pk: m for m in ContentMod.objects.filter(pk__in=mod_ids)}
        for app in applications:
            mod = polymorphic_mods.get(app.modifier_id)
            if mod is None:
                continue
            key = (app.target_content_type_id, app.target_object_id)
            result[key].append(mod)
        return result

    def pack_mods_for(self, target) -> list:
        """Return pack-scoped mods applying to ``target`` (a Content instance).

        ``target`` may be ``None`` (returns ``[]``) or any model instance whose
        ``(ContentType, pk)`` is a key in ``pack_mods_by_target``. Lookup is
        keyed by ``ContentType.id`` so polymorphic models resolve correctly.
        Returns ``[]`` when no pack mods exist for this list — short-circuits
        the ``ContentType.get_for_model()`` lookup, which would otherwise be
        the only DB query for an unsubscribed list.
        """
        if target is None:
            return []
        if not self.pack_mods_by_target:
            return []
        ct = ContentType.objects.get_for_model(type(target))
        return self.pack_mods_by_target.get((ct.id, target.pk), [])

    @cached_property
    @traced("list_content_house_cached")
    def content_house_cached(self):
        """Cache the content_house object to prevent repeated queries."""
        return self.content_house

    @cached_property
    @traced("list_content_house_name")
    def content_house_name(self):
        """Cache the house name which is frequently accessed in templates."""
        return self.content_house.name if self.content_house_id else ""

    @cached_property
    @traced("list_content_house_id_cached")
    def content_house_id_cached(self):
        """Cache the house ID to prevent object access."""
        return self.content_house_id

    @property
    def is_list_building(self):
        return self.status == self.LIST_BUILDING

    @property
    def is_campaign_mode(self):
        return self.status == self.CAMPAIGN_MODE

    def get_suggested_campaign_packs(self):
        """Return campaign packs not yet subscribed by this list.

        Checks both the pre-campaign M2M (self.campaigns) and the
        in-progress FK (self.campaign) to find all associated campaigns,
        then returns the union of their packs minus already-subscribed ones.
        """
        from gyrinx.core.models.pack import CustomContentPack

        subscribed_ids = set(self.packs.values_list("id", flat=True))

        # Campaigns associated via M2M (pre-campaign)
        campaign_ids = set(self.campaigns.values_list("id", flat=True))
        # Campaign associated via FK (in-progress)
        if self.campaign_id:
            campaign_ids.add(self.campaign_id)

        if not campaign_ids:
            return CustomContentPack.objects.none()

        return (
            CustomContentPack.objects.filter(
                campaigns__id__in=campaign_ids, archived=False
            )
            .exclude(id__in=subscribed_ids)
            .distinct()
            .select_related("owner")
        )

    @cached_property
    @traced("list_active_attributes_cached")
    def active_attributes_cached(self):
        if hasattr(self, "active_attribute_assignments"):
            return self.active_attribute_assignments

        # If not prefetched, filter directly
        return self.listattributeassignment_set.filter(archived=False).select_related(
            "attribute_value", "attribute_value__attribute"
        )

    @cached_property
    @traced("list_active_skill_trees_cached")
    def active_skill_trees_cached(self):
        return list(
            self.listskilltreeassignment_set.filter(archived=False).select_related(
                "skill_category"
            )
        )

    @cached_property
    @traced("list_gang_skill_slot_map")
    def gang_skill_slot_map(self):
        """Map of slot number -> chosen ContentSkillCategory for this gang."""
        return {a.slot: a.skill_category for a in self.active_skill_trees_cached}

    @cached_property
    @traced("list_gang_skill_rank_rules")
    def gang_skill_rank_rules(self):
        """
        House skill-rank rules grouped by (fighter_category, role) -> set of slots.

        Empty for non-gang-wide-skills houses. Cached once per list so the
        per-fighter skill-category resolution issues no extra queries.
        """
        if not self.content_house_cached.gang_wide_skills:
            return {}

        rules = defaultdict(set)
        for rule in self.content_house_cached.skill_rank_rules.all():
            rules[(rule.fighter_category, rule.role)].add(rule.slot)
        return rules

    @cached_property
    @traced("list_all_attributes")
    def all_attributes(self):
        # Build a map of attribute_id to value names

        assignment_map = defaultdict(list)
        # Performance: upstream of this, active_attribute_assignments has been prefetched
        # so we can iterate directly without hitting the database again.
        for attribute_assign in self.active_attributes_cached:
            attr_id = attribute_assign.attribute_value.attribute_id
            assignment_map[attr_id].append(attribute_assign.attribute_value.name)

        # Get all available attributes in a single query using values to avoid
        # object queries. Use with_packs() so pack-scoped attributes are
        # surfaced for lists subscribed to the pack.
        available_attributes = list(
            ContentAttribute.objects.with_packs(
                self.packs.all(), include_archived_items=True
            )
            .filter(Q(restricted_to__isnull=True) | Q(restricted_to=self.content_house))
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
    @traced("list_set_attributes")
    def set_attributes(self):
        """Attributes that have at least one value assigned."""
        return [a for a in self.all_attributes if a["assignments"]]

    @cached_property
    @traced("list_unset_attributes")
    def unset_attributes(self):
        """Attributes that have no value assigned."""
        return [a for a in self.all_attributes if not a["assignments"]]

    @cached_property
    @traced("list_expansion_equipment_by_category")
    def expansion_equipment_by_category(self) -> dict[str, pylist]:
        """
        Compute expansion equipment for all fighter categories once at list level.

        This is a performance optimization to avoid running expansion queries once
        per fighter. Instead, we compute expansion equipment for each possible
        fighter category once, and cache the results keyed by category.

        Returns:
            dict mapping fighter category string -> list of ContentEquipment instances
            with expansion_cost_override annotation.
        """
        from gyrinx.content.models import (
            ContentEquipmentListExpansion,
            ExpansionRuleInputs,
        )

        result = {}

        # Get all unique fighter categories that might be used
        # We only compute for categories that have fighters in this list to avoid waste
        categories_in_list = set()
        for fighter in self.listfighter_set.all():
            if not fighter.archived:
                cat = fighter.get_category()
                if cat:
                    categories_in_list.add(cat)

        # Also include generic expansion (no fighter category required)
        # This is computed once with fighter_category=None
        rule_inputs_no_fighter = ExpansionRuleInputs(list=self)
        base_equipment = ContentEquipmentListExpansion.get_expansion_equipment(
            rule_inputs_no_fighter
        )
        result[None] = pylist(
            base_equipment.select_related("category").prefetch_related(
                "category__restricted_to"
            )
        )

        # Compute for each category present in the list
        for category in categories_in_list:
            rule_inputs = ExpansionRuleInputs(list=self, fighter_category=category)
            equipment_qs = ContentEquipmentListExpansion.get_expansion_equipment(
                rule_inputs
            )
            result[category] = pylist(
                equipment_qs.select_related("category").prefetch_related(
                    "category__restricted_to"
                )
            )

        return result

    @cached_property
    def expansion_cost_lookup_by_category(self) -> dict[str, dict]:
        """
        Build a cost override lookup from expansion_equipment_by_category.

        This provides O(1) lookup for expansion cost overrides without
        additional database queries. Leverages the existing cached
        expansion_equipment_by_category property.

        Returns:
            dict mapping fighter category -> dict mapping equipment_id -> cost
        """
        result = {}
        for category, equipment_list in self.expansion_equipment_by_category.items():
            result[category] = {
                eq.id: eq.expansion_cost_override
                for eq in equipment_list
                if hasattr(eq, "expansion_cost_override")
            }
        return result

    @cached_property
    @traced("list_fighter_type_summary")
    def fighter_type_summary(self):
        """
        Returns a summary of fighter types and their counts for active fighters.

        Excludes archived fighters, dead fighters, stash fighters, and vehicles (vehicles are not fighters).

        Performance: This must use prefetched listfighter_set data from with_related_data,
        so it doesn't issue any additional queries.

        Returns:
            dict with keys:
                'total': int, total number of active fighters
                'type_totals': list of dicts with 'type', 'category', and 'count' keys
        """

        # Use OrderedDict to maintain the order fighters are encountered
        type_counts = OrderedDict()

        # Iterate over prefetched listfighter_set and filter in memory to avoid queries
        # Exclude archived fighters, stash fighters, and vehicles (vehicles are not fighters)
        active_fighters = [
            f
            for f in self.listfighter_set.all()
            if not f.archived
            and not f.is_dead
            and not f.content_fighter.is_stash
            and not f.content_fighter.is_vehicle
        ]
        for fighter in active_fighters:
            # We use a compound key of (type, category) to differentiate types with same name but different categories,
            # and so we can extract both later for the output.
            fighter_type = (fighter.content_fighter.type, fighter.get_category_label())
            type_counts[fighter_type] = type_counts.get(fighter_type, 0) + 1

        # Convert to the expected format while preserving order
        type_totals = [
            {"type": fighter_type, "category": category, "count": count}
            for (fighter_type, category), count in type_counts.items()
        ]

        total = sum(item["count"] for item in type_totals)

        summary = {
            "total": total,
            "type_totals": type_totals,
        }

        return summary

    @cached_property
    @traced("list_latest_action")
    def latest_action(self) -> Optional[ListAction]:
        """Get the latest ListAction for this list, if any.

        Performance: This requires prefetching latest_actions via with_related_data().
        """
        if hasattr(self, "latest_actions") and self.latest_actions:
            return self.latest_actions[0]

        return ListAction.objects.latest_for_list(self.id)

    @property
    def can_use_facts(self) -> bool:
        """
        Check if facts system can be used for display methods.

        Returns True only if:
        - latest_actions was prefetched via with_related_data()
        - AND there is at least one action (list has action tracking)

        Returns False if:
        - Not prefetched (to avoid database query)
        - Or prefetched but empty (no action tracking yet)

        This is used by display methods to avoid expensive cost_int calculations
        when cached facts are available.
        """
        # Only check prefetched data - never query the database
        if hasattr(self, "latest_actions"):
            return bool(self.latest_actions)
        return False

    @traced("list_create_action")
    def create_action(
        self,
        update_credits: bool = False,
        skip_apply: Optional[list[str]] = None,
        **kwargs,
    ) -> Optional[ListAction]:
        """
        Create a ListAction to track changes to this list.

        Args:
            update_credits: If True, applies credits_delta to the list's credits_current.
                           This works regardless of whether the feature flag is enabled -
                           credits are always updated when this is True.
            skip_apply: List of delta field names to skip applying. Valid values:
                       ["rating", "stash"]. Use this when facts_from_db(update=True)
                       has already updated rating_current/stash_current. The deltas
                       are still recorded in the action for history.
                       Note: credits is controlled by update_credits, not this param.
            **kwargs: Additional fields for the ListAction (action_type, description,
                     rating_delta, stash_delta, credits_delta, etc.)

        Returns:
            The created ListAction if feature flag is enabled, None otherwise.
            Note: Even when returning None, credits are still updated if update_credits=True.
        """
        skip_apply = skip_apply or []
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
            # skip_apply allows skipping rating/stash when already applied via facts_from_db
            rating_delta = (
                kwargs.get("rating_delta", 0) if "rating" not in skip_apply else 0
            )
            stash_delta = (
                kwargs.get("stash_delta", 0) if "stash" not in skip_apply else 0
            )
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
        from gyrinx.core.models.list.fighter import ListFighter

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

        # Create the stash ListFighter with correct cached values
        new_stash = ListFighter.objects.create_with_facts(
            name="Stash",
            content_fighter=stash_fighter,
            list=self,
            owner=owner,
        )

        return new_stash

    def spend_credits(self, amount, description="Purchase"):
        """Spend credits from this list's available credits.

        Handles both positive amounts (spending) and negative amounts (gaining).
        Negative cost equipment (e.g., Goliath gene-smithing) results in credit gains.

        Args:
            amount: The number of credits to spend (positive) or gain (negative)
            description: Description of what the credits are being spent on (for error messages)

        Returns:
            True if the credits were successfully spent/gained

        Raises:
            ValidationError: If the list doesn't have enough credits for positive amounts
        """
        if amount < 0:
            # Negative cost = credit gain (e.g., gene-smithing with negative cost)
            self.credits_current -= amount  # Subtracting negative = adding
            self.save(update_fields=["credits_current"])
            return True

        if self.credits_current < amount:
            raise ValidationError(
                f"Insufficient credits. {description} costs {amount}¢, "
                f"but you only have {self.credits_current}¢ available."
            )

        self.credits_current -= amount
        self.save(update_fields=["credits_current"])
        return True

    @traced("list_clone")
    def clone(self, name=None, owner=None, for_campaign=None, **kwargs) -> "List":
        """Clone the list, creating a new list with the same fighters.

        Args:
            name: Name for the clone (defaults to original name + suffix)
            owner: Owner of the clone (defaults to original owner)
            for_campaign: If provided, creates a campaign mode clone for this campaign
            **kwargs: Additional fields to set on the clone
        """
        from gyrinx.core.models.list.campaign_state import (
            ListAttributeAssignment,
            ListSkillTreeAssignment,
        )

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
            "notes": self.notes,
            "theme_color": self.theme_color,
            # Don't copy rating_current/stash_current - they'll be recalculated
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

        # Note: ListAction creation for clones is handled by handle_list_clone handler.
        # The model method only handles the data cloning, not side effects like actions.

        # Clone pack subscriptions
        clone.packs.set(self.packs.all())

        # Clone attributes first - this must happen before fighters so that
        # equipment cost calculations can use expansion costs from affiliations
        # See: https://github.com/gyrinx-app/gyrinx/issues/1333
        for attribute_assignment in self.listattributeassignment_set.filter(
            archived=False
        ):
            ListAttributeAssignment.objects.create(
                list=clone,
                attribute_value=attribute_assignment.attribute_value,
            )

        # Clone gang-wide skill-tree picks
        for skill_tree_assignment in self.listskilltreeassignment_set.filter(
            archived=False
        ):
            ListSkillTreeAssignment.objects.create(
                list=clone,
                slot=skill_tree_assignment.slot,
                skill_category=skill_tree_assignment.skill_category,
            )

        with span("list_clone_fighters"):
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
                # Update stash fighter's rating after all equipment is cloned
                # (assignment.clone only updates the assignment, not the fighter)
                new_stash.facts_from_db(update=True)

        track(
            "list_cloned",
            original_list=str(self.id),
            cloned_list=str(clone.id),
            for_campaign=str(for_campaign.id) if for_campaign else "",
        )

        # Always recalculate cached values after cloning
        # Cloning is not part of the action/propagation system - it needs explicit recalculation
        clone.facts_from_db(update=True)

        return clone

    class Meta:
        verbose_name = "List"
        verbose_name_plural = "Lists"
        ordering = ["name"]

    def __str__(self):
        return self.name

    objects = ListManager.from_queryset(ListQuerySet)()
