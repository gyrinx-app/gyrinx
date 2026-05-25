"""Attach bundled SVG house icons to their matching ContentHouse records.

The icon set and mapping live in :mod:`gyrinx.content.house_icons`. A data
migration applies the same icons automatically on deploy; this command exists
for local use and for re-running / overwriting after the migration has run.

    manage load_house_icons              # apply, skipping houses that already have an icon
    manage load_house_icons --overwrite  # replace existing icons too
    manage load_house_icons --dry-run    # report what would change, touch nothing
"""

from django.core.management.base import BaseCommand

from gyrinx.content.house_icons import attach_house_icons
from gyrinx.content.models import ContentHouse


class Command(BaseCommand):
    help = "Attach bundled SVG house icons to their matching ContentHouse records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace icons on houses that already have one.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        applied, skipped, missing = attach_house_icons(
            ContentHouse,
            overwrite=options["overwrite"],
            dry_run=dry_run,
            log=self.stdout.write,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. applied={applied} skipped={skipped} missing={missing}"
            )
        )
