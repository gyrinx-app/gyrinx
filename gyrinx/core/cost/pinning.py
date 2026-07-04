"""The resolve-and-pin choke point (#1826 Phase 7, §4.6).

Every acquisition path calls `pin_assignment()` after the assignment and its
component rows exist. It runs the same lookups live resolution uses — in the
same precedence order — and writes the acquisition receipt on each row:
the amount paid, the price-setting source it came from (as an FK, when there
is one), and the pin state that classifies it:

- expansion item priced it        → SOURCE, FK to the expansion item
- equipment-list row priced it    → SOURCE, FK to that row
- catalog priced it               → CATALOG, no FK (the row's own content FK
                                    is the attribution)
- the amount is computed, not
  looked up (formula accessories,
  cumulative SINGLE-stack rungs)  → DERIVED, evaluated amount, no FK

Rows the §4.2 anchors outrank are deliberately left UNPINNED: a user base
override, linked-child gear (structurally free), and default-kit components
(free by membership). A pin on those could never be read, and the CI guard's
allowlist names their creation paths as zero-anchored.

Idempotent by design: only UNPINNED rows are written, an existing receipt is
never overwritten — re-pinning would replace the acquisition price with
today's. That makes the choke point safe to call from any layer (view AND
handler double-calling is a no-op), and for un-anchored rows makes each call
on a legacy assignment a value-neutral early instalment of the Phase 8
backfill: their live resolution already returns the price being pinned.

Assignments with a fixed total (total_cost_override) are skipped entirely:
the frozen value is what the gang actually paid, so a receipt written at
today's live prices would record a price that was never paid — and, since
receipts are never overwritten, it would also block the Phase 8 conversion
from writing the frozen value into those rows when Phase 9 retires the
freeze.

Writes use queryset .update() (no signals, no history churn), matching the
sweep's write semantics (core/cost/pin_sweep.py).
"""

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentListExpansion,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ExpansionRuleInputs,
)
from gyrinx.content.signals import get_new_cost
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    PinState,
)


def pin_assignment(assignment) -> int:
    """Write acquisition receipts on an assignment and its component rows.

    Accepts any instance (possibly stale or carrying cached cost properties);
    works on a fresh refetch so live resolution sees true pre-pin state.
    Returns the number of rows pinned (0 when everything was already pinned
    or anchored) — callers don't need it, but tests do.
    """
    fresh = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=assignment.pk
    )
    if fresh.total_cost_override is not None:
        # Frozen gear: the override is the paid price. Leave every row
        # unpinned for the Phase 8 freeze-conversion to receipt correctly.
        return 0
    pinned = 0

    # --- Base -----------------------------------------------------------
    # base_for_expression must match what resolution's expression branch
    # reads (base_cost_int): the pinned amount when we write one, the
    # override/anchor value when we skip.
    base_for_expression = fresh.base_cost_int()
    if (
        fresh.pinned_base_amount is None
        and fresh.cost_override is None
        and fresh.linked_equipment_parent_id is None
    ):
        expansion_item = _expansion_item(fresh, weapon_profile=None)
        if expansion_item is not None:
            amount = expansion_item.cost
            fields = {
                "pinned_base_amount": amount,
                "pinned_base_state": PinState.SOURCE,
                "pinned_expansion_item": expansion_item,
            }
        else:
            list_item = _equipment_list_item(fresh, weapon_profile=None)
            if list_item is not None:
                amount = list_item.cost_int()
                fields = {
                    "pinned_base_amount": amount,
                    "pinned_base_state": PinState.SOURCE,
                    "pinned_equipment_list_item": list_item,
                }
            else:
                amount = get_new_cost(fresh.content_equipment, "cost")
                fields = {
                    "pinned_base_amount": amount,
                    "pinned_base_state": PinState.CATALOG,
                }
        ListFighterEquipmentAssignment.objects.filter(pk=fresh.pk).update(**fields)
        base_for_expression = amount
        pinned += 1

    default = fresh.from_default_assignment

    # --- Profiles ---------------------------------------------------------
    for row in fresh.profile_rows.all():
        if row.pinned_amount is not None:
            continue
        profile = row.contentweaponprofile
        if default and default.weapon_profiles_field.contains(profile):
            continue  # default-kit profile: structurally free, stays unpinned
        expansion_item = _expansion_item(fresh, weapon_profile=profile)
        if expansion_item is not None:
            fields = {
                "pinned_amount": expansion_item.cost,
                "pin_state": PinState.SOURCE,
                "pinned_expansion_item": expansion_item,
            }
        else:
            list_item = _equipment_list_item(fresh, weapon_profile=profile)
            if list_item is not None:
                fields = {
                    "pinned_amount": list_item.cost_int(),
                    "pin_state": PinState.SOURCE,
                    "pinned_equipment_list_item": list_item,
                }
            else:
                fields = {
                    "pinned_amount": get_new_cost(profile, "cost"),
                    "pin_state": PinState.CATALOG,
                }
        type(row).objects.filter(pk=row.pk).update(**fields)
        pinned += 1

    # --- Accessories --------------------------------------------------------
    for row in fresh.accessory_rows.all():
        if row.pinned_amount is not None:
            continue
        accessory = row.contentweaponaccessory
        if default and default.weapon_accessories_field.contains(accessory):
            continue  # default-kit accessory: free by membership
        if accessory.cost_expression:
            fields = {
                "pinned_amount": accessory.calculate_cost_for_weapon(
                    base_for_expression
                ),
                "pin_state": PinState.DERIVED,
            }
        else:
            override = _preferred_override(
                ContentFighterEquipmentListWeaponAccessory.objects.filter(
                    fighter__in=fresh.list_fighter.equipment_list_fighters,
                    weapon_accessory=accessory,
                ),
                fresh.list_fighter,
            )
            if override is not None:
                fields = {
                    "pinned_amount": override.cost_int(),
                    "pin_state": PinState.SOURCE,
                    "pinned_equipment_list_accessory": override,
                }
            else:
                fields = {
                    "pinned_amount": get_new_cost(accessory, "cost"),
                    "pin_state": PinState.CATALOG,
                }
        type(row).objects.filter(pk=row.pk).update(**fields)
        pinned += 1

    # --- Upgrades -------------------------------------------------------
    for row in fresh.upgrade_rows.all():
        if row.pinned_amount is not None:
            continue
        upgrade = row.contentequipmentupgrade
        if upgrade.equipment.upgrade_mode == ContentEquipment.UpgradeMode.SINGLE:
            # Cumulative stacks pin the whole override-inclusive rung walk
            # at acquisition; the amount is a sum, so the state is DERIVED
            # and sweeps re-derive it rather than copying any single source.
            fields = {
                "pinned_amount": fresh._upgrade_cost_with_override(upgrade),
                "pin_state": PinState.DERIVED,
            }
        else:
            override = _preferred_override(
                ContentFighterEquipmentListUpgrade.objects.filter(
                    fighter__in=fresh.list_fighter.equipment_list_fighters,
                    upgrade=upgrade,
                ),
                fresh.list_fighter,
            )
            if override is not None:
                fields = {
                    "pinned_amount": override.cost_int(),
                    "pin_state": PinState.SOURCE,
                    "pinned_equipment_list_upgrade": override,
                }
            else:
                fields = {
                    "pinned_amount": upgrade.cost,
                    "pin_state": PinState.CATALOG,
                }
        type(row).objects.filter(pk=row.pk).update(**fields)
        pinned += 1

    return pinned


# --- Provenance lookups (mirror resolution precedence exactly) ---------------


def _expansion_item(assignment, weapon_profile):
    """The applicable expansion item pricing this equipment/profile, if any.

    Mirrors _get_expansion_cost_override (assignment.py): first applicable
    item with a non-null cost wins — but returns the ITEM, which is the
    receipt's attribution FK.
    """
    items = ContentEquipmentListExpansion.get_applicable_expansion_items_for_equipment(
        ExpansionRuleInputs(
            list=assignment.list_fighter.list, fighter=assignment.list_fighter
        ),
        assignment.content_equipment,
        weapon_profile,
        cost__isnull=False,
    )
    return items[0] if items else None


def _equipment_list_item(assignment, weapon_profile):
    """The equipment-list row pricing this equipment/profile, if any."""
    return _preferred_override(
        ContentFighterEquipmentListItem.objects.filter(
            fighter__in=assignment.list_fighter.equipment_list_fighters,
            equipment=assignment.content_equipment,
            weapon_profile=weapon_profile,
        ),
        assignment.list_fighter,
    )


def _preferred_override(qs, list_fighter):
    """First override, preferring the legacy fighter's row when both exist —
    the same tie-break live resolution applies."""
    rows = list(qs)
    if len(rows) > 1 and list_fighter.legacy_content_fighter:
        for row in rows:
            if row.fighter_id == list_fighter.legacy_content_fighter_id:
                return row
    return rows[0] if rows else None
