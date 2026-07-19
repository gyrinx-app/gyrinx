"""Split a crew's frozen rating into what was *selected* and what was *played*.

``rating_locked`` named a mechanism; the two snapshots either side of the battle
name moments, so it becomes ``rating_selected`` and is joined by
``rating_played``. Renamed rather than dropped and re-added: the existing values
are exactly the selection-time figures, and the crews that hold them were
genuinely picked at those numbers.

``rating_played`` is deliberately left NULL on existing crews, including ones
whose battle has already ended. There is no way to recover what those fighters
cost at the moment they fought, and back-filling today's figure would invent a
fact; those crews go on computing live, as they did before.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0176_backfill_battle_result"),
    ]

    operations = [
        migrations.RenameField(
            model_name="crew",
            old_name="rating_locked",
            new_name="rating_selected",
        ),
        migrations.RenameField(
            model_name="crewmember",
            old_name="rating_locked",
            new_name="rating_selected",
        ),
        migrations.RenameField(
            model_name="historicalcrew",
            old_name="rating_locked",
            new_name="rating_selected",
        ),
        migrations.RenameField(
            model_name="historicalcrewmember",
            old_name="rating_locked",
            new_name="rating_selected",
        ),
        migrations.AlterField(
            model_name="crew",
            name="rating_selected",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="The crew's rating at the moment it was picked (locked). A record of intent, not what was fielded. Blank on a draft, and on crews locked before snapshotting existed.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="crewmember",
            name="rating_selected",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="This member's contribution to the crew's rating at the moment the crew was picked (locked). Blank until then.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicalcrew",
            name="rating_selected",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="The crew's rating at the moment it was picked (locked). A record of intent, not what was fielded. Blank on a draft, and on crews locked before snapshotting existed.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicalcrewmember",
            name="rating_selected",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="This member's contribution to the crew's rating at the moment the crew was picked (locked). Blank until then.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="crew",
            name="rating_played",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="The crew's rating when the battle ended — what actually fought. Blank until then, and on battles ended before snapshotting existed.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="crewmember",
            name="rating_played",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="This member's contribution to what actually fought, frozen when the battle ended. Blank until then.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalcrew",
            name="rating_played",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="The crew's rating when the battle ended — what actually fought. Blank until then, and on battles ended before snapshotting existed.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalcrewmember",
            name="rating_played",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="This member's contribution to what actually fought, frozen when the battle ended. Blank until then.",
                null=True,
            ),
        ),
    ]
