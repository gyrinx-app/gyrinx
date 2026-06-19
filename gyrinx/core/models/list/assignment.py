import logging
from typing import Optional

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import (
    Prefetch,
)
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    VirtualWeaponProfile,
)
from gyrinx.core.models.facts import AssignmentFacts
from gyrinx.core.models.history_mixin import HistoryMixin
from gyrinx.models import (
    Archived,
    Base,
    format_cost_display,
)
from gyrinx.core.models.list.fighter import ListFighter
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)
pylist = list


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
            "weapon_profiles_field",
            # Use all_content() so pack-scoped accessories are not hidden
            # by the default M2M manager.
            Prefetch(
                "weapon_accessories_field",
                queryset=ContentWeaponAccessory.objects.all_content(),
            ),
            "upgrades_field",
        )

    def create_with_facts(self, user=None, **kwargs):
        """
        Create a ListFighterEquipmentAssignment and calculate facts from database.

        Use this when the assignment is complete at creation (no m2m relationships
        like weapon_profiles_field need to be added). For assignments needing m2m
        setup first, use regular create() followed by manual facts_from_db().

        Args:
            user: Optional user for history tracking
            **kwargs: Fields for the new assignment

        Returns:
            The created assignment with correct cached values and dirty=False

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

    rating_current = models.IntegerField(
        default=0,
        help_text="Cached total rating of this assignment. Can be negative if equipment or upgrades have negative cost.",
    )

    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale",
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

    @traced("listfighterequipmentassignment_name")
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

    @traced("listfighterequipmentassignment_assign_profile")
    def assign_profile(self, profile: "ContentWeaponProfile"):
        """Assign a weapon profile to this equipment."""
        if profile.equipment != self.content_equipment_cached:
            raise ValueError(
                f"{profile} is not a profile for {self.content_equipment_cached}"
            )
        self.weapon_profiles_field.add(profile)

    @traced("listfighterequipmentassignment_profile_cost_int")
    def weapon_profiles(self):
        list_obj = self.list_fighter.list
        return [
            VirtualWeaponProfile(p, self._mods + list(list_obj.pack_mods_for(p)))
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

    @traced("listfighterequipmentassignment_all_profiles")
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

    @traced("listfighterequipmentassignment_standard_profiles")
    def standard_profiles(self):
        # TODO: There is nothing in the prefetch cache here
        list_obj = self.list_fighter.list
        return [
            VirtualWeaponProfile(p, self._mods + list(list_obj.pack_mods_for(p)))
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

    @traced("listfighterequipmentassignment_weapon_accessories")
    def weapon_accessories(self):
        return list(self.weapon_accessories_field.all())

    @cached_property
    def weapon_accessories_cached(self):
        return self.weapon_accessories()

    # Mods

    @cached_property
    @traced("listfighterequipmentassignment_mods")
    def _mods(self):
        """
        Get the mods for this assignment.

        Mods come from:
        - the equipment itself
        - accessories
        - upgrades
        - pack-scoped house-rule mods targeting this assignment's equipment
          (the equipment-level lookup; per-profile house-rule mods are unioned
          in at ``VirtualWeaponProfile`` construction time).
        """
        mods = [m for a in self.weapon_accessories_cached for m in a.modifiers.all()]
        mods += list(self.content_equipment_cached.modifiers.all())
        mods += [m for u in self.upgrades_field.all() for m in u.modifiers.all()]
        # Pack-scoped house rules targeting this equipment apply to every
        # profile of the weapon (and to fighter stats when they're equipped).
        mods += list(
            self.list_fighter.list.pack_mods_for(self.content_equipment_cached)
        )
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

    def facts(self) -> Optional[AssignmentFacts]:
        """
        Return cached facts about this assignment.

        Fast O(1) read from rating_current field.
        Returns None if dirty=True.
        """
        if self.dirty:
            return None

        return AssignmentFacts(rating=self.rating_current)

    def set_dirty(self, save: bool = True) -> None:
        """
        Mark this assignment as dirty and propagate to parent fighter.

        Args:
            save: If True, immediately saves the dirty flag to the database.
                  Uses QuerySet.update() to bypass signals and avoid thrashing.
        """
        if not self.dirty:
            self.dirty = True
            if save:
                ListFighterEquipmentAssignment.objects.filter(pk=self.pk).update(
                    dirty=True
                )

        # Propagate to parent fighter
        self.list_fighter.set_dirty(save=save)

    @traced("list_fighter_assignment_facts_from_db")
    def facts_from_db(self, update: bool = True) -> AssignmentFacts:
        """
        Recalculate facts from database using existing cost_int() method.

        Args:
            update: If True, updates rating_current and clears dirty flag.

        Returns:
            AssignmentFacts with recalculated rating.

        Uses existing heavily-tested cost_int() method for calculation.
        """
        # Use existing tested cost calculation
        rating = self.cost_int()

        # Optionally update cache
        if update:
            # Use QuerySet.update() to bypass signals - facts_from_db is already
            # computing correct values, we don't want to trigger expensive
            # signal_update_list_cache_for_assignment recalculations
            # Note: rating can be negative if equipment or upgrades have negative cost
            ListFighterEquipmentAssignment.objects.filter(pk=self.pk).update(
                rating_current=rating,
                dirty=False,
            )
            # Update instance to reflect DB changes
            self.rating_current = rating
            self.dirty = False

        return AssignmentFacts(rating=rating)

    def _get_expansion_cost_override(
        self, content_equipment, weapon_profile, expansion_inputs
    ):
        """Helper method to get expansion cost override for equipment or weapon profile."""
        from gyrinx.content.models import (
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

    @traced("listfighterequipmentassignment_equipment_cost_with_override")
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
        # Performance optimization: use cached lookup from list level if available
        list_obj = self.list_fighter.list
        fighter_category = self.list_fighter.get_category()

        # Try cached expansion cost lookup (O(1) instead of DB query)
        # Only use cache if expansion_equipment_by_category is already computed
        # to avoid triggering new queries in contexts that don't expect them
        if "expansion_equipment_by_category" in list_obj.__dict__:
            expansion_lookup = list_obj.expansion_cost_lookup_by_category
            category_costs = expansion_lookup.get(fighter_category, {})
            if not category_costs:
                # Fall back to generic expansion (no category)
                category_costs = expansion_lookup.get(None, {})

            if self.content_equipment_id in category_costs:
                return category_costs[self.content_equipment_id]

        # Fallback to DB query if equipment not in expansion cache
        from gyrinx.content.models import ExpansionRuleInputs

        expansion_inputs = ExpansionRuleInputs(list=list_obj, fighter=self.list_fighter)
        expansion_cost = self._get_expansion_cost_override(
            content_equipment=self.content_equipment,
            weapon_profile=None,  # Base equipment cost, not profile
            expansion_inputs=expansion_inputs,
        )

        # If expansion has cost override, use it
        if expansion_cost is not None:
            return expansion_cost

        # Otherwise check normal equipment list overrides
        # Performance optimization: use prefetched lookup if available
        lookup = self.list_fighter.equipment_list_items_lookup
        lookup_key = (self.content_equipment_id, None)  # None = base equipment cost

        # If we have a prefetched lookup (non-empty dict), use it
        if lookup is not None:
            if lookup_key in lookup:
                # Use prefetched item (already handles legacy preference)
                return lookup[lookup_key].cost_int()
            else:
                # Item not in equipment list, use base equipment cost
                return self.content_equipment.cost_int()

        # Fallback to DB query if lookup not available (empty dict means prefetched but no items)
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

    @traced("listfighterequipmentassignment_profile_cost_with_override")
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

    @traced("listfighterequipmentassignment_profile_cost_with_override_for_profile")
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
        from gyrinx.content.models import ExpansionRuleInputs

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

    @traced("listfighterequipmentassignment_accessories_cost_with_override")
    def _accessories_cost_with_override(self):
        accessories = self.weapon_accessories_cached
        if not accessories:
            return 0

        after_overrides = [self._accessory_cost_with_override(a) for a in accessories]
        return sum(after_overrides)

    @traced("listfighterequipmentassignment_accessory_cost_with_override")
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

    @traced("listfighterequipmentassignment_upgrade_cost_with_override")
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

    @traced("list_fighter_equipment_assignment_clone")
    def clone(self, list_fighter=None, preserve_from_default_assignment=False):
        """Clone the assignment, creating a new assignment with the same weapon profiles.

        Args:
            list_fighter: The ListFighter to associate the clone with.
            preserve_from_default_assignment: If True, preserve the from_default_assignment
                field on the clone. This is used when cloning fighters to preserve
                upgrades on assignments that were converted from default assignments.
        """
        if not list_fighter:
            list_fighter = self.list_fighter

        clone = ListFighterEquipmentAssignment.objects.create(
            list_fighter=list_fighter,
            content_equipment=self.content_equipment,
        )

        # Preserve from_default_assignment if requested
        if preserve_from_default_assignment and self.from_default_assignment:
            clone.from_default_assignment = self.from_default_assignment

        for profile in self.weapon_profiles_field.all():
            clone.weapon_profiles_field.add(profile)

        # Use all_content() so pack-scoped accessories are copied too — the
        # default M2M manager would silently drop them.
        for accessory in ContentWeaponAccessory.objects.all_content().filter(
            weapon_accessories=self
        ):
            clone.weapon_accessories_field.add(accessory)

        for upgrade in self.upgrades_field.all():
            clone.upgrades_field.add(upgrade)

        if self.cost_override is not None:
            clone.cost_override = self.cost_override

        if self.total_cost_override is not None:
            clone.total_cost_override = self.total_cost_override

        clone.save()

        # Always recalculate cached values after cloning
        # Cloning is not part of the action/propagation system - it needs explicit recalculation
        clone.facts_from_db(update=True)

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

        indexes = [
            models.Index(
                fields=["content_equipment"],
                name="idx_assignment_content_equip",
            ),
        ]
