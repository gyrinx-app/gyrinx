"""Universal resolve-and-pin backfill (#1826 Phase 8, §4.8.4).

Synchronous driver for ops use; the async task (gyrinx.core.tasks.
backfill_pins) does the same work batch-by-batch on the task runner.
Idempotent: re-runs skip already-pinned rows. Run reconcile_lists first.
"""

from django.core.management.base import BaseCommand, CommandError

from gyrinx.core.cost.pinning import pin_assignment
from gyrinx.core.models.list import ListFighterEquipmentAssignment


class Command(BaseCommand):
    help = "Write acquisition receipts onto every legacy assignment via the pinning choke point."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument(
            "--max-consecutive-failures",
            type=int,
            default=25,
            help="Abort if this many assignments fail in a row — a systemic "
            "pinning bug should stop the walk, not log its way through the "
            "whole table.",
        )

    def handle(self, *args, **options):
        qs = ListFighterEquipmentAssignment.objects.order_by("id")
        total = pinned = failed = streak = 0
        for assignment_id in qs.values_list("id", flat=True).iterator(
            chunk_size=options["batch_size"]
        ):
            total += 1
            try:
                pinned += pin_assignment(assignment_id)
                streak = 0
            except Exception as e:
                failed += 1
                streak += 1
                self.stderr.write(f"FAILED {assignment_id}: {e}")
                if streak >= options["max_consecutive_failures"]:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Aborting: {streak} consecutive failures "
                            f"(cursor {assignment_id}). Fix the cause and "
                            "re-run — the backfill is idempotent."
                        )
                    )
                    return
            if total % options["batch_size"] == 0:
                self.stdout.write(
                    f"...{total} assignments processed, {pinned} rows pinned"
                )
        if failed:
            # Automation must not read a partial backfill as complete.
            raise CommandError(
                f"Backfill INCOMPLETE: {total} assignments walked, {pinned} "
                f"rows pinned, {failed} FAILED (left unpinned). Fix the "
                "cause and re-run — idempotent, retries only unpinned rows."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {total} assignments, {pinned} rows pinned."
            )
        )
