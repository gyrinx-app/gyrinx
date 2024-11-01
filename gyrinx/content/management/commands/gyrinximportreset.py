import click
from django.core.management.base import BaseCommand

from ...models import ContentImportVersion


class Command(BaseCommand):
    help = "Reset the content database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without making any changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        models = [
            # We only need to delete the ContentImportVersion records
            # because the other records are deleted automatically by
            # the ContentImportVersion delete cascade.
            (ContentImportVersion, "ContentImportVersion"),
        ]

        for model, name in models:
            count = model.objects.count()
            click.echo(f"Found {count} {name} records...")
            if not dry_run:
                model.objects.all().delete()
                click.echo(f"{count} {name} records deleted.")
            else:
                click.echo(f"Dry run: {count} {name} records would be deleted.")
