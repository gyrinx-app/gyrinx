import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

from django.utils.functional import cached_property

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerPower,
    ContentWeaponProfile,
    VirtualWeaponProfile,
)
from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment
from gyrinx.core.models.list.fighter import ListFighter
from gyrinx.models import (
    QuerySetOf,
    format_cost_display,
)

if TYPE_CHECKING:
    from gyrinx.core.models.list.psyker import ListFighterPsykerPowerAssignment

logger = logging.getLogger(__name__)
pylist = list


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

    @property
    def facts(self):
        """
        Return facts for the underlying assignment.

        For real ListFighterEquipmentAssignment: delegates to _assignment.facts()
        For defaults and virtuals: returns None (no cached state to display)
        """
        if isinstance(self._assignment, ListFighterEquipmentAssignment):
            return self._assignment.facts()
        return None

    @property
    def dirty(self):
        """
        Return dirty state for the underlying assignment.

        For real ListFighterEquipmentAssignment: delegates to _assignment.dirty
        For defaults and virtuals: returns False (no cached state, always "clean")
        """
        if isinstance(self._assignment, ListFighterEquipmentAssignment):
            return self._assignment.dirty
        return False

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

    def _rebuild_profiles_with_pack_mods(self, virtual_profiles):
        """Rebuild a list of VirtualWeaponProfiles to include pack-scoped mods.

        Default-assignment profiles are constructed in ``content/`` without
        knowledge of the list, so they don't include the list's pack
        house-rule mods. When we wrap a ``ContentFighterDefaultAssignment``
        we rebuild the virtual profiles here so pack mods (both
        equipment-scoped and profile-scoped) get applied. For
        already-list-aware ``ListFighterEquipmentAssignment`` profiles, the
        pack mods are unioned in at construction time and we don't rebuild.
        """
        if not isinstance(self._assignment, ContentFighterDefaultAssignment):
            return virtual_profiles
        if self.fighter is None:
            return virtual_profiles
        list_obj = self.fighter.list
        if not list_obj.pack_mods_by_target:
            return virtual_profiles

        equipment_mods = list(list_obj.pack_mods_for(self.equipment))
        rebuilt = []
        for vp in virtual_profiles:
            extra = equipment_mods + list(list_obj.pack_mods_for(vp.profile))
            if not extra:
                rebuilt.append(vp)
                continue
            rebuilt.append(VirtualWeaponProfile(vp.profile, vp.mods + extra))
        return rebuilt

    def _wrap_profiles_with_pack_mods(self, profiles):
        """Wrap raw ``ContentWeaponProfile`` rows in ``VirtualWeaponProfile``
        with the list's pack mods applied.

        Used when this virtual assignment was built without a backing
        ``ListFighterEquipmentAssignment`` (Trading Post / weapons-edit
        flow). The list's pack-scoped house-rule mods for each profile
        still need to apply so the displayed stats and traits match what
        the user will actually get after assignment.
        """
        list_obj = self.fighter.list if self.fighter else None
        pack_aware = list_obj is not None and bool(list_obj.pack_mods_by_target)
        wrapped = []
        for p in profiles:
            mods = list(list_obj.pack_mods_for(p)) if pack_aware else []
            wrapped.append(VirtualWeaponProfile(p, mods))
        return wrapped

    def all_profiles(self):
        """
        Return all profiles for this equipment.
        """
        if not self._assignment:
            return self._wrap_profiles_with_pack_mods(self.profiles)

        cached = getattr(self._assignment, "all_profiles_cached", None)
        if cached:
            return self._rebuild_profiles_with_pack_mods(cached)

        return self._rebuild_profiles_with_pack_mods(self._assignment.all_profiles())

    @cached_property
    def all_profiles_cached(self):
        return self.all_profiles()

    def standard_profiles(self):
        """
        Return only the standard (cost=0) weapon profiles for this equipment.
        """
        if not self._assignment:
            return self._wrap_profiles_with_pack_mods(
                [profile for profile in self.profiles if profile.cost == 0]
            )

        if self._assignment.standard_profiles_cached:
            return self._rebuild_profiles_with_pack_mods(
                self._assignment.standard_profiles_cached
            )

        return self._rebuild_profiles_with_pack_mods(
            self._assignment.standard_profiles()
        )

    @cached_property
    def standard_profiles_cached(self):
        return self.standard_profiles()

    def weapon_profiles(self) -> list["VirtualWeaponProfile"]:
        """
        Return all weapon profiles for this equipment.
        """
        if not self._assignment:
            return self._wrap_profiles_with_pack_mods(
                [profile for profile in self.profiles if profile.cost_int() > 0]
            )

        if self._assignment.weapon_profiles_cached:
            return self._rebuild_profiles_with_pack_mods(
                self._assignment.weapon_profiles_cached
            )

        return self._rebuild_profiles_with_pack_mods(self._assignment.weapon_profiles())

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

        mods = list(self._assignment._mods)

        # Default assignments don't know about the list's packs (they live in
        # ``content/`` and have no list reference), so we add equipment-scoped
        # pack mods here. ListFighterEquipmentAssignment._mods already does
        # this work for direct assignments.
        if isinstance(self._assignment, ContentFighterDefaultAssignment):
            list_obj = self.fighter.list if self.fighter else None
            if list_obj is not None:
                mods += list(list_obj.pack_mods_for(self.equipment))

        return mods


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
            "ListFighterPsykerPowerAssignment",
            ContentFighterPsykerPowerDefaultAssignment,
        ]
        | None
    ) = None

    @classmethod
    def from_assignment(cls, assignment: "ListFighterPsykerPowerAssignment"):
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
