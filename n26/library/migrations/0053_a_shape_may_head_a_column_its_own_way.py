# One stat definition is shared across statline shapes, so the
# abbreviation a column is headed with belongs to the placement rather
# than to the stat: a weapon table prints Strength as Str where a model
# prints S.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0052_choice_words_in_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="statlinetypestat",
            name="short_name_override",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Prints instead of the stat's own short name, on this shape only. Blank means the stat's own — a weapon shape prints Strength as Str where a model prints S.",
                max_length=10,
            ),
        ),
    ]
