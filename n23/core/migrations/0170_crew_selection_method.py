"""Store a crew's selection method instead of deriving it.

The method used to be inferred from whether a crew had picks and/or a random
spec, which made "pure Random" and "Hybrid" indistinguishable. It becomes an
explicit field, backfilled so that no existing crew changes meaning: the
derivation that ``Crew.method_label()`` used to do is applied once, here.
"""

import n23.core.models.crew
from django.db import migrations, models


def derive_selection_method(apps, schema_editor):
    """Mirror the old derived ``method_label()`` logic exactly.

    picks + spec -> Hybrid; spec only -> Random; picks only -> Custom (N);
    neither -> Custom with no number (the whole gang may take part).
    """
    Crew = apps.get_model("core", "Crew")
    for crew in Crew.objects.all().iterator():
        chosen = crew.chosen_fighters.count()
        has_random = bool((crew.random_spec or "").strip())
        if chosen and has_random:
            crew.selection_method = "hybrid"
            crew.custom_count = chosen
        elif has_random:
            crew.selection_method = "random"
            crew.custom_count = None
        else:
            crew.selection_method = "custom"
            crew.custom_count = chosen or None
        crew.save(update_fields=["selection_method", "custom_count"])


def noop(apps, schema_editor):
    """No-op: the columns are dropped by the reverse of the AddFields above, so
    there is nothing to unwind. The recipe itself (``chosen_fighters`` and
    ``random_spec``) is untouched by the forward pass, and the old code derives
    the method from those again."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0169_battle_result"),
    ]

    operations = [
        migrations.AddField(
            model_name="crew",
            name="custom_count",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="How many fighters the player chooses — the number in brackets. Blank on Custom Selection means no number is shown: the whole gang may take part.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="crew",
            name="selection_method",
            field=models.CharField(
                choices=[
                    ("custom", "Custom Selection"),
                    ("random", "Random Selection"),
                    ("hybrid", "Hybrid Selection"),
                ],
                default="custom",
                help_text="The scenario's crew selection method.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="historicalcrew",
            name="custom_count",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="How many fighters the player chooses — the number in brackets. Blank on Custom Selection means no number is shown: the whole gang may take part.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalcrew",
            name="selection_method",
            field=models.CharField(
                choices=[
                    ("custom", "Custom Selection"),
                    ("random", "Random Selection"),
                    ("hybrid", "Hybrid Selection"),
                ],
                default="custom",
                help_text="The scenario's crew selection method.",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="crew",
            name="random_spec",
            field=models.CharField(
                blank=True,
                default="",
                help_text="How many fighters are drawn at random at battle start — the Y of Random and Hybrid Selection. A number (6), a die (D3), or die + number (D3+4).",
                max_length=20,
                validators=[n23.core.models.crew.validate_selection_spec],
            ),
        ),
        migrations.AlterField(
            model_name="historicalcrew",
            name="random_spec",
            field=models.CharField(
                blank=True,
                default="",
                help_text="How many fighters are drawn at random at battle start — the Y of Random and Hybrid Selection. A number (6), a die (D3), or die + number (D3+4).",
                max_length=20,
                validators=[n23.core.models.crew.validate_selection_spec],
            ),
        ),
        # Existing history rows keep the field defaults (custom / no number):
        # they are an audit trail of past edits, not live recipes.
        migrations.RunPython(derive_selection_method, noop),
    ]
