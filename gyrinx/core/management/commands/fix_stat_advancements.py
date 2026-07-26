"""Finish moving stat advancements onto the mod system, and tell players (#2070).

Dry run by default. Pass ``--apply`` to write, and ``--notify`` to also send the
affected players a message. Read the dry run before applying: it changes stats
that people can see.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from gyrinx.core.stat_advancement_cleanup import (
    SITUATION_LABELS,
    STAT_NAMES,
    apply_plan,
    build_messages,
    build_plan,
    send_messages,
)


class Command(BaseCommand):
    help = (
        "Convert the stat advancements migration 0196 left behind, correct the "
        "stats they were inflating, and notify affected players."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without this, nothing is modified.",
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Also send affected players a message. Requires --apply.",
        )
        parser.add_argument(
            "--verbose-plan",
            action="store_true",
            help="List every pair, including the ones being left alone.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        notify = options["notify"]

        if notify and not apply:
            self.stderr.write(
                self.style.ERROR("--notify needs --apply; nothing would have changed.")
            )
            return

        plan = build_plan()

        self.stdout.write("Situations found:")
        for situation, count in plan.by_situation().items():
            self.stdout.write(
                f"  {count:>4}  ({situation}) {SITUATION_LABELS[situation]}"
            )

        acted = plan.acted_on
        visible = plan.visible
        messages = build_messages(plan)

        self.stdout.write("")
        self.stdout.write(f"Pairs to change:        {len(acted)}")
        self.stdout.write(f"Stats players will see: {len(visible)}")
        self.stdout.write(f"Messages to send:       {len(messages)}")

        if visible:
            self.stdout.write("")
            self.stdout.write("Visible changes:")
            for change in sorted(visible, key=lambda c: (c.list_name, c.fighter_name)):
                stat_name = STAT_NAMES.get(change.stat, change.stat)
                self.stdout.write(
                    f"  {change.direction:<4} {change.list_name} / "
                    f"{change.fighter_name} / {stat_name}: "
                    f"{change.displayed_before} -> {change.displayed_after}"
                )

        if options["verbose_plan"]:
            self.stdout.write("")
            self.stdout.write("Every pair:")
            for change in sorted(
                plan.changes, key=lambda c: (c.situation, c.list_name)
            ):
                self.stdout.write(
                    f"  ({change.situation}) {change.list_name} / "
                    f"{change.fighter_name} / {change.stat}: "
                    f"override {change.override_before!r} -> {change.override_after!r}"
                )

        if not apply:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("Dry run — nothing written. Re-run with --apply.")
            )
            return

        with transaction.atomic():
            changed = apply_plan(plan)
        self.stdout.write(self.style.SUCCESS(f"Applied {changed} changes."))

        if notify:
            sent = send_messages(messages)
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} messages."))
        elif messages:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(messages)} players saw a stat change but were not told "
                    "(--notify not given)."
                )
            )
