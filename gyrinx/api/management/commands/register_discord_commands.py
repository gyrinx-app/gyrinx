"""
Register Discord application commands.

Creates the "Create Issue" message context menu command that allows users
to right-click a message and file a GitHub issue from it.

Usage:
    manage register_discord_commands

Requires DISCORD_BOT_TOKEN and DISCORD_APPLICATION_ID in settings.
"""

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register Discord application commands (message context menu)"

    def handle(self, *args, **options):
        if not settings.DISCORD_BOT_TOKEN:
            raise CommandError("DISCORD_BOT_TOKEN is not configured")
        if not settings.DISCORD_APPLICATION_ID:
            raise CommandError("DISCORD_APPLICATION_ID is not configured")

        app_id = settings.DISCORD_APPLICATION_ID
        url = f"https://discord.com/api/v10/applications/{app_id}/commands"

        # Register "Create Issue" message context menu command
        # type 3 = MESSAGE command (context menu on messages)
        command_data = {
            "name": "Create Issue",
            "type": 3,
        }

        response = requests.put(
            url,
            headers={
                "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
                "Content-Type": "application/json",
            },
            json=[command_data],
            timeout=30,
        )

        if response.status_code == 200:
            commands = response.json()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Registered {len(commands)} command(s) successfully:"
                )
            )
            for cmd in commands:
                self.stdout.write(
                    f"  - {cmd['name']} (id: {cmd['id']}, type: {cmd['type']})"
                )
        else:
            raise CommandError(
                f"Failed to register commands: {response.status_code} {response.text}"
            )
