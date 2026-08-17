"""Plan or apply a slots-and-picks conversion, from the shell.

The rehearsal tool: point it at a database holding the system (a fork of
the prod mirror, a restore of a full dump) and read the plan; add
``--apply`` to perform it, with the conversion's own refusal standing
between the plan and a committed write.

This is how a conversion is checked before it ships, and how a database
nobody runs a console against — a developer's, an old fork — is brought
across. Production is not one of those: it converts from the maintenance
console (see :mod:`n26.maintenance`), which runs the same plan and apply
and writes down what happened.
"""

from django.core.management.base import BaseCommand, CommandError

from n26.library.conversion import SYSTEMS, ConversionRefused, apply


class Command(BaseCommand):
    help = "Plan (default) or apply a slots-and-picks conversion."

    def add_arguments(self, parser):
        parser.add_argument("system", choices=sorted(SYSTEMS))
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform the plan. Without this, the plan is printed and nothing is written.",
        )

    def handle(self, *args, **options):
        plan = SYSTEMS[options["system"]]()
        if not options["apply"]:
            for problem in plan.problems:
                self.stdout.write(self.style.ERROR(f"problem: {problem}"))
            for line in plan.preview():
                self.stdout.write(line)
            self.stdout.write("(planned only — nothing written)")
            return
        # The apply report opens with the preview, so it is not said twice.
        try:
            for line in apply(plan):
                self.stdout.write(line)
        except ConversionRefused as refused:
            raise CommandError(str(refused)) from None
