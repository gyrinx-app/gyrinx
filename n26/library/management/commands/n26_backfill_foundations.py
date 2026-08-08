"""Backfill the n26 foundations from the command line.

The Foundations page offers the same seeds as buttons; this is the ops
path — run after migrating a fresh environment, or any time, because
every seed is idempotent: rows are matched on their natural keys and
topped up, never duplicated.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from n26.library.standard_content import STANDARD_CONTENT


class Command(BaseCommand):
    help = "Create the n26 standard content: characteristics, Types, subtypes, skills, gang types, the Trading Post."

    def handle(self, *args, **options):
        for item in STANDARD_CONTENT.values():
            with transaction.atomic():
                item.create()
            self.stdout.write(f"{item.key}: {item.status()}")
        self.stdout.write(self.style.SUCCESS("Foundations backfilled."))
