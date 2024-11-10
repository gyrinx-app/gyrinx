import os
from pathlib import Path

import click
from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key
from dotenv import get_key, set_key


class Command(BaseCommand):
    help = "Set up the .env file for the project."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        # Create the .env file if it doesn't exist
        env_file = Path(os.getcwd()).resolve() / ".env"
        click.echo(f".env: {env_file}")
        if not env_file.exists():
            if options["dry_run"]:
                click.echo("Would create .env file")
            else:
                click.echo("Creating .env file")
                env_file.touch()

        # Create a secret key
        if get_key(env_file, "SECRET_KEY"):
            click.echo("SECRET_KEY already set")
        else:
            if options["dry_run"]:
                click.echo("Would set SECRET_KEY")
            else:
                click.echo("Setting SECRET_KEY")
                set_key(
                    str(env_file),
                    "SECRET_KEY",
                    get_random_secret_key(),
                )

        # Create a super user password
        if get_key(env_file, "DJANGO_SUPERUSER_PASSWORD"):
            click.echo("DJANGO_SUPERUSER_PASSWORD already set")
        else:
            if options["dry_run"]:
                click.echo("Would set DJANGO_SUPERUSER_PASSWORD")
            else:
                click.echo("Setting DJANGO_SUPERUSER_PASSWORD")
                set_key(
                    str(env_file),
                    "DJANGO_SUPERUSER_PASSWORD",
                    get_random_secret_key(),
                )
