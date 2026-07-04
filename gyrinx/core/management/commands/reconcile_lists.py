"""Audited cache reconciliation across lists (#1826 Phase 8, §4.8.2).

Runs the reconcile core over every list (or the ids given), truing up the
cached rating/stash chain from live resolution and recording any movement
as a RECONCILE action. Run this BEFORE backfill_pins: freezing amounts on
top of drifted caches would enshrine the drift.
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

        total = moved = 0
        for lst in qs.iterator():
            result = reconcile_list(lst)
            total += 1
            if result.moved:
                moved += 1
                self.stdout.write(
                    f"{lst.name} ({lst.id}): rating "
                    f"{result.rating_before}→{result.rating_after}, stash "
                    f"{result.stash_before}→{result.stash_after}"
                    + ("" if result.action else " [no action: list untracked]")
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled {total} list(s); {moved} had drift corrected."
            )
        )
