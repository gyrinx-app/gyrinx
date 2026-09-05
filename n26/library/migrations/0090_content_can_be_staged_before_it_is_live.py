"""Every content row can be staged: written, but not yet put live.

Staged rows are held back from every surface where a player adds to a gang
and shown there to authors, so new content can be checked as players will
meet it before players do (``n26.library.staged``). The column lives on the
abstract ``Content`` base, so it lands on every table here at once.

Adding a column with a constant default is a catalogue change in Postgres,
so this rewrites no table however large the library has grown.
"""

from django.db import migrations, models

#: Every concrete kind built on ``Content`` when this migration was written.
#: A kind added later gets the column from its own creating migration.
KINDS = [
    "affiliation",
    "asset",
    "assettype",
    "campaigntype",
    "category",
    "collection",
    "collectionentry",
    "collectionsection",
    "collectionselector",
    "counter",
    "defaultassignment",
    "defaultassignmentset",
    "gangtype",
    "hidden",
    "modifier",
    "option",
    "optiongroup",
    "pickable",
    "picklist",
    "picklistmember",
    "power",
    "profile",
    "profiletype",
    "rule",
    "section",
    "skill",
    "slot",
    "slottype",
    "stat",
    "statline",
    "statlinestat",
    "statlinetype",
    "statlinetypestat",
    "subtype",
    "trait",
    "wargear",
    "weapon",
    "weaponaccessory",
    "weaponprofile",
]

HELP = (
    "Held back from players until an author puts it live. Not offered where "
    "players add to a gang: creating a gang, hiring, equipment lists, the "
    "Trading Post, skills and choices. Anything a gang already holds stays "
    "as it is."
)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0088_possession_help_drops_and_keeps_it"),
    ]

    operations = [
        migrations.AddField(
            model_name=kind,
            name="staged",
            field=models.BooleanField(default=False, help_text=HELP),
        )
        for kind in KINDS
    ]
