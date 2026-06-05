"""
Move persistent-category equipment off stash fighters and back onto the dying
fighter that originally carried it.

Background (#1825): mutations / armour / other persistent-category gear should
stay with a Fighter when they die — the kill handler enforces this today. But
older kills (pre-persistent-flag) transferred such items to the stash. This
command undoes that for items whose provenance can be proven from the
ListAction ledger: assignment.created is within ±1s of an UPDATE_FIGHTER kill
action on the same list. That window is essentially "same atomic transaction"
since the kill handler creates assignments and the action in one
``transaction.atomic`` block.

Items that can't be proven from the ledger are left alone. Users will see the
ones we move disappear from their stash and reappear on the dead Fighter's
card (where the rules already render persistent gear). An audit ListAction is
appended per affected list to keep the action ledger self-consistent.

Defaults to dry-run; pass ``--apply`` to commit.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
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


class Command(BaseCommand):
    help = (
        "Move persistent-category gear off stash fighters back to the dying "
        "fighter that originally carried it. Only acts on items provably from "
        "a kill via the ListAction ledger (assignment.created within "
        "±1s of an UPDATE_FIGHTER kill action). Dry-run by default; "
        "pass --apply to commit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually move items and append audit ListAction entries.",
        )
        parser.add_argument(
            "--list-id",
            type=str,
            default=None,
            help="Restrict to a single list (useful for local testing).",
        )
        parser.add_argument(
            "--verbose-skips",
            action="store_true",
            help="Print one line per skipped item with the reason.",
        )

    def handle(self, *args, **options):
        do_apply = options.get("apply", False)
        list_id = options.get("list_id")
        verbose_skips = options.get("verbose_skips", False)
        mode = "APPLY" if do_apply else "DRY RUN"

        self.stdout.write(self.style.NOTICE(f"[{mode}] migrate_persistent_stash_items"))

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

        moves_by_list: dict[str, list[tuple]] = {}
        skips = {
            "no_match": 0,
            "ambiguous": 0,
            "null_fighter": 0,
            "alive": 0,
            "archived": 0,
            "wrong_list": 0,
        }
        scanned = 0

        for a in qs.iterator():
            scanned += 1
            decision = self._classify(a)
            if decision[0] == "move":
                moves_by_list.setdefault(a.list_fighter.list_id, []).append(
                    (a, decision[1])
                )
            else:
                skips[decision[0]] += 1
                if verbose_skips:
                    self._log_skip(a, decision[0], decision[1])

        moved = 0
        affected = 0
        for lid, moves in moves_by_list.items():
            affected += 1
            moved += len(moves)
            self._process_list(lid, moves, do_apply=do_apply)

        self.stdout.write(self.style.NOTICE(f"\nSUMMARY [{mode}]"))
        self.stdout.write(f"  scanned                : {scanned}")
        self.stdout.write(f"  {'moved' if do_apply else 'would-move'}: {moved}")
        self.stdout.write(f"  affected lists         : {affected}")
        for k, v in skips.items():
            self.stdout.write(f"  skip:{k:13s}     : {v}")

    # ------------------------------------------------------------------ helpers

    def _classify(self, assignment):
        """Return ('move', dying_fighter) or ('<skip_reason>', detail_str)."""
        list_id = assignment.list_fighter.list_id
        candidates = list(
            ListAction.objects.filter(
                list_id=list_id,
                action_type=ListActionType.UPDATE_FIGHTER,
                description__icontains="killed",
                created__gte=assignment.created - WINDOW,
                created__lte=assignment.created + WINDOW,
            ).select_related("list_fighter")
        )
        if not candidates:
            return ("no_match", "no kill action in ±1s window")

        candidates.sort(
            key=lambda x: abs((x.created - assignment.created).total_seconds())
        )
        # Ambiguous tie: two top candidates near-identical in distance.
        if len(candidates) > 1:
            d0 = abs((candidates[0].created - assignment.created).total_seconds())
            d1 = abs((candidates[1].created - assignment.created).total_seconds())
            if abs(d0 - d1) < AMBIGUOUS_TIE_S:
                return ("ambiguous", "multiple kill actions within 0.1s")

        match = candidates[0]
        dying = match.list_fighter
        if dying is None:
            return ("null_fighter", "matched kill action has null list_fighter")
        if dying.archived:
            return ("archived", f"dying fighter {dying.name!r} is archived")
        if dying.injury_state != ListFighter.DEAD:
            return (
                "alive",
                f"dying fighter {dying.name!r} not currently dead ({dying.injury_state})",
            )
        if dying.list_id != list_id:
            return ("wrong_list", "dying fighter is on a different list")
        return ("move", dying)

    def _process_list(self, list_id, moves, do_apply: bool):
        with transaction.atomic():
            lst = List.objects.select_for_update().get(id=list_id)
            rating_before = lst.rating_current
            stash_before = lst.stash_current
            credits_before = lst.credits_current
            fighters_to_dirty: set = set()

            for assignment, dying in moves:
                self.stdout.write(
                    f"  {'MOVE' if do_apply else 'WOULD MOVE'}: "
                    f"{assignment.content_equipment.name!r} → {dying.name!r} "
                    f"(list {lst.name!r}, assign {assignment.id})"
                )
                if do_apply:
                    fighters_to_dirty.add(assignment.list_fighter_id)
                    fighters_to_dirty.add(dying.id)
                    assignment.list_fighter = dying
                    assignment.save(update_fields=["list_fighter"])

            if not do_apply:
                return

            # The kill handler bumped the stash fighter's cached rating via a
            # delta when it transferred the gear; that bump never reconciles
            # against actual assignments unless we mark the fighter dirty.
            # Without this, facts_from_db trusts the stale cached value and
            # writes it straight back to list.stash_current.
            ListFighter.objects.filter(id__in=fighters_to_dirty).update(dirty=True)
            lst.dirty = True
            lst.facts_from_db(update=True)
            stash_after = lst.stash_current
            rating_after = lst.rating_current
            credits_after = lst.credits_current

            item_summary = ", ".join(
                f"{a.content_equipment.name} → {d.name}" for a, d in moves
            )
            ListAction.objects.create(
                list=lst,
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

    def _log_skip(self, assignment, reason_code, detail):
        self.stdout.write(
            f"  SKIP[{reason_code}]: {assignment.content_equipment.name!r} "
            f"on list {assignment.list_fighter.list_id} — {detail}"
        )
