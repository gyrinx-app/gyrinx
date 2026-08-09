import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """A weapon-targeting scope may narrow to one category of weapon.

    "An AP improvement on all Las weapons" is the category alone, where
    before a scope could only name a trait. The column is nullable and
    every scope already written leaves it blank, so each one keeps
    reaching exactly the weapons it reached.
    """

    dependencies = [
        ("library", "0028_gang_type_foundable"),
    ]

    operations = [
        migrations.AddField(
            model_name="targetsweapons",
            name="with_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="library.category",
                help_text=(
                    'Only weapons homed in this category — the "Las Weapons" '
                    'in "an AP improvement on all Las weapons". Blank means '
                    "all of them."
                ),
            ),
        ),
    ]
