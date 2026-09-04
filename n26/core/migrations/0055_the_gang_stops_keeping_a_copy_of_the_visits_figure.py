"""The gang stops keeping a copy of what its open visit brought.

The figure lives on the Visit Trading Post action row, and every screen
reads it there. This drops the column beside it.

Destructive, so it ships in a deploy of its own: the revision going out
must already have stopped reading the column, or it serves errors for
the seconds the two overlap.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0050_a_purchase_records_who_spent_the_trade_points"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="gang",
            name="starting_trade_points",
        ),
    ]
