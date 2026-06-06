"""Service for the persistent-stash data repair (#1825).

For each persistent-category equipment assignment currently on a stash
fighter, find the closest matching UPDATE_FIGHTER "killed" ``ListAction`` on
the same list within a ±1s window — essentially same-transaction matches from
``handle_fighter_kill``. If a clean match exists and the dying fighter is
currently dead and not archived, the assignment is moved back to that fighter
and the stash cache is reconciled.

Used by both the ``migrate_persistent_stash_items`` management command and the
admin maintenance view at ``/admin/maintenance/persistent-stash/``.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Optional

from django.db import transaction

from gyrinx.core.models import List
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

# Same-transaction kills land within microseconds; 1s is a safe ceiling.
WINDOW = timedelta(seconds=1)
# Two distinct kill actions inside this slice of the window means we can't
# confidently attribute the stash assignment to either — skip rather than
# guess.
AMBIGUOUS_TIE_S = 0.1

SKIP_REASONS = (
    "no_match",
    "ambiguous",
    "null_fighter",
    "alive",
    "archived",
    "wrong_list",
)


@dataclass
class Candidate:
    """One persistent-category stash assignment and the decision about it."""

    assignment_id: str
    equipment_name: str
    category_name: str
    list_id: str
    list_name: str
    decision: str  # "move" or one of SKIP_REASONS
    dying_fighter_id: Optional[str] = None
    dying_fighter_name: Optional[str] = None
    detail: str = ""


@dataclass
class ApplyResult:
    moved: int = 0
    affected_lists: int = 0
    skipped: dict = field(default_factory=dict)
    per_list: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------


def _candidates_queryset(list_id=None):
    qs = (
        ListFighterEquipmentAssignment.objects.filter(
            list_fighter__content_fighter__is_stash=True,
            content_equipment__category__persistent=True,
        )
        .exclude(archived=True)
        .select_related(
            "list_fighter__list",
            "list_fighter__content_fighter",
            "content_equipment__category",
        )
        .order_by("created")
    )
    if list_id:
        qs = qs.filter(list_fighter__list_id=list_id)
    return qs


def _fetch_kills_by_list(list_ids) -> dict[str, list[ListAction]]:
    """Batch-fetch kill ListActions for the candidate lists in a single query.

    Replaces an N+1: previously _classify() ran one ListAction query per
    assignment. With ~281 assignments in prod that meant ~282 round-trips
    to Cloud SQL. Now it's one round-trip + Python filtering by window.

    Filters ``applied=True`` so we only match committed kills, not in-flight
    rows that might be rolled back.
    """
    by_list: dict[str, list[ListAction]] = defaultdict(list)
    if not list_ids:
        return by_list
    for k in (
        ListAction.objects.filter(
            list_id__in=list_ids,
            action_type=ListActionType.UPDATE_FIGHTER,
            description__icontains="killed",
            applied=True,
        )
        .select_related("list_fighter")
        .iterator()
    ):
        by_list[k.list_id].append(k)
    return by_list


def _classify(assignment, kills_in_list: list[ListAction]):
    """Return (decision, dying_fighter_or_None, detail_str). Pure Python."""
    list_id = assignment.list_fighter.list_id

    lo, hi = assignment.created - WINDOW, assignment.created + WINDOW
    cands = [k for k in kills_in_list if lo <= k.created <= hi]
    if not cands:
        return ("no_match", None, "no kill action in ±1s window")

    cands.sort(key=lambda x: abs((x.created - assignment.created).total_seconds()))
    if len(cands) > 1:
        d0 = abs((cands[0].created - assignment.created).total_seconds())
        d1 = abs((cands[1].created - assignment.created).total_seconds())
        if abs(d0 - d1) < AMBIGUOUS_TIE_S:
            return ("ambiguous", None, "multiple kill actions within 0.1s")

    match = cands[0]
    dying = match.list_fighter
    if dying is None:
        return ("null_fighter", None, "matched kill action has null list_fighter")
    if dying.archived:
        return ("archived", dying, f"dying fighter {dying.name!r} is archived")
    if dying.injury_state != ListFighter.DEAD:
        return (
            "alive",
            dying,
            f"dying fighter {dying.name!r} not currently dead ({dying.injury_state})",
        )
    if dying.list_id != list_id:
        return ("wrong_list", dying, "dying fighter is on a different list")
    return ("move", dying, "")


def find_candidates(list_id=None) -> list[Candidate]:
    """Return Candidate decisions for the current DB state (read-only).

    Uses two queries total: one for the candidate assignments, one for all
    kill ListActions on the affected lists. Window-filtering happens in
    Python.
    """
    assignments = list(_candidates_queryset(list_id))
    list_ids = {a.list_fighter.list_id for a in assignments}
    kills_by_list = _fetch_kills_by_list(list_ids)

    out: list[Candidate] = []
    for a in assignments:
        kills = kills_by_list.get(a.list_fighter.list_id, [])
        decision, dying, detail = _classify(a, kills)
        cat = a.content_equipment.category
        out.append(
            Candidate(
                assignment_id=str(a.id),
                equipment_name=a.content_equipment.name,
                category_name=cat.name if cat else "",
                list_id=str(a.list_fighter.list_id),
                list_name=a.list_fighter.list.name,
                decision=decision,
                dying_fighter_id=str(dying.id) if dying else None,
                dying_fighter_name=dying.name if dying else None,
                detail=detail,
            )
        )
    return out


def apply(list_id=None, *, triggered_by=None) -> ApplyResult:
    """Apply moves for the matching candidates and reconcile caches.

    Returns an ApplyResult with per-list detail and per-reason skip counts.
    """
    candidates = find_candidates(list_id)
    moves_by_list: dict[str, list[Candidate]] = {}
    skipped = {r: 0 for r in SKIP_REASONS}
    for c in candidates:
        if c.decision == "move":
            moves_by_list.setdefault(c.list_id, []).append(c)
        else:
            skipped[c.decision] += 1

    per_list: list[dict] = []
    moved = 0
    skipped_at_apply: dict[str, int] = defaultdict(int)
    for lid, moves in moves_by_list.items():
        applied_in_list: list[Candidate] = []
        with transaction.atomic():
            lst = List.objects.select_for_update().get(id=lid)
            rating_before = lst.rating_current
            stash_before = lst.stash_current
            credits_before = lst.credits_current
            fighters_to_dirty: set = set()

            for c in moves:
                # Re-validate inside the lock — the owner could have edited
                # the gang between find_candidates() (no lock) and now. A
                # stale plan could otherwise move an assignment that's been
                # reassigned, sold, or whose dying fighter resurrected.
                try:
                    assignment = ListFighterEquipmentAssignment.objects.get(
                        id=c.assignment_id
                    )
                    dying = ListFighter.objects.get(id=c.dying_fighter_id)
                except (
                    ListFighterEquipmentAssignment.DoesNotExist,
                    ListFighter.DoesNotExist,
                ):
                    skipped_at_apply["disappeared"] += 1
                    continue
                if assignment.archived:
                    skipped_at_apply["archived_now"] += 1
                    continue
                # Only proceed if the assignment is still on a stash fighter
                # on the *same* list, and the target dying fighter is still
                # dead and not archived. Stringify the FK UUIDs because
                # ``lid`` came through Candidate as str.
                current_owner = assignment.list_fighter
                if (
                    str(current_owner.list_id) != str(lid)
                    or not current_owner.content_fighter.is_stash
                ):
                    skipped_at_apply["moved_off_stash"] += 1
                    continue
                if dying.archived or dying.injury_state != ListFighter.DEAD:
                    skipped_at_apply["fighter_state_changed"] += 1
                    continue

                fighters_to_dirty.add(assignment.list_fighter_id)
                fighters_to_dirty.add(dying.id)
                assignment.list_fighter = dying
                assignment.save(update_fields=["list_fighter"])
                applied_in_list.append(c)

            # If every planned move for this list was invalidated at apply
            # time, skip the recompute and don't write an empty audit row.
            if not applied_in_list:
                continue

            # The kill handler bumped the stash fighter's cached rating via a
            # delta when it transferred the gear; that bump never reconciles
            # against actual assignments unless we mark the fighter dirty.
            ListFighter.objects.filter(id__in=fighters_to_dirty).update(dirty=True)
            lst.dirty = True
            lst.facts_from_db(update=True)
            stash_after = lst.stash_current
            rating_after = lst.rating_current
            credits_after = lst.credits_current

            item_summary = ", ".join(
                f"{c.equipment_name} → {c.dying_fighter_name}" for c in applied_in_list
            )
            audit = ListAction.objects.create(
                list=lst,
                owner=triggered_by or lst.owner,
                applied=True,
                action_type=ListActionType.UPDATE_FIGHTER,
                description=(
                    "Persistent gear restored to dead Fighters "
                    f"(#1825 data repair): {item_summary}"
                ),
                rating_before=rating_before,
                stash_before=stash_before,
                credits_before=credits_before,
                rating_delta=rating_after - rating_before,
                stash_delta=stash_after - stash_before,
                credits_delta=credits_after - credits_before,
            )

            per_list.append(
                {
                    "list_id": lid,
                    "list_name": lst.name,
                    "items": [
                        f"{c.equipment_name} → {c.dying_fighter_name}"
                        for c in applied_in_list
                    ],
                    "audit_action_id": str(audit.id),
                    "stash_before": stash_before,
                    "stash_after": stash_after,
                }
            )
            moved += len(applied_in_list)

    # Surface any apply-time invalidations alongside the find-time skip counts.
    skipped.update(dict(skipped_at_apply))
    return ApplyResult(
        moved=moved,
        affected_lists=len(per_list),
        skipped=skipped,
        per_list=per_list,
    )
