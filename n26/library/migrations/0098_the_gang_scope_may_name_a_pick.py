"""The gang scope may name a pick.

``GangHasPickable`` is a condition row hanging off ``TargetsGang``, the
gang-scope twin of ``HasPickable`` on the model scope: "gangs that have
picked Goliath". Read against the gang's own facts — its assignments and
the picks it was given — so a boon for Goliath gangs reaches a
Goliath gang and a Clan House Goliath Outcast gang alike. A scope with
no rows behaves as before.

Reversible: the table goes.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0097_a_grant_may_carry_its_pick"),
    ]

    operations = [
        migrations.CreateModel(
            name="GangHasPickable",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "negate",
                    models.BooleanField(
                        default=False,
                        help_text="Reach everything this does not name — every gang except these. Other conditions still narrow it further.",
                    ),
                ),
                (
                    "pickables",
                    models.ManyToManyField(
                        help_text="The gang must have picked at least one of these.",
                        related_name="+",
                        to="library.pickable",
                    ),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="has_gang_pickable",
                        to="library.targetsgang",
                    ),
                ),
            ],
            options={
                "verbose_name": "gang has pickable",
                "verbose_name_plural": "gang has pickable",
            },
        ),
    ]
