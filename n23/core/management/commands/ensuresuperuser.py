import os
import sys

import click
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates an admin user non-interactively if it doesn't exist"

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Admin's username")
        parser.add_argument("--email", help="Admin's email")
        parser.add_argument("--password", help="Admin's password")
        parser.add_argument(
            "--no-input", help="Read options from the environment", action="store_true"
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if options["no_input"]:
            options["username"] = os.environ["DJANGO_SUPERUSER_USERNAME"]
            options["email"] = os.environ["DJANGO_SUPERUSER_EMAIL"]
            options["password"] = os.getenv("DJANGO_SUPERUSER_PASSWORD", None)

        click.echo(f"Ensuring superuser: {options['username']}")
        if not User.objects.filter(username=options["username"]).exists():
            click.echo(f"Creating superuser: {options['username']}")
            try:
                User.objects.create_superuser(
                    username=options["username"],
                    email=options["email"],
                    password=options["password"],
                )
            except Exception as e:
                click.echo(f"Error creating superuser: {e}")
                sys.exit(1)

            click.echo(f"Superuser created: {options['username']}")
        else:
            click.echo(f"Superuser already exists: {options['username']}")
