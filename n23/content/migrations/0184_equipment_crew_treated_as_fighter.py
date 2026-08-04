from django.db import migrations, models

HELP_TEXT = (
    "When this equipment sits in a gang's stash, the fighter card it brings is "
    "treated as one of the gang's fighters when a crew is picked: it appears on "
    "the crew's eligibility and selection screens like any other fighter, rather "
    "than as a stash item (e.g. the Iron Automaton, which is effectively part of "
    "the gang once owned). Only meaningful for equipment that has a linked "
    "fighter."
)


class Migration(migrations.Migration):
    """Rename the crew stash flag now that it means "treated as a fighter".

    Hand-written as a RenameField rather than the auto-generated drop-and-add so
    equipment already flagged in production keeps its value.
    """

    dependencies = [
        ("content", "0183_equipment_crew_always_brought"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contentequipment",
            old_name="crew_always_brought",
            new_name="crew_treated_as_fighter",
        ),
        migrations.RenameField(
            model_name="historicalcontentequipment",
            old_name="crew_always_brought",
            new_name="crew_treated_as_fighter",
        ),
        migrations.AlterField(
            model_name="contentequipment",
            name="crew_treated_as_fighter",
            field=models.BooleanField(
                default=False,
                help_text=HELP_TEXT,
                verbose_name="Treated as a fighter for crews",
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentequipment",
            name="crew_treated_as_fighter",
            field=models.BooleanField(
                default=False,
                help_text=HELP_TEXT,
                verbose_name="Treated as a fighter for crews",
            ),
        ),
    ]
