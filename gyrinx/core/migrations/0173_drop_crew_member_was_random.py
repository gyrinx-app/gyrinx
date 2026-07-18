"""Drop ``CrewMember.was_random``, now that ``source`` (0171/0172) carries it.

Separate from the backfill because PostgreSQL will not ALTER a table in a
transaction that has already modified its rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0172_backfill_crew_member_source"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="crewmember",
            name="was_random",
        ),
        migrations.RemoveField(
            model_name="historicalcrewmember",
            name="was_random",
        ),
        migrations.AlterField(
            model_name="crew",
            name="chosen_fighters",
            field=models.ManyToManyField(
                blank=True,
                help_text="Deprecated: superseded by CrewMember rows.",
                related_name="chosen_in_crews",
                to="core.listfighter",
            ),
        ),
    ]
