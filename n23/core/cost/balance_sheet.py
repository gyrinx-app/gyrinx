"""Balance sheet: a read-only, itemised reconciliation of a list's costs.

This is the verification instrument for the cost-pinning programme (#1826).
It decomposes every fighter and equipment assignment into priced component
lines, then checks three invariant families:

1. **Computed vs cached** — the live-computed cost of every clean (non-dirty)
   assignment, fighter, and list-level aggregate must equal its cached value
   (``rating_current`` / ``stash_current``). Divergence here is exactly the
   "cache says X, recompute says Y" drift class.
2. **Credits ledger** — ``credits_current`` must equal the chain anchor (the
   first ListAction's ``credits_before``) plus the sum of every recorded
   ``credits_delta``. Credits are a ledger, not a derivable quantity, so this
   is the only way to see a wrong ``credits_delta``.
3. **Action-chain continuity** — each action's ``*_before`` must equal the
   previous action's ``*_after``, and the newest action's ``*_after`` must
   equal the current cached values (when clean). A silent recompute or an
   unrecorded mutation shows up as a break in the chain.

Families 2 and 3 are scoped to lists that have an action chain (see
``List.create_action`` — lists without a bootstrap action don't record).

``build_balance_sheet()`` never writes. It is used by the situation-matrix
tests (``core/tests/test_balance_sheet.py``) and the staff debug view. A
"deep" mode that re-resolves pinned amounts against their price sources
arrives with the pin schema in a later phase of the programme.
"""

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from n23.core.models.list import List, PinState

# Component line kinds
KIND_BASE = "base"
KIND_PROFILES = "profiles"
KIND_ACCESSORIES = "accessories"
KIND_UPGRADES = "upgrades"

# Pricing provenance per component line. "pinned" means the amount comes from
# an acquisition receipt (#1826); "mixed" marks an aggregate line whose rows
# are only partially pinned (the pre-backfill state).
PRICING_LIVE = "live"
PRICING_USER_OVERRIDE = "user_override"
PRICING_PINNED = "pinned"
PRICING_MIXED = "mixed"


def _rows_pricing(rows) -> str:
    """Classify an aggregate component line by its through-rows' pins."""
    pinned = [r.pinned_amount is not None for r in rows]
    if not pinned or not any(pinned):
        return PRICING_LIVE
    if all(pinned):
        return PRICING_PINNED
    return PRICING_MIXED


# Pin attribution FKs, in resolution order — an assignment (base pin) or a
# through-row (profile/accessory/upgrade pin) carries exactly one when SOURCE.
_PIN_FK_FIELDS = (
    "pinned_equipment_list_item",
    "pinned_expansion_item",
    "pinned_equipment_list_accessory",
    "pinned_equipment_list_upgrade",
)


def _pin_fk(obj):
    """The first non-null pin attribution FK on an assignment or through-row."""
    for name in _PIN_FK_FIELDS:
        target = getattr(obj, name, None)
        if target is not None:
            return target
    return None


def _source_repr(state, amount, fk=None) -> str:
    """Human-readable attribution for one pinned component price (design §5.1) —
    what a receipt points at, for the pricing-column tooltip. Empty for an
    unpinned/absent amount (live resolution, no receipt to describe)."""
    if amount is None or state == PinState.UNPINNED:
        return ""
    if state == PinState.SOURCE:
        # A SOURCE pin should always name its FK; the fallback is defensive, and
        # stays neutral so it can't be misread as a user cost-override.
        where = str(fk) if fk is not None else "a price source"
        return f"Pinned to {where} ({amount}¢)"
    if state == PinState.CATALOG:
        return f"Catalog price at acquisition ({amount}¢)"
    if state == PinState.DERIVED:
        return f"Derived price ({amount}¢)"
    if state == PinState.ORPHANED:
        return f"Frozen — pricing source removed ({amount}¢)"
    return ""


def _rows_source_repr(rows) -> str:
    """Attribution summary for an aggregate line's through-rows: resolve a lone
    pinned row fully, else summarise the mix by state."""
    rows = list(rows)
    priced = [
        r
        for r in rows
        if r.pin_state != PinState.UNPINNED and r.pinned_amount is not None
    ]
    if not priced:
        return ""
    if len(rows) == 1:  # the sole row is priced (unpriced-only returned above)
        r = priced[0]
        return _source_repr(r.pin_state, r.pinned_amount, _pin_fk(r))
    counts = Counter(r.pin_state for r in priced)
    parts = [f"{n}× {PinState(s).label.lower()}" for s, n in sorted(counts.items())]
    live = len(rows) - len(priced)
    if live:
        parts.append(f"{live}× live")
    return "Pinned: " + ", ".join(parts)


@dataclass(frozen=True)
class ComponentLine:
    """One priced component inside an assignment."""

    kind: str  # KIND_* above
    amount: int
    pricing: str  # PRICING_* above
    detail: str = ""
    source_repr: str = ""  # human-readable attribution for the pricing tooltip


@dataclass(frozen=True)
class AssignmentBalance:
    """One equipment assignment (direct or default) on a fighter."""

    assignment_id: UUID | None
    equipment_name: str
    kind: str  # "assigned" | "default"
    lines: tuple[ComponentLine, ...]
    total_cost_override: int | None
    computed: int  # what cost_int() returns for this assignment
    cached_rating: int | None  # LFEA.rating_current; None for defaults
    dirty: bool

    @property
    def is_mismatch(self) -> bool:
        """Computed disagrees with a comparable (clean, present) cache.

        The single source of truth for family-1 assignment checks — used by
        both reconcile() and the debug template so they cannot drift.
        """
        return (
            self.cached_rating is not None
            and not self.dirty
            and self.computed != self.cached_rating
        )


@dataclass(frozen=True)
class FighterBalance:
    fighter_id: UUID
    name: str
    is_stash: bool
    zero_costed: bool  # dead/captured/sold — contributes 0 regardless of lines
    base: int
    advancements: int
    assignments: tuple[AssignmentBalance, ...]
    computed: int  # what cost_int() returns for this fighter
    cached_rating: int
    dirty: bool

    @property
    def is_mismatch(self) -> bool:
        """Computed disagrees with a clean cache (family-1 fighter check)."""
        return not self.dirty and self.computed != self.cached_rating


@dataclass(frozen=True)
class ActionLine:
    """A ListAction's cost-tracking fields, for chain checks and display."""

    action_id: UUID
    action_type: str
    description: str
    rating_before: int
    rating_delta: int
    stash_before: int
    stash_delta: int
    credits_before: int
    credits_delta: int

    @property
    def rating_after(self) -> int:
        return self.rating_before + self.rating_delta

    @property
    def stash_after(self) -> int:
        return self.stash_before + self.stash_delta

    @property
    def credits_after(self) -> int:
        return self.credits_before + self.credits_delta


@dataclass(frozen=True)
class ListBalance:
    list_id: UUID
    name: str
    fighters: tuple[FighterBalance, ...]  # active, non-stash
    stash: FighterBalance | None
    cached_rating: int
    cached_stash: int
    cached_credits: int
    dirty: bool
    actions: tuple[ActionLine, ...]  # oldest first; empty if no chain
    # Rows whose caches were skipped from comparison because they are dirty.
    # Dirty is a legitimate transient state; these are surfaced for display
    # but are not reconciliation problems by themselves.
    dirty_rows: tuple[str, ...] = field(default=())

    @property
    def has_action_chain(self) -> bool:
        return bool(self.actions)

    @property
    def all_fighters(self) -> tuple[FighterBalance, ...]:
        """Active fighters plus the stash, for uniform iteration."""
        return self.fighters + ((self.stash,) if self.stash else ())

    @property
    def rating_mismatch(self) -> bool:
        return not self.dirty and self.computed_rating != self.cached_rating

    @property
    def stash_mismatch(self) -> bool:
        return not self.dirty and self.computed_stash != self.cached_stash

    @property
    def computed_rating(self) -> int:
        return sum(f.computed for f in self.fighters)

    @property
    def computed_stash(self) -> int:
        return self.stash.computed if self.stash else 0

    def reconcile(self) -> list[str]:
        """Return human-readable reconciliation problems; [] == clean."""
        problems: list[str] = []

        # --- Family 1: computed vs cached, bottom-up -----------------------
        # The mismatch predicates live on the dataclasses (is_mismatch,
        # rating_mismatch, stash_mismatch) so the debug template highlights
        # exactly what reconcile() reports.
        for f in self.all_fighters:
            for a in f.assignments:
                if a.is_mismatch:
                    problems.append(
                        f"assignment '{a.equipment_name}' on '{f.name}': "
                        f"cached={a.cached_rating} computed={a.computed}"
                    )
            if f.is_mismatch:
                problems.append(
                    f"fighter '{f.name}': cached={f.cached_rating} "
                    f"computed={f.computed}"
                )

        if self.rating_mismatch:
            problems.append(
                f"list rating: cached={self.cached_rating} "
                f"computed={self.computed_rating}"
            )
        if self.stash_mismatch:
            problems.append(
                f"list stash: cached={self.cached_stash} computed={self.computed_stash}"
            )

        # Families 2 and 3 only apply to lists with an action chain.
        if not self.actions:
            return problems

        # --- Family 2: credits ledger --------------------------------------
        anchor = self.actions[0]
        ledger = anchor.credits_before + sum(a.credits_delta for a in self.actions)
        if ledger != self.cached_credits:
            problems.append(
                f"credits ledger: anchor {anchor.credits_before} + deltas "
                f"{ledger - anchor.credits_before} = {ledger}, "
                f"but credits_current={self.cached_credits}"
            )

        # --- Family 3: action-chain continuity -----------------------------
        prev = None
        for a in self.actions:
            if prev is not None:
                for label, before, after in (
                    ("rating", a.rating_before, prev.rating_after),
                    ("stash", a.stash_before, prev.stash_after),
                    ("credits", a.credits_before, prev.credits_after),
                ):
                    if before != after:
                        problems.append(
                            f"action chain break ({label}): action "
                            f"'{a.action_type}: {a.description or ''}' has "
                            f"{label}_before={before} but previous action "
                            f"ended at {after}"
                        )
            prev = a

        head = self.actions[-1]
        if not self.dirty:
            for label, after, current in (
                ("rating", head.rating_after, self.cached_rating),
                ("stash", head.stash_after, self.cached_stash),
                ("credits", head.credits_after, self.cached_credits),
            ):
                if after != current:
                    problems.append(
                        f"action head desync ({label}): newest action ends at "
                        f"{after} but {label}_current={current}"
                    )

        return problems


def _assignment_balance(virtual) -> AssignmentBalance:
    """Build the balance entry for one virtual assignment.

    Mirrors VirtualListFighterEquipmentAssignment.cost_int() exactly: default
    assignments contribute 0; a total_cost_override short-circuits the
    component sum for direct assignments.
    """
    kind = virtual.kind()
    if kind == "default":
        return AssignmentBalance(
            assignment_id=virtual.id,
            equipment_name=virtual.content_equipment.name,
            kind=kind,
            lines=(
                ComponentLine(KIND_BASE, 0, PRICING_LIVE, "default assignment (free)"),
            ),
            total_cost_override=None,
            computed=0,
            cached_rating=None,
            dirty=False,
        )

    assignment = virtual._assignment
    override = assignment.total_cost_override

    if assignment.cost_override is not None:
        base_pricing, base_detail = PRICING_USER_OVERRIDE, ""
        base_source = f"User override ({assignment.cost_override}¢)"
    elif assignment.pinned_base_amount is not None:
        base_pricing = PRICING_PINNED
        base_detail = assignment.pinned_base_state
        base_source = _source_repr(
            assignment.pinned_base_state,
            assignment.pinned_base_amount,
            _pin_fk(assignment),
        )
    else:
        base_pricing, base_detail, base_source = PRICING_LIVE, "", ""

    profile_rows = assignment.profile_rows.all()
    accessory_rows = assignment.accessory_rows.all()
    upgrade_rows = assignment.upgrade_rows.all()
    lines = (
        ComponentLine(
            KIND_BASE,
            assignment.base_cost_int(),
            base_pricing,
            base_detail,
            source_repr=base_source,
        ),
        ComponentLine(
            KIND_PROFILES,
            assignment.weapon_profiles_cost_int(),
            _rows_pricing(profile_rows),
            source_repr=_rows_source_repr(profile_rows),
        ),
        ComponentLine(
            KIND_ACCESSORIES,
            assignment.weapon_accessories_cost_int(),
            _rows_pricing(accessory_rows),
            source_repr=_rows_source_repr(accessory_rows),
        ),
        ComponentLine(
            KIND_UPGRADES,
            assignment.upgrade_cost_int(),
            _rows_pricing(upgrade_rows),
            source_repr=_rows_source_repr(upgrade_rows),
        ),
    )

    if override is not None:
        computed = override
    else:
        computed = sum(line.amount for line in lines)

    return AssignmentBalance(
        assignment_id=assignment.id,
        equipment_name=virtual.content_equipment.name,
        kind=kind,
        lines=lines,
        total_cost_override=override,
        computed=computed,
        cached_rating=assignment.rating_current,
        dirty=assignment.dirty,
    )


def _fighter_balance(fighter) -> FighterBalance:
    zero_costed = fighter.should_have_zero_cost

    assignments = tuple(_assignment_balance(v) for v in fighter.assignments())
    base = fighter._base_cost_int
    advancements = fighter._advancement_cost_int

    if zero_costed:
        computed = 0
    else:
        computed = base + advancements + sum(a.computed for a in assignments)

    return FighterBalance(
        fighter_id=fighter.id,
        name=fighter.name,
        is_stash=fighter.is_stash,
        zero_costed=zero_costed,
        base=base,
        advancements=advancements,
        assignments=assignments,
        computed=computed,
        cached_rating=fighter.rating_current,
        dirty=fighter.dirty,
    )


def build_balance_sheet(lst: List) -> ListBalance:
    """Build the balance sheet for a list. Read-only; never writes.

    The decomposition mirrors the live cost computation (``cost_int()``) at
    each level; the situation-matrix tests assert the two agree, so a change
    to cost semantics that this module doesn't track fails loudly rather than
    silently reconciling.
    """
    fighters = []
    stash = None
    for fighter in lst.fighters():
        balance = _fighter_balance(fighter)
        if balance.is_stash:
            stash = balance
        else:
            fighters.append(balance)

    actions = tuple(
        ActionLine(
            action_id=a.id,
            action_type=a.action_type,
            description=a.description or "",
            rating_before=a.rating_before,
            rating_delta=a.rating_delta,
            stash_before=a.stash_before,
            stash_delta=a.stash_delta,
            credits_before=a.credits_before,
            credits_delta=a.credits_delta,
        )
        for a in lst.actions.order_by("created", "id")
    )

    dirty_rows = []
    for f in fighters + ([stash] if stash else []):  # ListBalance not built yet
        if f.dirty:
            dirty_rows.append(f"fighter '{f.name}'")
        for a in f.assignments:
            if a.dirty:
                dirty_rows.append(f"assignment '{a.equipment_name}' on '{f.name}'")

    return ListBalance(
        list_id=lst.id,
        name=lst.name,
        fighters=tuple(fighters),
        stash=stash,
        cached_rating=lst.rating_current,
        cached_stash=lst.stash_current,
        cached_credits=lst.credits_current,
        dirty=lst.dirty,
        actions=actions,
        dirty_rows=tuple(dirty_rows),
    )
