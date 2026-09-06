"""A pick may add to its holder's rating.

A pick is never paid for — no credits move, nothing is refunded or sold —
but a rolled result can still raise a model's value: a Spyrer's Power
Boost adds the amount the table prints. The pickable now says what it
adds, and the pick is written with that as its rating contribution and
nothing paid. Every existing pickable adds 0, so no gang's rating moves.

Reversible: the field goes, and the values with it.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0093_a_stat_has_a_minimum_and_a_maximum"),
    ]

    operations = [
        migrations.AddField(
            model_name="pickable",
            name="rating_contribution",
            field=models.IntegerField(
                default=0,
                help_text="Credits this pick adds to the model's rating. A pick is never paid for, so this is a rating, not a price. Leave at 0 unless the rules raise the model's value, as a Spyrer's Power Boost does.",
            ),
        ),
    ]
