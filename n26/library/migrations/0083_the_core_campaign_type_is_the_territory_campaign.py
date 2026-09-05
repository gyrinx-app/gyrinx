"""The core campaign type is named for what the rulebook's campaign is
about, and gains a description for the arbitrator founding on it.

A campaign type gets a ``description``: words written for the player
setting a campaign up, as distinct from ``library_author_help``, which
is for content authors and never reaches a player. The set-up screen's
card draws the description.

The type every install has, created under a working name, becomes the
**Territory campaign** — the core rulebook's own campaign, in which gangs
fight for Territory. ``rename_core_campaign`` moves the row across by
name, with its built-ins set, and fills in the description and author
help where the type has none; a type already carrying either keeps its
words. Everything is matched on what stands, so a database that has
already been through this is left as it is.

Reversible for the schema only: the description column goes, and the
rename stands, because a campaign founded on the type names it and a
name is nothing a reverse should take away.
"""

from django.db import migrations, models

from n26.library.core_campaign import rename_core_campaign


def rename(apps, schema_editor):
    for line in rename_core_campaign(apps):
        print(f"[core campaign] {line}")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0082_an_asset_belongs_to_its_kinds_campaign_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaigntype",
            name="description",
            field=models.TextField(
                blank=True,
                default="",
                help_text="What a campaign of this type is about, for the arbitrator setting one up: what the gangs fight over, what each starts with, how the campaign runs and how it ends. Shown on the set-up screen. Use your own words, not the book's.",
            ),
        ),
        migrations.AlterField(
            model_name="assetkind",
            name="mode",
            field=models.CharField(
                choices=[
                    ("held-one-each", "Held one each"),
                    ("pooled", "Changes hands"),
                ],
                help_text="Held one each: every gang is given one when it joins and keeps it. Changes hands: the campaign keeps the copies, and each copy has one holder at a time.",
                max_length=20,
            ),
        ),
        migrations.RunPython(rename, migrations.RunPython.noop),
    ]
