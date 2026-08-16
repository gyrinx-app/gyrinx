"""Ledger events may stand alone, and every one is pinned to its gang.

An event gains three things: a nullable assignment (journal-only acts —
a rename, a note, a characteristic set by hand — have no assignment to
be about), a model to be about instead, and a gang set on every event so
a gang's whole history is one indexed query. Existing events are all
about assignments, so their gang is copied from the assignment's pinned
root.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def pin_gangs(apps, schema_editor):
    """Every existing event is about an assignment; its gang is the
    assignment's pinned root."""
    LedgerEvent = apps.get_model("n26", "LedgerEvent")
    Assignment = apps.get_model("n26", "Assignment")
    LedgerEvent.objects.update(
        gang_id=models.Subquery(
            Assignment.objects.filter(pk=models.OuterRef("assignment_id")).values(
                "gang_root_id"
            )[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0012_a_pick_names_the_slot_it_settles"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="ledgerevent",
            name="assignment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ledger_events",
                to="n26.assignment",
            ),
        ),
        migrations.AlterField(
            model_name="ledgerevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("purchased", "Purchased"),
                    ("added", "Added"),
                    ("granted", "Granted"),
                    ("moved", "Moved"),
                    ("tallied", "Tallied"),
                    ("amended", "Amended"),
                    ("repriced", "Repriced"),
                    ("removed", "Removed"),
                    ("refunded", "Refunded"),
                    ("sold", "Sold"),
                    ("renamed", "Renamed"),
                    ("noted", "Notes edited"),
                    ("stat_set", "Characteristic set"),
                    ("stat_cleared", "Characteristic cleared"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="ledgerevent",
            name="miniature",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ledger_events",
                to="n26.miniature",
            ),
        ),
        migrations.AddField(
            model_name="ledgerevent",
            name="gang",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ledger_events",
                to="n26.gang",
            ),
        ),
        migrations.RunPython(pin_gangs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ledgerevent",
            name="gang",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ledger_events",
                to="n26.gang",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("assignment__isnull", True))
                | models.Q(("miniature__isnull", True)),
                name="ledger_event_about_at_most_one",
            ),
        ),
    ]
