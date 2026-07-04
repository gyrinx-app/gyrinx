"""Universal resolve-and-pin backfill (#1826 Phase 8, §4.8.4).

Synchronous driver for ops use; the async task (gyrinx.core.tasks.
backfill_pins) does the same work batch-by-batch on the task runner.
Idempotent: re-runs skip already-pinned rows. Run reconcile_lists first.
"""

from django.core.management.base import BaseCommand

from gyrinx.core.cost.pinning import pin_assignment
from gyrinx.core.models.list import ListFighterEquipmentAssignment


class Command(BaseCommand):
    help = "Write acquisition receipts onto every legacy assignment via the pinning choke point."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=250)

    def handle(self, *args, **options):
        qs = ListFighterEquipmentAssignment.objects.order_by("id")
        total = pinned = failed = 0
        for assignment_id in qs.values_list("id", flat=True).iterator(
            chunk_size=options["batch_size"]
        ):
            total += 1
            try:
                pinned += pin_assignment(
                    ListFighterEquipmentAssignment.objects.get(pk=assignment_id)
                )
            except Exception as e:
                failed += 1
                self.stderr.write(f"FAILED {assignment_id}: {e}")
            if total % options["batch_size"] == 0:
                self.stdout.write(
                    f"...{total} assignments processed, {pinned} rows pinned"
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {total} assignments, {pinned} rows pinned, {failed} failures."
            )
        )
