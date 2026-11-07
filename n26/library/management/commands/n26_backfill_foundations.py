"""Create missing Foundations content from the command line.

Run each idempotent seed in its own transaction and report its final status.
The Foundations page exposes the same definition sets.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from n26.library.standard_content import STANDARD_CONTENT
from n26.write_pause import write_guard


class Command(BaseCommand):
    help = "Create the n26 standard content: characteristics, Types, subtypes, skills, gang types, the Trading Post."

    def handle(self, *args, **options):
        for item in STANDARD_CONTENT.values():
            with transaction.atomic(), write_guard():
                item.create()
            self.stdout.write(f"{item.key}: {item.status()}")
        self.stdout.write(self.style.SUCCESS("Foundations backfilled."))
