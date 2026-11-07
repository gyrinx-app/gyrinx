"""Provision registered task topics, subscriptions and Scheduler jobs.

docker/entrypoint.sh runs this separately from request workers. Skip
execution outside Cloud Run unless --force is passed. Existing resources
are updated to the current route configuration.
"""

import os

from django.core.management.base import BaseCommand

from gyrinx.tasks.provisioning import provision_task_infrastructure


class Command(BaseCommand):
    help = "Provision Pub/Sub topics, subscriptions and Cloud Scheduler jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Provision even outside Cloud Run. Without this the command is a "
                "no-op when K_SERVICE is unset, so it is safe to call "
                "unconditionally from the entrypoint."
            ),
        )

    def handle(self, *args, **options):
        if not options["force"] and not os.getenv("K_SERVICE"):
            self.stdout.write("Not in Cloud Run (K_SERVICE unset) — nothing to do.")
            return

        provision_task_infrastructure()
