"""The notes toggle covers pictures and writing space too.

``include_notes`` used to mean a notes card per model. It now means the
footer strip on each model card: the notes themselves, a box to write
in during a game, and the picture if there is one. The gang's notes
still print as their own card.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0062_credits_move_between_gangs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="printconfig",
            name="include_notes",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Print the gang's notes, and on each model card its notes, "
                    "picture, and space to write during a game."
                ),
            ),
        ),
    ]
