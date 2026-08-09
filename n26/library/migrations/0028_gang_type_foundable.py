from django.db import migrations, models


class Migration(migrations.Migration):
    """A gang type says whether a player may found a gang of it.

    Every type already written stays foundable — the column defaults to true,
    so the create-a-gang screen offers exactly what it offered before and an
    author has to turn a type off deliberately.
    """

    dependencies = [
        ("library", "0027_choice_labels_read_as_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="gangtype",
            name="foundable",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Whether a player may create a gang of this type. Turn it "
                    "off for a type that exists to be hired from or fought "
                    "against rather than played, and it stops being offered "
                    "when someone creates a gang. Gangs that are already this "
                    "type are unaffected."
                ),
            ),
        ),
    ]
