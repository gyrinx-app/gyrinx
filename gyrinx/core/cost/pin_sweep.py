"""Amount-rewriting sweeps for pinned component rows (#1826 Phase 6, §4.7).

When a price-bearing content source changes, rows pinned to it must have
their cached amounts rewritten to the corrected price — this is how a
content correction propagates to pinned gear (prices stay at acquisition
value EXCEPT when the acquisition-time source itself is corrected). The
caller (`_create_content_cost_change_actions`) runs the rewrite BEFORE any
recompute or dirty processing, so `facts_from_db` sums already-updated
amounts; rewriting after would either snap the caches back or double-count.

The sweep domains are partitioned by pin_state (§4.1):

- SOURCE rows are found by pin-FK equality — holder-independent, so gear
  that has moved away from the context that priced it is still reached.
- CATALOG rows are found by the component's own content FK (those lookups
  were holder-independent already).
- DERIVED rows are re-derived, never amount-copied: expression accessories
  re-evaluate against the assignment's (possibly just-rewritten) base cost;
  SINGLE-stack upgrade rows re-sum their cumulative rungs.
- ORPHANED rows are excluded from every rewrite — frozen by definition.
- UNPINNED rows have no amount to rewrite; their presence on a list flips
  that list's audit delta back to the snapshot fallback (`has_unpinned`),
  because their live repricing can't be expressed as per-row amount deltas.

Deltas are per-row: Σ(new − old amount), split rating/stash by the holding
fighter. Archived rows are rewritten too — a later unarchive must not
resurrect a stale amount — but contribute no delta, matching cache
semantics (facts exclude archived rows).
"""

from dataclasses import dataclass, field

from django.db.models import Q

from gyrinx.content.signals import get_new_cost
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    ListFighterEquipmentAssignmentAccessory,
    ListFighterEquipmentAssignmentProfile,
    ListFighterEquipmentAssignmentUpgrade,
    PinState,
    bulk_mark_assignments_dirty,
)


@dataclass
class PinSweep:
    """Outcome of an amount-rewriting sweep for one (source, list) pair."""

    pin_capable: bool = False  # the source model participates in pin sweeps
    has_unpinned: bool = False  # live UNPINNED rows affected → snapshot fallback
    rewrote: int = 0  # rows whose amount was rewritten
    rating_delta: int = 0
    stash_delta: int = 0
    # Assignments whose amounts changed, for the post-rewrite dirty-marking.
    touched_assignments: set = field(default_factory=set)

    @property
    def use_row_deltas(self) -> bool:
        """Whether the audit delta can be the exact per-row amount sum."""
        return self.pin_capable and not self.has_unpinned

    @property
    def total_delta(self) -> int:
        return self.rating_delta + self.stash_delta


def rewrite_pinned_amounts_for_list(instance, lst) -> PinSweep:
    """Rewrite pinned amounts on ``lst`` affected by a change to ``instance``.

    Returns a PinSweep carrying the per-row deltas and whether the caller
    can use them as the audit delta (`use_row_deltas`) or must fall back to
    the snapshot-vs-recompute computation (UNPINNED rows present, or a
    source model pins don't apply to).
    """
    handler = _SWEEP_HANDLERS.get(type(instance).__name__)
    if handler is None:
        return PinSweep()
    sweep = handler(instance, lst)
    if sweep.touched_assignments:
        # Sweeps do two jobs: rewrite amounts, THEN mark dirty (§4.7). The
        # enqueue-time set_dirty is not enough — an action landing in the
        # enqueue-to-task window (a purchase, say) refreshes the fighter's
        # caches from the OLD amounts and clears the dirty flags, so the
        # recompute that follows this rewrite would lazily skip the fighter
        # and leave its cache stale against the rewritten amounts.
        bulk_mark_assignments_dirty(
            ListFighterEquipmentAssignment.objects.filter(
                pk__in=sweep.touched_assignments,
                archived=False,
                list_fighter__archived=False,
            )
        )
    return sweep


# --- Row-set helpers ---------------------------------------------------------


def _base_rows(lst):
    return ListFighterEquipmentAssignment.objects.filter(list_fighter__list=lst)


def _profile_rows(lst):
    return ListFighterEquipmentAssignmentProfile.objects.filter(
        listfighterequipmentassignment__list_fighter__list=lst
    )


def _accessory_rows(lst):
    return ListFighterEquipmentAssignmentAccessory.objects.filter(
        listfighterequipmentassignment__list_fighter__list=lst
    )


def _upgrade_rows(lst):
    return ListFighterEquipmentAssignmentUpgrade.objects.filter(
        listfighterequipmentassignment__list_fighter__list=lst
    )


def _live_through(qs):
    """Through rows whose assignment and fighter are unarchived (cache-visible)."""
    return qs.filter(
        listfighterequipmentassignment__archived=False,
        listfighterequipmentassignment__list_fighter__archived=False,
    )


def _holder_context_q(fighter, prefix=""):
    """The legacy holder-keyed sweep condition, for the unpinned checks."""
    return Q(**{f"{prefix}list_fighter__content_fighter": fighter}) | Q(
        **{f"{prefix}list_fighter__legacy_content_fighter": fighter}
    )


def _bucket(sweep, assignment, delta):
    """Accumulate a row delta into rating or stash; archived rows move nothing."""
    fighter = assignment.list_fighter
    if assignment.archived or fighter.archived:
        return
    if fighter.content_fighter.is_stash:
        sweep.stash_delta += delta
    else:
        sweep.rating_delta += delta


def _flush(model, updates, field):
    by_value = {}
    for pk, new in updates:
        by_value.setdefault(new, []).append(pk)
    for value, pks in by_value.items():
        model.objects.filter(pk__in=pks).update(**{field: value})


def _rewrite_base_rows(qs, new_amount_for, sweep):
    """Rewrite pinned_base_amount; returns ids of assignments that changed."""
    changed = []
    updates = []
    for assignment in qs.select_related("list_fighter__content_fighter"):
        new = new_amount_for(assignment)
        if new is None or new == assignment.pinned_base_amount:
            continue
        _bucket(sweep, assignment, new - assignment.pinned_base_amount)
        updates.append((assignment.pk, new))
        changed.append(assignment.pk)
        sweep.touched_assignments.add(assignment.pk)
    _flush(ListFighterEquipmentAssignment, updates, "pinned_base_amount")
    sweep.rewrote += len(updates)
    return changed


def _rewrite_through_rows(model, qs, new_amount_for, sweep):
    updates = []
    for row in qs.select_related(
        "listfighterequipmentassignment__list_fighter__content_fighter"
    ):
        new = new_amount_for(row)
        if new is None or new == row.pinned_amount:
            continue
        _bucket(sweep, row.listfighterequipmentassignment, new - row.pinned_amount)
        updates.append((row.pk, new))
        sweep.touched_assignments.add(row.listfighterequipmentassignment_id)
    _flush(model, updates, "pinned_amount")
    sweep.rewrote += len(updates)


def _rederive_accessory_rows(qs, sweep, require_expression):
    """Re-derive DERIVED accessory amounts against their assignment's base.

    ``require_expression`` distinguishes the base-rewrite cascade (only
    expression accessories depend on the base) from a direct accessory
    change (every DERIVED row for it re-derives — the evaluator falls back
    to the flat cost when there is no expression).
    """
    qs = qs.filter(pin_state=PinState.DERIVED)
    if require_expression:
        qs = qs.exclude(contentweaponaccessory__cost_expression="").exclude(
            contentweaponaccessory__cost_expression__isnull=True
        )
    base_cache = {}
    updates = []
    for row in qs.select_related(
        "contentweaponaccessory",
        "listfighterequipmentassignment__list_fighter__content_fighter",
    ):
        assignment = row.listfighterequipmentassignment
        base = base_cache.get(assignment.pk)
        if base is None:
            # Fresh fetch: the base amount may have been rewritten earlier in
            # this same sweep, and base_cost_int() caches aggressively.
            base = ListFighterEquipmentAssignment.objects.get(
                pk=assignment.pk
            ).base_cost_int()
            base_cache[assignment.pk] = base
        new = row.contentweaponaccessory.calculate_cost_for_weapon(base)
        if new == row.pinned_amount:
            continue
        _bucket(sweep, assignment, new - row.pinned_amount)
        updates.append((row.pk, new))
        sweep.touched_assignments.add(assignment.pk)
    _flush(ListFighterEquipmentAssignmentAccessory, updates, "pinned_amount")
    sweep.rewrote += len(updates)


def _cascade_expression_accessories(lst, changed_assignment_ids, sweep):
    """Base corrections cascade to same-assignment expression accessories."""
    if not changed_assignment_ids:
        return
    _rederive_accessory_rows(
        _accessory_rows(lst).filter(
            listfighterequipmentassignment_id__in=changed_assignment_ids
        ),
        sweep,
        require_expression=True,
    )


# --- Per-source sweeps: catalog models ---------------------------------------


def _sweep_equipment(instance, lst):
    sweep = PinSweep(pin_capable=True)
    new = get_new_cost(instance, "cost")
    changed = _rewrite_base_rows(
        _base_rows(lst).filter(
            content_equipment=instance, pinned_base_state=PinState.CATALOG
        ),
        lambda a: new,
        sweep,
    )
    _cascade_expression_accessories(lst, changed, sweep)
    sweep.has_unpinned = (
        _base_rows(lst)
        .filter(
            content_equipment=instance,
            pinned_base_state=PinState.UNPINNED,
            archived=False,
            list_fighter__archived=False,
        )
        .exists()
    )
    return sweep


def _sweep_weapon_profile(instance, lst):
    sweep = PinSweep(pin_capable=True)
    new = get_new_cost(instance, "cost")
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentProfile,
        _profile_rows(lst).filter(
            contentweaponprofile=instance, pin_state=PinState.CATALOG
        ),
        lambda r: new,
        sweep,
    )
    sweep.has_unpinned = _live_through(
        _profile_rows(lst).filter(
            contentweaponprofile=instance, pin_state=PinState.UNPINNED
        )
    ).exists()
    return sweep


def _sweep_weapon_accessory(instance, lst):
    sweep = PinSweep(pin_capable=True)
    new = get_new_cost(instance, "cost")
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentAccessory,
        _accessory_rows(lst).filter(
            contentweaponaccessory=instance, pin_state=PinState.CATALOG
        ),
        lambda r: new,
        sweep,
    )
    # Expression (or flat) re-derivation for DERIVED rows of this accessory —
    # covers both a cost edit and a cost_expression edit.
    _rederive_accessory_rows(
        _accessory_rows(lst).filter(contentweaponaccessory=instance),
        sweep,
        require_expression=False,
    )
    sweep.has_unpinned = _live_through(
        _accessory_rows(lst).filter(
            contentweaponaccessory=instance, pin_state=PinState.UNPINNED
        )
    ).exists()
    return sweep


def _sweep_upgrade(instance, lst):
    from gyrinx.content.models import ContentEquipment

    sweep = PinSweep(pin_capable=True)
    if instance.equipment.upgrade_mode == ContentEquipment.UpgradeMode.MULTI:
        new = get_new_cost(instance, "cost")
        _rewrite_through_rows(
            ListFighterEquipmentAssignmentUpgrade,
            _upgrade_rows(lst).filter(
                contentequipmentupgrade=instance, pin_state=PinState.CATALOG
            ),
            lambda r: new,
            sweep,
        )
        affected_upgrade_ids = [instance.pk]
    else:
        # SINGLE stacks price cumulatively: correcting one rung reprices
        # every row holding that rung or a higher one. Those rows are
        # DERIVED (their amount is a sum, not a copy) and re-derive via
        # cost_int(), which reads the committed new rung cost.
        cumulative = {u.pk: u.cost_int() for u in instance.same_stack_from_position()}
        _rewrite_through_rows(
            ListFighterEquipmentAssignmentUpgrade,
            _upgrade_rows(lst).filter(
                contentequipmentupgrade__in=list(cumulative),
                pin_state=PinState.DERIVED,
            ),
            lambda r: cumulative[r.contentequipmentupgrade_id],
            sweep,
        )
        affected_upgrade_ids = list(cumulative)
    sweep.has_unpinned = _live_through(
        _upgrade_rows(lst).filter(
            contentequipmentupgrade__in=affected_upgrade_ids,
            pin_state=PinState.UNPINNED,
        )
    ).exists()
    return sweep


# --- Per-source sweeps: override sources (pin-FK equality) --------------------


def _sweep_equipment_list_item(instance, lst):
    sweep = PinSweep(pin_capable=True)
    new = instance.cost
    changed = _rewrite_base_rows(
        _base_rows(lst).filter(
            pinned_equipment_list_item=instance, pinned_base_state=PinState.SOURCE
        ),
        lambda a: new,
        sweep,
    )
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentProfile,
        _profile_rows(lst).filter(
            pinned_equipment_list_item=instance, pin_state=PinState.SOURCE
        ),
        lambda r: new,
        sweep,
    )
    _cascade_expression_accessories(lst, changed, sweep)

    # Live-repricing UNPINNED rows: current-context assignments this row
    # still prices, split by whether it prices the base or a profile.
    context = _base_rows(lst).filter(
        _holder_context_q(instance.fighter),
        content_equipment=instance.equipment,
        archived=False,
        list_fighter__archived=False,
    )
    if instance.weapon_profile_id:
        sweep.has_unpinned = (
            _profile_rows(lst)
            .filter(
                listfighterequipmentassignment__in=context,
                contentweaponprofile=instance.weapon_profile,
                pin_state=PinState.UNPINNED,
            )
            .exists()
        )
    else:
        sweep.has_unpinned = context.filter(
            pinned_base_state=PinState.UNPINNED
        ).exists()
    return sweep


def _sweep_equipment_list_accessory(instance, lst):
    sweep = PinSweep(pin_capable=True)
    new = instance.cost
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentAccessory,
        _accessory_rows(lst).filter(
            pinned_equipment_list_accessory=instance, pin_state=PinState.SOURCE
        ),
        lambda r: new,
        sweep,
    )
    sweep.has_unpinned = (
        _live_through(
            _accessory_rows(lst).filter(
                _holder_context_q(
                    instance.fighter, prefix="listfighterequipmentassignment__"
                ),
                contentweaponaccessory=instance.weapon_accessory,
                pin_state=PinState.UNPINNED,
            )
        )
    ).exists()
    return sweep


def _sweep_equipment_list_upgrade(instance, lst):
    sweep = PinSweep(pin_capable=True)
    # Provisional flat semantics: what Phase 7 pins for a SINGLE-stack rung
    # priced through this override defines the cumulative story; until a
    # producer writes such pins, SOURCE rows copy the override cost.
    new = instance.cost
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentUpgrade,
        _upgrade_rows(lst).filter(
            pinned_equipment_list_upgrade=instance, pin_state=PinState.SOURCE
        ),
        lambda r: new,
        sweep,
    )
    sweep.has_unpinned = (
        _live_through(
            _upgrade_rows(lst).filter(
                _holder_context_q(
                    instance.fighter, prefix="listfighterequipmentassignment__"
                ),
                contentequipmentupgrade=instance.upgrade,
                pin_state=PinState.UNPINNED,
            )
        )
    ).exists()
    return sweep


def _sweep_expansion_item(instance, lst):
    sweep = PinSweep(pin_capable=True)
    # Expansion semantics: a null cost means "use the base cost" — of the
    # equipment for base pins, of the profile for profile pins.
    if instance.cost is not None:
        base_new = profile_new = instance.cost
    else:
        base_new = get_new_cost(instance.equipment, "cost")
        profile_new = (
            get_new_cost(instance.weapon_profile, "cost")
            if instance.weapon_profile_id
            else base_new
        )
    changed = _rewrite_base_rows(
        _base_rows(lst).filter(
            pinned_expansion_item=instance, pinned_base_state=PinState.SOURCE
        ),
        lambda a: base_new,
        sweep,
    )
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentProfile,
        _profile_rows(lst).filter(
            pinned_expansion_item=instance, pin_state=PinState.SOURCE
        ),
        lambda r: profile_new,
        sweep,
    )
    _cascade_expression_accessories(lst, changed, sweep)

    context = _base_rows(lst).filter(
        content_equipment=instance.equipment,
        archived=False,
        list_fighter__archived=False,
    )
    if instance.weapon_profile_id:
        sweep.has_unpinned = (
            _profile_rows(lst)
            .filter(
                listfighterequipmentassignment__in=context,
                contentweaponprofile=instance.weapon_profile,
                pin_state=PinState.UNPINNED,
            )
            .exists()
        )
    else:
        sweep.has_unpinned = context.filter(
            pinned_base_state=PinState.UNPINNED
        ).exists()
    return sweep


_SWEEP_HANDLERS = {
    "ContentEquipment": _sweep_equipment,
    "ContentWeaponProfile": _sweep_weapon_profile,
    "ContentWeaponAccessory": _sweep_weapon_accessory,
    "ContentEquipmentUpgrade": _sweep_upgrade,
    "ContentFighterEquipmentListItem": _sweep_equipment_list_item,
    "ContentFighterEquipmentListWeaponAccessory": _sweep_equipment_list_accessory,
    "ContentFighterEquipmentListUpgrade": _sweep_equipment_list_upgrade,
    "ContentEquipmentListExpansionItem": _sweep_expansion_item,
}
