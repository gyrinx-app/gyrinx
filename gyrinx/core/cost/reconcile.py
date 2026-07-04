"""Audited cache reconciliation (#1826 Phase 8, §4.8.2).

Cached ratings can drift from what the source-of-truth assignments compute —
years of the pre-programme drift producers (§1.2) left stale values on
regular fighters, not just stashes. Before the backfill freezes amounts en
masse, every cache must be trued up — and every value-changing recompute
must be RECORDED, because a silent snap breaks the ledger-continuity
invariant (§5.1 family 3) that the whole balance-sheet harness stands on.

`reconcile_list` rebuilds the full chain (assignment → fighter → list caches)
from live resolution, ignoring dirty flags, and writes a single
ListActionType.RECONCILE action carrying the before-values and deltas when
the list's cached totals moved. Deltas are recorded with skip_apply — the
recompute already wrote the absolute values, so the clamped delta-apply path
(`max(0, current + delta)`, the silent continuity hazard §4.8.2 warns about)
never runs.

Credits are never touched: reconciliation corrects the *books*, it is not a
wealth event.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import format_cost_display


@dataclass(frozen=True)
class ReconcileResult:
    list_id: object
    rating_before: int
    stash_before: int
    rating_after: int
    stash_after: int
    action: Optional[ListAction]

    @property
    def moved(self) -> bool:
        return (
            self.rating_after != self.rating_before
            or self.stash_after != self.stash_before
        )


def reconcile_list(lst, user=None, rebuild_fighters=True) -> ReconcileResult:
    """True up one list's cache chain, recording any movement.

    With ``rebuild_fighters`` (the default), every fighter's assignment and
    fighter caches are rebuilt from live resolution first, ignoring dirty
    flags — drift by definition hides behind a clean flag. Pass False when
    the caller has already rebuilt the fighters (the admin per-fighter
    action) and only the list-level roll-up + audit record are needed.

    Lists outside the action system (no initial action) get their caches
    fixed but no record — there is no chain to keep continuous.
    """
    with transaction.atomic():
        fresh = List.objects.get(pk=lst.pk)
        rating_before = fresh.rating_current
        stash_before = fresh.stash_current

        if rebuild_fighters:
            for fighter in fresh.listfighter_set.select_related("content_fighter"):
                assignments = (
                    ListFighterEquipmentAssignment.objects.with_related_data().filter(
                        list_fighter=fighter
                    )
                )
                for assignment in assignments:
                    assignment.facts_from_db(update=True)
                fighter.facts_from_db(update=True)

        facts = fresh.facts_from_db(update=True)

        # The action chains off the LEDGER HEAD, not the cached values —
        # drift is by definition an un-audited cache mutation, so the chain's
        # last "after" is the only continuous baseline (family 3 checks each
        # action's before against the previous action's after, pairwise). The
        # recorded delta is therefore the accumulated un-audited movement the
        # ledger is absorbing.
        action = None
        head = fresh.latest_action
        if head is not None:
            head_rating = head.rating_before + head.rating_delta
            head_stash = head.stash_before + head.stash_delta
            head_credits = head.credits_before + head.credits_delta
            rating_delta = facts.rating - head_rating
            stash_delta = facts.stash - head_stash
            if rating_delta or stash_delta:
                parts = []
                if rating_delta:
                    parts.append(
                        f"rating {format_cost_display(rating_delta, show_sign=True)}"
                    )
                if stash_delta:
                    parts.append(
                        f"stash {format_cost_display(stash_delta, show_sign=True)}"
                    )
                action = fresh.create_action(
                    user=user,
                    action_type=ListActionType.RECONCILE,
                    description=(
                        "Reconciled cached values to computed ("
                        + ", ".join(parts)
                        + ")"
                    ),
                    rating_before=head_rating,
                    stash_before=head_stash,
                    # Credits chain off the head too — defaulting to the
                    # cached value would mint a NEW chain break at this very
                    # link on lists whose credits chain is already broken.
                    credits_before=head_credits,
                    rating_delta=rating_delta,
                    stash_delta=stash_delta,
                    credits_delta=0,
                    # facts_from_db already wrote the absolute values;
                    # applying the deltas again would double-move (and the
                    # apply path clamps at zero, which silently breaks chain
                    # continuity).
                    skip_apply=["rating", "stash"],
                )

        return ReconcileResult(
            list_id=fresh.pk,
            rating_before=rating_before,
            stash_before=stash_before,
            rating_after=facts.rating,
            stash_after=facts.stash,
            action=action,
        )
