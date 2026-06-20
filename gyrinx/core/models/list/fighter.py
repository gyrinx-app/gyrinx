import logging
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.contrib import admin
from django.contrib.postgres.aggregates import ArrayAgg
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
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
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterHouseOverride,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentRule,
    ContentModFighterStat,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
    ContentStatline,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    RulelineDisplay,
    StatlineDisplay,
)
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.facts import FighterFacts
from gyrinx.core.models.list._common import (
    ALLOWED_CATEGORY_OVERRIDES,
    validate_category_override,
)
from gyrinx.core.models.list.list import List
from gyrinx.core.models.util import ModContext
from gyrinx.models import (
    FighterCategoryChoices,
    QuerySetOf,
    format_cost_display,
)
from gyrinx.tracing import traced

if TYPE_CHECKING:
    from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment
    from gyrinx.core.models.list.virtual import (
        VirtualListFighterEquipmentAssignment,
    )

logger = logging.getLogger(__name__)
pylist = list


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

    def create_with_facts(self, user=None, **kwargs):
        """
        Create a ListFighter and immediately calculate facts from database.

        Use this when the fighter is complete at creation (no equipment
        assignments need to be added). For fighters needing equipment first,
        use regular create() followed by manual facts_from_db().

        Args:
            user: Optional user for history tracking
            **kwargs: Fields for the new ListFighter

        Returns:
            The created ListFighter with correct cached values and dirty=False

        Note:
            Filters out rating_current and dirty since they're calculated fresh.
            Creation and facts calculation are atomic.
        """
        # Filter out cached fields that we'll recalculate
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k not in ("rating_current", "dirty")
        }

        with transaction.atomic():
            obj = self.model(**filtered_kwargs)
            # Use save_with_user for proper history tracking (from HistoryMixin)
            obj.save_with_user(user=user)

            # Calculate and cache facts from database
            obj.facts_from_db(update=True)

        return obj


class ListFighterQuerySet(models.QuerySet):
    """
    Custom QuerySet for :model:`content.ListFighter`.
    """

    def with_related_data(self, packs=None):
        """
        Optimize queries by selecting related content_fighter and list,
        and prefetching injuries and equipment assignments.

        This is the standard optimization pattern used throughout views
        to reduce N+1 query issues.

        Args:
            packs: Optional queryset of CustomContentPack. When provided,
                prefetches for skills/rules use with_packs() so that
                ruleline/skilline can read from the prefetch cache instead
                of issuing per-fighter queries.
        """
        # When packs are provided, use pack-aware querysets for skill/rule
        # prefetches so that ruleline() and skilline() hit the cache.
        if packs is not None:
            skills_qs = ContentSkill.objects.with_packs(
                packs, include_archived_items=True
            )
            rules_qs = ContentRule.objects.with_packs(
                packs, include_archived_items=True
            )
            skill_prefetches = [
                Prefetch("skills", queryset=skills_qs),
                Prefetch("disabled_skills", queryset=skills_qs),
                Prefetch("content_fighter__skills", queryset=skills_qs),
            ]
            rule_prefetches = [
                Prefetch("disabled_rules", queryset=rules_qs),
                Prefetch("custom_rules", queryset=rules_qs),
                Prefetch("content_fighter__rules", queryset=rules_qs),
            ]
        else:
            skill_prefetches = [
                "skills",
                "disabled_skills",
                "content_fighter__skills",
            ]
            rule_prefetches = [
                "disabled_rules",
                "custom_rules",
                "content_fighter__rules",
            ]

        return (
            self.prefetch_related(None)  # Clear inherited lookups to prevent
            # doubling when called on a cached queryset (e.g. from
            # with_fighter_data's Prefetch). Without this, Prefetch objects
            # with custom querysets would appear twice and Django raises
            # ValueError("lookup was already seen with a different queryset").
            .select_related(
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
                "counters",
                *skill_prefetches,
                *rule_prefetches,
                "disabled_default_assignments",
                "advancements",
                "stat_overrides",
                Prefetch(
                    "listfighterequipmentassignment_set__content_equipment__contentweaponprofile_set",
                    queryset=ContentWeaponProfile.objects.all_content(),
                ),
                Prefetch(
                    "listfighterequipmentassignment_set__weapon_profiles_field",
                    queryset=ContentWeaponProfile.objects.all_content(),
                ),
                # Use all_content() so pack-scoped accessories are visible
                # through this prefetch — the default M2M manager would
                # exclude them, hiding them on display surfaces.
                Prefetch(
                    "listfighterequipmentassignment_set__weapon_accessories_field",
                    queryset=ContentWeaponAccessory.objects.all_content().prefetch_related(
                        "modifiers"
                    ),
                ),
                "listfighterequipmentassignment_set__content_equipment__modifiers",
                "listfighterequipmentassignment_set__upgrades_field__modifiers",
                "content_fighter__counters",
                "content_fighter__house",
                "content_fighter__house__restricted_equipment_categories",
                "content_fighter__house__restricted_equipment_categories__restricted_to",
                Prefetch(
                    "content_fighter__default_assignments__equipment__contentweaponprofile_set",
                    queryset=ContentWeaponProfile.objects.all_content(),
                ),
                # Default-assignment M2Ms also need all_content() so that
                # pack-scoped weapon profiles / accessories chosen on a
                # ContentFighterDefaultAssignment aren't dropped by the
                # default ContentManager when the fighter is hired.
                Prefetch(
                    "content_fighter__default_assignments__weapon_profiles_field",
                    queryset=ContentWeaponProfile.objects.all_content(),
                ),
                Prefetch(
                    "content_fighter__default_assignments__weapon_accessories_field",
                    queryset=ContentWeaponAccessory.objects.all_content().prefetch_related(
                        "modifiers"
                    ),
                ),
                # Prefetch equipment list items for cost override lookups
                "content_fighter__contentfighterequipmentlistitem_set",
                "legacy_content_fighter__contentfighterequipmentlistitem_set",
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
                _pack_prefetched=Value(packs is not None),
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
        from gyrinx.core.models.list.advancement import ListFighterAdvancement

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
        from gyrinx.core.models.list.campaign_state import ListFighterStatOverride

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
        db_index=True,
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

    rating_current = models.IntegerField(
        default=0,
        help_text="Cached total rating of this fighter (base + equipment + advancements). Can be negative if equipment has negative cost.",
    )

    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale",
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

    # Notes (public, shown on Notes page)
    notes = models.TextField(
        blank=True,
        help_text="Notes about the fighter",
    )

    # Private notes (only visible to list owner)
    private_notes = models.TextField(
        blank=True,
        help_text="Private notes about the fighter (only visible to you)",
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
    def equipment_list_items_lookup(self) -> dict | None:
        """
        Return a lookup dict for equipment list cost overrides.

        Performance optimization: builds an index from prefetched equipment list
        items to avoid individual DB queries in _equipment_cost_with_override().

        Returns:
            dict mapping (equipment_id, weapon_profile_id) -> ContentFighterEquipmentListItem
            If multiple items match (legacy + base), returns the legacy one.
            Returns None if data was not prefetched (caller should use DB query).
        """
        # Check if the equipment list items were prefetched
        content_fighter = self.content_fighter
        has_prefetch = (
            hasattr(content_fighter, "_prefetched_objects_cache")
            and "contentfighterequipmentlistitem_set"
            in content_fighter._prefetched_objects_cache
        )
        if not has_prefetch:
            return None

        lookup = {}

        # Process base fighter's equipment list (add first)
        items = content_fighter.contentfighterequipmentlistitem_set.all()
        for item in items:
            key = (item.equipment_id, item.weapon_profile_id)
            lookup[key] = item

        # Process legacy fighter's equipment list (overrides base)
        if self.legacy_content_fighter:
            legacy_has_prefetch = (
                hasattr(self.legacy_content_fighter, "_prefetched_objects_cache")
                and "contentfighterequipmentlistitem_set"
                in self.legacy_content_fighter._prefetched_objects_cache
            )
            if legacy_has_prefetch:
                items = self.legacy_content_fighter.contentfighterequipmentlistitem_set.all()
                for item in items:
                    key = (item.equipment_id, item.weapon_profile_id)
                    # Legacy overrides base
                    lookup[key] = item

        return lookup

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
    @traced("listfighter_category_terms")
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
    @traced("listfighter_fully_qualified_name")
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
    @traced("listfighter_cost_int")
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
    @traced("listfighter_cost_int_cached")
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
    @traced("listfighter_base_cost_int")
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

    @traced("listfighter_base_cost_before_override")
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
    @traced("listfighter_advancement_cost_int")
    def _advancement_cost_int(self):
        # Dead, captured, or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            return 0

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

    @admin.display(description="Total Cost Display")
    @traced("listfighter_cost_display")
    def cost_display(self):
        """Display the fighter's total cost."""
        if self.can_use_facts:
            facts = self.facts()
            if facts is not None:
                return format_cost_display(facts.rating)
        return format_cost_display(self.cost_int_cached)

    def facts(self) -> Optional[FighterFacts]:
        """
        Return cached facts about this fighter.

        Fast O(1) read from rating_current field.
        Returns None if dirty=True.
        """
        if self.dirty:
            return None

        return FighterFacts(rating=self.rating_current)

    @property
    def can_use_facts(self) -> bool:
        """
        Check if facts system can be used for display methods.

        Delegates to parent list's can_use_facts property.
        Relies on list being prefetched via with_related_data().
        """
        return self.list.can_use_facts

    @property
    def debug_facts_in_sync(self) -> bool:
        """
        Check if cached facts match calculated values.

        Used by debug menu to show red flag when out of sync.
        Uses cost_int_cached to avoid expensive recalculation.
        """
        facts = self.facts()
        if facts is None:
            return False  # Dirty state means not in sync

        return facts.rating == self.cost_int_cached

    @traced("listfighter_set_dirty")
    def set_dirty(self, save: bool = True) -> None:
        """
        Mark this fighter as dirty and propagate to parent list.

        Args:
            save: If True, immediately saves the dirty flag to the database.
                  Uses QuerySet.update() to bypass signals and avoid thrashing.
        """
        if not self.dirty:
            self.dirty = True
            if save:
                ListFighter.objects.filter(pk=self.pk).update(dirty=True)

        # Propagate to parent list
        self.list.set_dirty(save=save)

    @traced("list_fighter_facts_from_db")
    def facts_from_db(self, update: bool = True) -> FighterFacts:
        """
        Recalculate facts from database with lazy child evaluation.

        Args:
            update: If True, updates rating_current and clears dirty flag.
                    Also passed to child assignments for recursive updates.

        Returns:
            FighterFacts with recalculated rating.

        Uses lazy evaluation: tries assignment.facts() first, only calling
        assignment.facts_from_db(update) if facts() returns None (dirty).
        This minimizes DB writes when equipment subtree is already clean.
        """
        from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment

        # Captured or sold fighters contribute 0 to gang total cost
        if self.should_have_zero_cost:
            rating = 0
        else:
            # Calculate base cost (content fighter + overrides)
            base_cost = self._base_cost_int

            # Include advancement cost increases (uses annotation if prefetched)
            advancement_cost = self._advancement_cost_int

            # Calculate equipment cost with lazy evaluation
            # Note: assignments() returns VirtualListFighterEquipmentAssignment wrappers
            equipment_cost = 0
            for virtual_assignment in self.assignments():
                # Check if this is a real assignment (not default equipment)
                real_assignment = virtual_assignment._assignment
                if isinstance(real_assignment, ListFighterEquipmentAssignment):
                    # Try cached facts first
                    assignment_facts = real_assignment.facts()
                    if assignment_facts is None:
                        # Dirty - recalculate and optionally update
                        assignment_facts = real_assignment.facts_from_db(update=update)
                    equipment_cost += assignment_facts.rating
                else:
                    # Default assignments (ContentFighterDefaultAssignment) or None
                    # have cost 0 or use the virtual wrapper's cost_int()
                    equipment_cost += virtual_assignment.cost_int()

            rating = base_cost + advancement_cost + equipment_cost

        # Optionally update cache
        if update:
            # Use QuerySet.update() to bypass signals - facts_from_db is already
            # computing correct values with the latest data
            # Note: rating can be negative if equipment has negative cost
            ListFighter.objects.filter(pk=self.pk).update(
                rating_current=rating,
                dirty=False,
            )
            # Update instance to reflect DB changes
            self.rating_current = rating
            self.dirty = False

        return FighterFacts(rating=rating)

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
    @traced("listfighter_mods")
    def _mods(self):
        from gyrinx.core.models.list.advancement import AdvancementStatMod

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

        # Pack-scoped house-rule mods targeting this fighter's content_fighter
        # (e.g. "fighter X gets +1 toughness as a house rule"). Empty when no
        # packs are subscribed.
        pack_mods = list(self.list.pack_mods_for(self.content_fighter))

        return equipment_mods + injury_mods + advancement_mods + pack_mods

    @traced("listfighter_apply_mods")
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

    def _base_skill_categories(self, role):
        """
        Base (pre-equipment-mod) primary/secondary skill categories for this fighter.

        For a gang-wide-skills house, the categories come from the gang's ranked
        skill-tree picks combined with the house's rank rules for this fighter's
        rank (``get_category()``); the fighter template's own primary/secondary
        skill trees are ignored. For all other houses, the categories come from
        the fighter template's M2M fields (pack-aware).

        ``role`` is "primary" or "secondary".
        """
        if self.list.content_house_cached.gang_wide_skills:
            slot_map = self.list.gang_skill_slot_map
            slots = self.list.gang_skill_rank_rules.get(
                (self.get_category(), role), set()
            )
            return {slot_map[slot] for slot in slots if slot in slot_map}

        # Default: base categories from the content fighter template.
        # Use with_packs() to include pack skill categories — the default
        # manager on ContentSkillCategory excludes pack content.
        filter_kwarg = "primary_fighters" if role == "primary" else "secondary_fighters"
        packs = self.list.packs.all()
        return set(
            ContentSkillCategory.objects.with_packs(
                packs, include_archived_items=True
            ).filter(**{filter_kwarg: self.content_fighter})
        )

    @traced("listfighter_get_primary_skill_categories")
    def get_primary_skill_categories(self):
        """
        Get primary skill categories for this fighter, including equipment modifications.
        """
        from gyrinx.content.models import ContentModSkillTreeAccess

        categories = self._base_skill_categories("primary")

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

    @traced("listfighter_get_secondary_skill_categories")
    def get_secondary_skill_categories(self):
        """
        Get secondary skill categories for this fighter, including equipment modifications.
        """
        from gyrinx.content.models import ContentModSkillTreeAccess

        categories = self._base_skill_categories("secondary")

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

    @traced("listfighter_get_available_psyker_disciplines")
    def get_available_psyker_disciplines(self):
        """
        Get available psyker disciplines for this fighter, including equipment modifications.

        Pack-aware: discipline assignments authored in packs the list
        subscribes to are also visible. The reverse-FK
        ``content_fighter.psyker_disciplines.all()`` would otherwise hit the
        default Content manager and exclude pack-authored rows.
        """
        from gyrinx.content.models import ContentModPsykerDisciplineAccess
        from gyrinx.content.models.psyker import (
            ContentFighterPsykerDisciplineAssignment,
        )

        base_assignments = (
            ContentFighterPsykerDisciplineAssignment.objects.with_packs(
                self.list.packs.all(), include_archived_items=True
            )
            .filter(fighter=self.content_fighter)
            .select_related("discipline")
        )
        disciplines = {assignment.discipline for assignment in base_assignments}

        # Apply equipment modifications
        for mod in self._mods:
            if isinstance(mod, ContentModPsykerDisciplineAccess):
                if mod.mode == "add":
                    disciplines.add(mod.discipline)
                elif mod.mode == "remove":
                    disciplines.discard(mod.discipline)

        return disciplines

    @traced("listfighter_statmods")
    def _statmods(self, stat: str):
        """
        Get the stat mods for this fighter.

        Includes both ContentModFighterStat (from equipment/injuries) and
        AdvancementStatMod (from stat advancements using the mod system).
        """
        from gyrinx.core.models.list.advancement import AdvancementStatMod

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
    @traced("listfighter_statline")
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
    @traced("listfighter_content_fighter_statline")
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

    @property
    def _has_pack_aware_prefetch(self):
        """Check if this fighter was loaded with pack-aware prefetch data.

        When with_related_data(packs=...) is used, the prefetch stores a
        _pack_aware marker on the queryset result. When using default manager
        prefetch (no packs), this marker is absent and we need fallback queries.
        """
        # If the fighter has the annotation from with_related_data(), check
        # whether the prefetch cache was built with pack-aware querysets.
        # The simplest signal: check if list.packs is non-empty but the
        # prefetched rules on content_fighter are from the default manager.
        # We use a flag set during prefetch construction instead.
        return getattr(self, "_pack_prefetched", False)

    @cached_property
    @traced("listfighter_ruleline")
    def ruleline(self):
        """
        Get the ruleline for this fighter.

        Uses prefetched data when available (via pack-aware Prefetch objects
        set up by with_related_data(packs=...)). Falls back to with_packs()
        queries when prefetch data was not pack-aware.
        """
        if self._has_pack_aware_prefetch:
            # Fast path: read from pack-aware prefetch cache (0 queries)
            rules = list(self.content_fighter_cached.rules.all())
            disabled_rules_set = set(self.disabled_rules.all())
            custom_rules = list(self.custom_rules.all())
        else:
            # Fallback: explicit pack-scoped queries
            packs = self.list.packs.all()
            rules_qs = ContentRule.objects.with_packs(
                packs, include_archived_items=True
            )
            rules = list(rules_qs.filter(contentfighter=self.content_fighter_cached))
            disabled_rules_set = set(rules_qs.filter(disabled_by_fighters=self))
            custom_rules = list(rules_qs.filter(custom_for_fighters=self))

        equipment_modded = set()
        user_modded = set()
        rules = [r for r in rules if r not in disabled_rules_set]

        # Apply modifications from equipment/items
        for mod in self._rulemods:
            if mod.mode == "add" and mod.rule not in rules:
                rules.append(mod.rule)
                equipment_modded.add(mod.rule)
            elif mod.mode == "remove" and mod.rule in rules:
                rules.remove(mod.rule)

        # Add custom rules
        for custom_rule in custom_rules:
            if custom_rule not in rules:
                rules.append(custom_rule)
                user_modded.add(custom_rule)

        def _make_display(rule):
            if rule in equipment_modded:
                return RulelineDisplay(
                    rule.name,
                    modded=True,
                    source=RulelineDisplay.SOURCE_EQUIPMENT,
                )
            elif rule in user_modded:
                return RulelineDisplay(
                    rule.name,
                    modded=True,
                    source=RulelineDisplay.SOURCE_USER,
                )
            return RulelineDisplay(rule.name)

        return [_make_display(rule) for rule in rules]

    # Assignments

    @traced("listfighter_assign")
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
        from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment

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

    @traced("listfighter_direct_assignments")
    def _direct_assignments(self) -> QuerySetOf["ListFighterEquipmentAssignment"]:
        return self.listfighterequipmentassignment_set.all()

    @cached_property
    @traced("listfighter_default_assignments")
    def _default_assignments(self):
        # Performance: this is done in Python because when we prefetch these, these queries are
        # already optimized and won't hit the database again.
        return [
            a
            for a in self.content_fighter_cached.default_assignments.all()
            if a not in self.disabled_default_assignments.all()
        ]

    @traced("listfighter_assignments")
    def assignments(self) -> pylist["VirtualListFighterEquipmentAssignment"]:
        from gyrinx.core.models.list.virtual import (
            VirtualListFighterEquipmentAssignment,
        )

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
    @traced("listfighter_parent_list_fighter")
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

    @traced("listfighter_skilline")
    def skilline(self):
        """Get the skilline for this fighter.

        Uses prefetched data when available (via pack-aware Prefetch objects
        set up by with_related_data(packs=...)). Falls back to with_packs()
        queries when prefetch data was not pack-aware.
        """
        if self._has_pack_aware_prefetch:
            # Fast path: read from pack-aware prefetch cache (0 queries)
            default_skills = list(self.content_fighter_cached.skills.all())
            disabled_skills_set = set(self.disabled_skills.all())
            user_skills = list(self.skills.all())
        else:
            # Fallback: explicit pack-scoped queries
            packs = self.list.packs.all()
            skills_qs = ContentSkill.objects.with_packs(
                packs, include_archived_items=True
            )
            default_skills = list(
                skills_qs.filter(contentfighter=self.content_fighter_cached)
            )
            disabled_skills_set = set(skills_qs.filter(disabled_for_fighters=self))
            user_skills = list(skills_qs.filter(listfighter=self))

        default_skills = [s for s in default_skills if s not in disabled_skills_set]
        skills = set(default_skills + user_skills)

        # Apply modifications from equipment/items
        for mod in self._skillmods:
            if mod.mode == "add" and mod.skill not in skills:
                skills.add(mod.skill)
            elif mod.mode == "remove" and mod.skill in skills:
                skills.remove(mod.skill)
        return [s.name for s in skills]

    @cached_property
    @traced("listfighter_skilline_cached")
    def skilline_cached(self):
        return self.skilline()

    @traced("listfighter_weapons")
    def weapons(self):
        return sorted(
            [e for e in self.assignments_cached if e.is_weapon_cached],
            key=lambda e: e.name(),
        )

    @cached_property
    def weapons_cached(self):
        return self.weapons()

    @traced("listfighter_wargear")
    def wargear(self):
        # Stash shows all non-weapon gear in one flat list. The stash card
        # doesn't render house_additional_gearline_display / category_restricted
        # sections like normal fighter cards do, so anything filtered out here
        # is invisible to the user despite being counted in cost_int.
        if self.is_stash:
            return [e for e in self.assignments_cached if not e.is_weapon_cached]

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
    @traced("listfighter_has_house_additional_gear")
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
        from gyrinx.content.models import (
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
    @traced("listfighter_house_additional_gearline_display")
    def house_additional_gearline_display(self):
        """
        Get display info for house-restricted and expansion equipment categories.
        Includes:
        1. restricted_equipment_categories on the house
        2. actual assigned gear categories
        3. available categories as a result of expansions

        Optimized to use list-level cached expansion equipment to avoid running
        expensive expansion queries once per fighter.
        """
        gearlines = []
        seen_categories = set()

        # === BATCH QUERIES UPFRONT ===

        # 1. Get expansion equipment from list-level cache (keyed by fighter category)
        # This avoids running expensive expansion queries once per fighter
        fighter_category = self.get_category()
        expansion_cache = self.list.expansion_equipment_by_category
        # Combine category-specific equipment with base equipment (no category filter)
        # Make a copy to avoid modifying the cached list
        expansion_equipment_list = pylist(expansion_cache.get(fighter_category, []))
        # Also include base expansion equipment (applies to all fighters regardless of category)
        base_expansion_equipment = expansion_cache.get(None, [])
        # Merge: category-specific takes precedence, add base equipment not already included
        seen_equipment_ids = {eq.id for eq in expansion_equipment_list}
        for eq in base_expansion_equipment:
            if eq.id not in seen_equipment_ids:
                expansion_equipment_list.append(eq)
                seen_equipment_ids.add(eq.id)
        expansion_category_ids = {eq.category_id for eq in expansion_equipment_list}

        # 2. Get all equipment list category IDs for this fighter (single query)
        equipment_list_category_ids = set(
            ContentFighterEquipmentListItem.objects.filter(
                fighter__in=self.equipment_list_fighters
            ).values_list("equipment__category_id", flat=True)
        )

        # === PROCESS CATEGORIES ===

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
                # Check equipment list items (using pre-fetched set)
                elif cat.id in equipment_list_category_ids:
                    has_equipment_in_category = True
                # Check expansion equipment (using pre-fetched set)
                elif cat.id in expansion_category_ids:
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

        # 3. Categories from expansions (using pre-fetched list)
        for equipment in expansion_equipment_list:
            cat = equipment.category
            # Use prefetched restricted_to - check if it has any items
            has_restrictions = (
                hasattr(cat, "_prefetched_objects_cache")
                and "restricted_to" in cat._prefetched_objects_cache
                and len(cat._prefetched_objects_cache["restricted_to"]) > 0
            ) or (
                not hasattr(cat, "_prefetched_objects_cache")
                and cat.restricted_to.exists()
            )

            if cat.id not in seen_categories and has_restrictions:
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
    def applicable_counters(self):
        """Return applicable ContentCounter objects for this fighter.

        Uses prefetched content_fighter__counters when available.
        Returns a list of (ContentCounter, value) tuples.
        """
        content_fighter = self.content_fighter_cached
        if not content_fighter:
            return []

        # Use prefetched reverse M2M from ContentCounter.restricted_to_fighters
        applicable = list(content_fighter.counters.all())
        if not applicable:
            return []

        # Build a map of existing counter values from prefetched data
        existing = {c.counter_id: c.value for c in self.counters.all()}

        return [
            (counter, existing.get(counter.id, 0))
            for counter in sorted(applicable, key=lambda c: (c.display_order, c.name))
        ]

    @cached_property
    @traced("listfighter_has_category_restricted_gear")
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
    @traced("listfighter_category_restricted_gearline_display")
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

    @traced("listfighter_category_restricted_assignments")
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

    @traced("listfighter_powers")
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

    @traced("listfighter_psyker_default_powers")
    def psyker_default_powers(self):
        # Pack-aware: a pack-authored ContentFighterPsykerPowerDefaultAssignment
        # would be hidden by the default ContentManager via the reverse FK,
        # so we go through the model with `with_packs(...)` instead.
        from gyrinx.content.models.psyker import (
            ContentFighterPsykerPowerDefaultAssignment,
        )
        from gyrinx.core.models.list.virtual import (
            VirtualListFighterPsykerPowerAssignment,
        )

        # Read disabled IDs through the M2M through-table — `.all()` would
        # go through the target's ContentManager and silently exclude
        # pack-authored disabled rows.
        disabled_pks = self.disabled_pskyer_default_powers.through.objects.filter(
            listfighter=self
        ).values("contentfighterpsykerpowerdefaultassignment_id")
        default_powers = (
            ContentFighterPsykerPowerDefaultAssignment.objects.with_packs(
                self.list.packs.all(), include_archived_items=True
            )
            .filter(fighter=self.content_fighter_cached)
            .exclude(pk__in=disabled_pks)
            .select_related("psyker_power", "psyker_power__discipline")
        )
        return [
            VirtualListFighterPsykerPowerAssignment.from_default_assignment(p, self)
            for p in default_powers
        ]

    @cached_property
    def psyker_default_powers_cached(self):
        return self.psyker_default_powers()

    @traced("listfighter_psyker_assigned_powers")
    def psyker_assigned_powers(self):
        from gyrinx.core.models.list.virtual import (
            VirtualListFighterPsykerPowerAssignment,
        )

        return [
            VirtualListFighterPsykerPowerAssignment.from_assignment(p)
            for p in self.psyker_powers.all()
        ]

    @cached_property
    def psyker_assigned_powers_cached(self):
        return self.psyker_assigned_powers()

    @property
    @traced("listfighter_is_psyker")
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
    @traced("listfighter_should_have_zero_cost")
    def should_have_zero_cost(self):
        """Check if this fighter should contribute 0 to gang total cost."""
        return self.is_captured or self.is_sold_to_guilders or self.is_dead

    @property
    @traced("listfighter_active_advancement_count")
    def active_advancement_count(self):
        """Return count of non-archived advancements.

        Uses the prefetched ``advancements`` set when available (the fighter
        prefetch suite includes it) so rendering a fighter card doesn't issue
        a COUNT query per fighter. ``.filter()`` would bypass the prefetch
        cache and hit the database, so count in Python instead.
        """
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "advancements" in self._prefetched_objects_cache
        ):
            return sum(
                1
                for adv in self._prefetched_objects_cache["advancements"]
                if not adv.archived
            )
        return self.advancements.filter(archived=False).count()

    def has_overridden_cost(self):
        return self.cost_override is not None or self.should_have_zero_cost

    @traced("listfighter_toggle_default_assignment")
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

    @traced("listfighter_convert_default_assignment")
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

    @traced("list_fighter_copy_attributes_to")
    def copy_attributes_to(self, target_fighter, include_equipment=True):
        """Copy attributes from this fighter to another fighter.

        Args:
            target_fighter: The fighter to copy attributes to
            include_equipment: Whether to copy equipment assignments (default True)
        """
        from gyrinx.core.models.list.advancement import ListFighterAdvancement
        from gyrinx.core.models.list.campaign_state import ListFighterStatOverride
        from gyrinx.core.models.list.psyker import ListFighterPsykerPowerAssignment

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

        # Copy narrative and notes
        target_fighter.narrative = self.narrative
        target_fighter.notes = self.notes
        target_fighter.private_notes = self.private_notes

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
            # Copy equipment assignments, including those converted from default assignments
            for assignment in self._direct_assignments():
                # Clone the assignment, preserving from_default_assignment if present
                # This ensures upgrades and other customizations are preserved
                cloned_assignment = assignment.clone(
                    list_fighter=target_fighter,
                    preserve_from_default_assignment=True,
                )

                # If this assignment was converted from a default, disable the default
                # on the target fighter to match the original state
                if assignment.from_default_assignment is not None:
                    target_fighter.disabled_default_assignments.add(
                        assignment.from_default_assignment
                    )

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

        # Mark target fighter dirty so facts get recalculated.
        # Set instance attr for in-memory consistency, update() persists to DB without signals.
        target_fighter.dirty = True
        ListFighter.objects.filter(pk=target_fighter.pk).update(dirty=True)

    @traced("list_fighter_clone")
    def clone(self, **kwargs):
        """Clone the fighter, creating a new fighter with the same equipment."""
        from gyrinx.core.models.list.campaign_state import ListFighterStatOverride
        from gyrinx.core.models.list.psyker import ListFighterPsykerPowerAssignment

        values = {
            "name": self.name,
            "content_fighter": self.content_fighter,
            "legacy_content_fighter": self.legacy_content_fighter,
            "narrative": self.narrative,
            "notes": self.notes,
            "private_notes": self.private_notes,
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

        # Clone equipment assignments, including those converted from default assignments
        # to preserve upgrades and other customizations
        for assignment in self._direct_assignments():
            if assignment.linked_equipment_parent is not None:
                # Skip assignments that were auto-created from equipment-equipment links
                # The clone will get these via the signal when the parent equipment is cloned
                continue

            # Clone the assignment, preserving from_default_assignment if present
            cloned_assignment = assignment.clone(
                list_fighter=clone,
                preserve_from_default_assignment=True,
            )

            # If this assignment was converted from a default, disable the default
            # on the clone to match the original state
            if assignment.from_default_assignment is not None:
                clone.disabled_default_assignments.add(
                    assignment.from_default_assignment
                )

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

        # Recalculate cached values if propagation system is not active
        # When propagation IS active (latest_action exists), the handler will call
        # propagate_from_fighter() which updates rating_current
        if not (
            clone.list.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL
        ):
            clone.facts_from_db(update=True)

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
        """Check if the fighter has any content in the info fields (save roll, private notes)."""
        return bool(self.save_roll or self.private_notes)

    def has_lore_content(self):
        """Check if the fighter has any content in the Lore tab."""
        return bool(self.narrative or self.image)

    def has_notes_content(self):
        """Check if the fighter has any content in the Notes tab."""
        return bool(self.notes or self.save_roll or self.private_notes)

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

    @traced("listfighter_clean_fields")
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


def _materialise_child_fighter_defaults(list_fighter) -> int:
    """Materialise a list-fighter's child-spawning default assignments.

    For each default assignment on the fighter's ``content_fighter`` whose
    equipment spawns a child fighter (``ContentEquipmentFighterProfile``) or
    child equipment (``ContentEquipmentEquipmentProfile``), disable the default
    and create a direct assignment with ``cost_override=0``. The direct
    assignment's ``post_save`` (``create_related_objects``) then spawns the
    child fighter / linked equipment.

    Idempotent: skips defaults that are disabled or already materialised, so it
    is safe to call repeatedly (used both at hire time and by the #1725
    propagation task).

    Returns the number of direct assignments created.
    """
    from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment

    # Find the default assignments where the equipment has a fighter profile
    default_assigns = list_fighter.content_fighter.default_assignments.exclude(
        Q(equipment__contentequipmentfighterprofile__isnull=True)
        & Q(equipment__contentequipmentequipmentprofile__isnull=True)
    )
    created = 0
    for assign in default_assigns:
        # Find disabled default assignments
        is_disabled = list_fighter.disabled_default_assignments.contains(assign)

        # Find assignments on this fighter of that equipment
        exists = (
            list_fighter._direct_assignments()
            .filter(content_equipment=assign.equipment, from_default_assignment=assign)
            .exists()
        )

        if not is_disabled and not exists:
            # Disable the default assignment and assign the equipment directly
            # This will trigger the ListFighterEquipmentAssignment logic to
            # create the linked objects
            list_fighter.toggle_default_assignment(assign, enable=False)
            ListFighterEquipmentAssignment.objects.create_with_facts(
                list_fighter=list_fighter,
                content_equipment=assign.equipment,
                cost_override=0,
                from_default_assignment=assign,
            )
            created += 1
    return created
