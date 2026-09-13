import os
from urllib.parse import urlencode

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from gyrinx.debug_login import ensure_debug_agent_user


class Command(BaseCommand):
    help = "Create a local agent user and print its one-click debug login URL"

    def add_arguments(self, parser):
        parser.add_argument(
            "target",
            nargs="?",
            default="/",
            help="Local path to open after login (default: /)",
        )
        parser.add_argument(
            "--username",
            default="agent",
            help="Dedicated user: agent or agent-<purpose> (default: agent)",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Agent login URLs are only available with DEBUG enabled")

        target = options["target"]
        if not target.startswith("/") or target.startswith("//"):
            raise CommandError("Target must be a local absolute path beginning with /")

        try:
            user = ensure_debug_agent_user(options["username"])
        except ValueError as error:
            raise CommandError(str(error)) from error

        port = os.environ.get("DJANGO_PORT", "8000")
        query = urlencode({"user": user.username, "next": target})
        self.stdout.write(
            f"http://localhost:{port}{reverse('debug_agent_login')}?{query}"
        )
