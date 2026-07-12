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
    # A rewritten row sits behind a mask the per-row maths can't price
    # exactly (a from-default assignment frees SOME components, by
    # membership) → snapshot fallback, which prices precedence exactly.
    has_masked: bool = False
    rewrote: int = 0  # rows whose amount was rewritten
    rating_delta: int = 0
    stash_delta: int = 0
    # Assignments whose amounts changed, for the post-rewrite dirty-marking.
    touched_assignments: set = field(default_factory=set)

    @property
    def use_row_deltas(self) -> bool:
        """Whether the audit delta can be the exact per-row amount sum."""
        return self.pin_capable and not self.has_unpinned and not self.has_masked

    @property
    def total_delta(self) -> int:
        return self.rating_delta + self.stash_delta


def rewrite_pinned_amounts_for_list(instance, lst, old_cost=None) -> PinSweep:
    """Rewrite pinned amounts on ``lst`` affected by a change to ``instance``.

    ``old_cost`` is the source's pre-change value (captured by the pre_save
    handler and carried through the task payload). Amount-snapshot DERIVED
    rows — SINGLE-stack cumulative pins — can only be maintained by DELTA
    (new − old applied to the receipt): re-deriving them from current
    catalog values would silently destroy acquisition-time discounts on
    rungs that were never corrected. Without ``old_cost`` those rows are
    left untouched and the list is flagged has_masked (snapshot fallback).

    Returns a PinSweep carrying the per-row deltas and whether the caller
    can use them as the audit delta (`use_row_deltas`) or must fall back to
    the snapshot-vs-recompute computation (UNPINNED rows present, masked
    rows, or a source model pins don't apply to).
    """
    handler = _SWEEP_HANDLERS.get(type(instance).__name__)
    if handler is None:
        return PinSweep()
    if handler in _NEEDS_OLD_COST:
        sweep = handler(instance, lst, old_cost)
    else:
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
    """Accumulate a row delta into rating or stash; archived rows move nothing.

    A fixed assignment total masks every component: the resolved value cannot
    move, so a rewritten amount is provenance, not book movement — booking it
    would charge campaign credits for a price that never changed and fabricate
    an unchained baseline.
    """
    fighter = assignment.list_fighter
    if assignment.archived or fighter.archived:
        return
    if assignment.total_cost_override is not None:
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
        # cost_override and linked-child-zero outrank the base pin in
        # resolution: the base contribution is exactly unchanged, so the
        # amount is rewritten but no movement is booked.
        base_masked = (
            assignment.cost_override is not None
            or assignment.linked_equipment_parent_id is not None
        )
        if not base_masked:
            _bucket(sweep, assignment, new - assignment.pinned_base_amount)
        updates.append((assignment.pk, new))
        changed.append(assignment.pk)
        sweep.touched_assignments.add(assignment.pk)
    _flush(ListFighterEquipmentAssignment, updates, "pinned_base_amount")
    sweep.rewrote += len(updates)
    return changed


def _rewrite_through_rows(model, qs, new_amount_for, sweep, defaults_can_mask=False):
    updates = []
    for row in qs.select_related(
        "listfighterequipmentassignment__list_fighter__content_fighter"
    ):
        new = new_amount_for(row)
        if new is None or new == row.pinned_amount:
            continue
        assignment = row.listfighterequipmentassignment
        if assignment.archived or assignment.list_fighter.archived:
            # Rewrite only: archived rows move no caches and must not mask —
            # a sticky has_masked from an archived row would force the whole
            # list back onto the racy snapshot fallback for nothing.
            pass
        elif defaults_can_mask and assignment.from_default_assignment_id is not None:
            # A from-default assignment frees SOME profiles/accessories (by
            # membership in the default's component sets) — resolution-exact
            # pricing needs the recompute, so flag for the snapshot fallback.
            sweep.has_masked = True
        else:
            _bucket(sweep, assignment, new - row.pinned_amount)
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
        qs = _expression_rows(qs)
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
        if assignment.archived or assignment.list_fighter.archived:
            pass  # rewrite only: no delta, no mask (see _rewrite_through_rows)
        elif assignment.from_default_assignment_id is not None:
            sweep.has_masked = True  # membership-dependent free accessories
        else:
            _bucket(sweep, assignment, new - row.pinned_amount)
        updates.append((row.pk, new))
        sweep.touched_assignments.add(assignment.pk)
    _flush(ListFighterEquipmentAssignmentAccessory, updates, "pinned_amount")
    sweep.rewrote += len(updates)


def _expression_rows(qs):
    return qs.exclude(contentweaponaccessory__cost_expression="").exclude(
        contentweaponaccessory__cost_expression__isnull=True
    )


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
    # An UNPINNED expression accessory on a rewritten base reprices live off
    # the new base amount: its movement is in the recompute but not in the
    # per-row deltas, so it forces the snapshot fallback like any other
    # live-repricing UNPINNED row.
    if _expression_rows(
        _live_through(
            _accessory_rows(lst).filter(
                listfighterequipmentassignment_id__in=changed_assignment_ids,
                pin_state=PinState.UNPINNED,
            )
        )
    ).exists():
        sweep.has_unpinned = True


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
    # DERIVED expression rows re-derive whenever their base input changed —
    # whether the base was a rewritten pin or an UNPINNED base repricing
    # live off this source. Re-derivation reads the row's true
    # base_cost_int(), so a base that didn't actually move is a no-op.
    live_bases = _base_rows(lst).filter(
        content_equipment=instance, pinned_base_state=PinState.UNPINNED
    )
    _cascade_expression_accessories(
        lst, changed + list(live_bases.values_list("pk", flat=True)), sweep
    )
    sweep.has_unpinned = sweep.has_unpinned or (
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
        defaults_can_mask=True,
    )
    sweep.has_unpinned = (
        sweep.has_unpinned
        or _live_through(
            _profile_rows(lst).filter(
                contentweaponprofile=instance, pin_state=PinState.UNPINNED
            )
        ).exists()
    )
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
        defaults_can_mask=True,
    )
    # Expression (or flat) re-derivation for DERIVED rows of this accessory —
    # covers both a cost edit and a cost_expression edit.
    _rederive_accessory_rows(
        _accessory_rows(lst).filter(contentweaponaccessory=instance),
        sweep,
        require_expression=False,
    )
    sweep.has_unpinned = (
        sweep.has_unpinned
        or _live_through(
            _accessory_rows(lst).filter(
                contentweaponaccessory=instance, pin_state=PinState.UNPINNED
            )
        ).exists()
    )
    return sweep


def _single_stack_delta_rewrite(
    lst, sweep, stack_upgrade_ids, delta, masked_fighter_ids
):
    """Apply a rung correction to SINGLE-stack DERIVED receipts BY DELTA.

    Amount-snapshot receipts (Phase 7 pins the override-inclusive cumulative
    walk) can't be re-derived from catalog values without destroying
    acquisition discounts on uncorrected rungs — the correction moves the
    receipt by exactly what the corrected contribution moved, nothing else.
    ``masked_fighter_ids``: holders for whom the corrected contribution is
    masked (e.g. a per-rung override hides its catalog price) keep their
    receipt untouched. Moved rows are best-effort: the mask is evaluated
    against the CURRENT holder (the receipt doesn't record acquisition-time
    per-rung state — the documented v1 amount-snapshot imprecision; per-rung
    provenance is the escalation if it bites).
    """
    if delta == 0:
        return

    def new_amount(row):
        fighter = row.listfighterequipmentassignment.list_fighter
        if (
            fighter.content_fighter_id in masked_fighter_ids
            or fighter.legacy_content_fighter_id in masked_fighter_ids
        ):
            return None  # masked for this holder: receipt stands
        return row.pinned_amount + delta

    _rewrite_through_rows(
        ListFighterEquipmentAssignmentUpgrade,
        _upgrade_rows(lst).filter(
            contentequipmentupgrade__in=stack_upgrade_ids,
            pin_state=PinState.DERIVED,
        ),
        new_amount,
        sweep,
    )


def _sweep_upgrade(instance, lst, old_cost=None):
    from gyrinx.content.models import (
        ContentEquipment,
        ContentFighterEquipmentListUpgrade,
    )

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
        # SINGLE stacks price cumulatively: a rung's catalog correction
        # moves every DERIVED receipt holding that rung or a higher one by
        # the rung's own delta — except for holders whose per-rung override
        # masks the catalog price entirely.
        stack_ids = [u.pk for u in instance.same_stack_from_position()]
        if old_cost is None:
            # No pre-change value (direct caller outside the task path):
            # the delta is unknowable, so leave the receipts and flag the
            # snapshot fallback rather than guess.
            if (
                _upgrade_rows(lst)
                .filter(
                    contentequipmentupgrade__in=stack_ids,
                    pin_state=PinState.DERIVED,
                )
                .exists()
            ):
                sweep.has_masked = True
        else:
            masked_fighter_ids = set(
                ContentFighterEquipmentListUpgrade.objects.filter(
                    upgrade=instance
                ).values_list("fighter_id", flat=True)
            )
            _single_stack_delta_rewrite(
                lst,
                sweep,
                stack_ids,
                get_new_cost(instance, "cost") - old_cost,
                masked_fighter_ids,
            )
        affected_upgrade_ids = stack_ids
    sweep.has_unpinned = (
        sweep.has_unpinned
        or _live_through(
            _upgrade_rows(lst).filter(
                contentequipmentupgrade__in=affected_upgrade_ids,
                pin_state=PinState.UNPINNED,
            )
        ).exists()
    )
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
        defaults_can_mask=True,
    )
    # Live-repricing UNPINNED rows: current-context assignments this row
    # still prices, split by whether it prices the base or a profile.
    context_all = _base_rows(lst).filter(
        _holder_context_q(instance.fighter),
        content_equipment=instance.equipment,
    )
    cascade_ids = list(changed)
    if not instance.weapon_profile_id:
        # A base-pricing row also moves the live base of UNPINNED
        # context-matched assignments — their DERIVED expression
        # accessories must re-derive too (see _sweep_equipment).
        cascade_ids += list(
            context_all.filter(pinned_base_state=PinState.UNPINNED).values_list(
                "pk", flat=True
            )
        )
    _cascade_expression_accessories(lst, cascade_ids, sweep)

    context = context_all.filter(archived=False, list_fighter__archived=False)
    if instance.weapon_profile_id:
        sweep.has_unpinned = sweep.has_unpinned or (
            _profile_rows(lst)
            .filter(
                listfighterequipmentassignment__in=context,
                contentweaponprofile=instance.weapon_profile,
                pin_state=PinState.UNPINNED,
            )
            .exists()
        )
    else:
        sweep.has_unpinned = (
            sweep.has_unpinned
            or context.filter(pinned_base_state=PinState.UNPINNED).exists()
        )
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
        defaults_can_mask=True,
    )
    sweep.has_unpinned = (
        sweep.has_unpinned
        or (
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
    )
    return sweep


def _sweep_equipment_list_upgrade(instance, lst, old_cost=None):
    from gyrinx.content.models import ContentEquipment

    sweep = PinSweep(pin_capable=True)
    # MULTI-mode pins are SOURCE rows carrying this override's FK: flat copy.
    new = instance.cost
    _rewrite_through_rows(
        ListFighterEquipmentAssignmentUpgrade,
        _upgrade_rows(lst).filter(
            pinned_equipment_list_upgrade=instance, pin_state=PinState.SOURCE
        ),
        lambda r: new,
        sweep,
    )
    # SINGLE-mode pins are DERIVED amount-snapshots with no FK — this
    # override's contribution is folded into the cumulative receipt of every
    # holder who uses it, on this rung or any higher one. Corrections reach
    # them BY DELTA, scoped to holders in this override's fighter context
    # (a moved row's new holder doesn't use the override — the documented
    # v1 amount-snapshot imprecision).
    if instance.upgrade.equipment.upgrade_mode == ContentEquipment.UpgradeMode.SINGLE:
        stack_ids = [u.pk for u in instance.upgrade.same_stack_from_position()]
        derived_rows = _upgrade_rows(lst).filter(
            _holder_context_q(
                instance.fighter, prefix="listfighterequipmentassignment__"
            ),
            contentequipmentupgrade__in=stack_ids,
            pin_state=PinState.DERIVED,
        )
        if old_cost is None:
            if derived_rows.exists():
                sweep.has_masked = True  # delta unknowable outside the task path
        else:
            delta = instance.cost - old_cost
            if delta:
                _rewrite_through_rows(
                    ListFighterEquipmentAssignmentUpgrade,
                    derived_rows,
                    lambda r: r.pinned_amount + delta,
                    sweep,
                )
    sweep.has_unpinned = (
        sweep.has_unpinned
        or (
            _live_through(
                _upgrade_rows(lst).filter(
                    _holder_context_q(
                        instance.fighter, prefix="listfighterequipmentassignment__"
                    ),
                    # Per-rung override in cumulative pricing: this rung and
                    # every higher one reprice live (mirror of set_dirty).
                    contentequipmentupgrade__in=instance.upgrade.same_stack_from_position(),
                    pin_state=PinState.UNPINNED,
                )
            )
        ).exists()
    )
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
        defaults_can_mask=True,
    )
    context_all = _base_rows(lst).filter(content_equipment=instance.equipment)
    cascade_ids = list(changed)
    if not instance.weapon_profile_id:
        # A base-pricing item also moves the live base of UNPINNED matching
        # assignments — their DERIVED expression accessories must re-derive
        # too (see _sweep_equipment).
        cascade_ids += list(
            context_all.filter(pinned_base_state=PinState.UNPINNED).values_list(
                "pk", flat=True
            )
        )
    _cascade_expression_accessories(lst, cascade_ids, sweep)

    context = context_all.filter(archived=False, list_fighter__archived=False)
    if instance.weapon_profile_id:
        sweep.has_unpinned = sweep.has_unpinned or (
            _profile_rows(lst)
            .filter(
                listfighterequipmentassignment__in=context,
                contentweaponprofile=instance.weapon_profile,
                pin_state=PinState.UNPINNED,
            )
            .exists()
        )
    else:
        sweep.has_unpinned = (
            sweep.has_unpinned
            or context.filter(pinned_base_state=PinState.UNPINNED).exists()
        )
    return sweep


# Handlers whose amount-snapshot (DERIVED) rewrites need the source's
# pre-change value to apply corrections by delta.
_NEEDS_OLD_COST = None  # set below, after the handler definitions

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

_NEEDS_OLD_COST = {_sweep_upgrade, _sweep_equipment_list_upgrade}
