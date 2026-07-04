"""Audited cache reconciliation across lists (#1826 Phase 8, §4.8.2).

Runs the reconcile core over every list (or the ids given), truing up the
cached rating/stash chain from live resolution and recording any movement
as a RECONCILE action. Run this BEFORE backfill_pins: freezing amounts on
top of drifted caches would enshrine the drift.

Prefer a quiet window: user actions landing mid-reconcile on the same list
can chain off the same ledger head (a short, per-list race a re-run
repairs).
"""

from django.core.management.base import BaseCommand

from gyrinx.core.cost.reconcile import reconcile_list
from gyrinx.core.models.list import List


class Command(BaseCommand):
    help = "True up cached list costs from live resolution, recording movement as RECONCILE actions."

    def add_arguments(self, parser):
        parser.add_argument(
            "list_ids", nargs="*", help="Specific list ids (default: all lists)"
        )

    def handle(self, *args, **options):
        qs = List.objects.order_by("id")
        if options["list_ids"]:
            qs = qs.filter(id__in=options["list_ids"])

        total = moved = clamped = 0
        for lst in qs.iterator():
            result = reconcile_list(lst)
            total += 1
            # Report head repairs too: a stale chain head behind a correct
            # cache books an action without any cache movement.
            if result.moved or result.action:
                moved += 1
                self.stdout.write(
                    f"{lst.name} ({lst.id}): rating "
                    f"{result.rating_before}→{result.rating_after}, stash "
                    f"{result.stash_before}→{result.stash_after}"
                    + (
                        ""
                        if result.action
                        else (
                            " [no entry needed: cache-only repair]"
                            if result.tracked
                            else " [no action: list untracked]"
                        )
                    )
                )
            if result.clamped:
                clamped += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"CLAMPED {lst.name} ({lst.id}): computed total was "
                        "negative; cache floors at zero. The remainder is a "
                        "real continuity gap — investigate this list."
                    )
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled {total} list(s); {moved} corrected; "
                f"{clamped} hit the zero-floor clamp."
            )
        )
