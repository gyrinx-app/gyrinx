"""Create earned rank allowances for fighters that predate structured actions."""

from django.core.management.base import BaseCommand

from n26.core.allowances import bootstrap_rank_allowances, starting_counter_value
from n26.core.models import Assignment
from n26.core.operations import operation


class Command(BaseCommand):
    help = "Grant unused earned action allowances from trustworthy starting counters."

    def handle(self, *args, **options):
        granted = skipped = 0
        assignments = (
            Assignment.objects.filter(
                counter__isnull=False,
                miniature_root__isnull=False,
                archived=False,
                counter_value__isnull=False,
            )
            .select_related(
                "counter",
                "counter_value",
                "materialised_from",
                "miniature_root__membership__gang",
            )
            .order_by("gang_root_id", "created")
        )
        for assignment in assignments:
            if starting_counter_value(assignment) is None:
                skipped += 1
                self.stdout.write(
                    f"Skipped {assignment.miniature_root}: {assignment.counter} has no opening baseline."
                )
                continue
            gang = assignment.miniature_root.membership.gang
            with operation(gang) as op:
                granted += len(bootstrap_rank_allowances(op, assignment))
        self.stdout.write(
            self.style.SUCCESS(
                f"Granted {granted} allowance(s); skipped {skipped} counter(s)."
            )
        )
