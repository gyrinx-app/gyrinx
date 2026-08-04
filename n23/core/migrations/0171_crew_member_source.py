"""Add ``CrewMember.source``: how a fighter joined the crew.

Schema only. The backfill is 0172 and the removal of the ``was_random`` column
it replaces is 0173 — PostgreSQL refuses to ALTER a table in the same
transaction that has already modified its rows ("pending trigger events"), so
the three steps have to be separate migrations rather than one. That also makes
each step independently reversible.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0170_crew_selection_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="crewmember",
            name="source",
            field=models.CharField(
                choices=[("chosen", "Chosen"), ("random", "Drawn at random")],
                default="chosen",
                help_text="How this fighter joined the crew (audit of the draw).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="historicalcrewmember",
            name="source",
            field=models.CharField(
                choices=[("chosen", "Chosen"), ("random", "Drawn at random")],
                default="chosen",
                help_text="How this fighter joined the crew (audit of the draw).",
                max_length=10,
            ),
        ),
    ]
