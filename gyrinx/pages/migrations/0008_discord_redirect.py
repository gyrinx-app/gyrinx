"""Add /discord/ as a short URL for the community Discord invite.

gyrinx.app/discord is a permanent, shareable address instead of the raw
discord.gg invite. django.contrib.redirects already serves 301s from the
Redirect table — same mechanism as the /help/ moves in 0007 — so this is
a row, not a view.

old_path is /discord/ (trailing slash). /discord without one is handled
by CommonMiddleware APPEND_SLASH: the flatpage catch-all makes /discord/
a valid path, so Django 301s there first, then this row fires.
"""

from django.db import migrations

DISCORD_PATH = "/discord/"
DISCORD_INVITE = "https://discord.gg/WnJFKfyEuj"


def add_discord_redirect(apps, schema_editor):
    Redirect = apps.get_model("redirects", "Redirect")
    Site = apps.get_model("sites", "Site")

    site = Site.objects.first()
    if site is None:
        return

    Redirect.objects.get_or_create(
        site=site, old_path=DISCORD_PATH, defaults={"new_path": DISCORD_INVITE}
    )


def remove_discord_redirect(apps, schema_editor):
    Redirect = apps.get_model("redirects", "Redirect")
    # Only remove the row this migration wrote. If someone has retargeted
    # it in admin, leave their copy.
    Redirect.objects.filter(old_path=DISCORD_PATH, new_path=DISCORD_INVITE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0007_move_n23_help_pages"),
        ("redirects", "0002_alter_redirect_new_path_help_text"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [migrations.RunPython(add_discord_redirect, remove_discord_redirect)]
