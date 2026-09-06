"""A grant of a slot may carry the pick the slot arrives settled on.

``AddsAssignable.with_pick`` is the grant-side twin of
``DefaultAssignment.default_pickable``: "gives this slot, already
settled on this pick". The pick is dealt onto the card beside the slot
and goes the moment the slot does. It is how one gang-level choice
settles another — a Clan House pick on an Outcast gang gives the hidden
Gang supertype slot with that House already picked, so the gang counts
as a gang of that House wherever a rule asks.

The constraint says what the database can: a pick needs a slot beside
it. That the pick belongs to the slot's type, and that the slot is
hidden, only the row knows, and ``clean()`` says.

Reversible: the column and the constraint go.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0093_a_stat_has_a_minimum_and_a_maximum"),
    ]

    operations = [
        migrations.AddField(
            model_name="addsassignable",
            name="with_pick",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The pick a granted slot arrives settled on. Only for a "
                    "hidden slot; leave blank for anything else."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="library.pickable",
                verbose_name="pick given with the slot",
            ),
        ),
        migrations.AddConstraint(
            model_name="addsassignable",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("with_pick__isnull", True),
                    ("slot__isnull", False),
                    _connector="OR",
                ),
                name="adds_assignable_pick_belongs_to_a_slot",
            ),
        ),
    ]
