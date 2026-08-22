import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0064_sheets_are_held_between_upload_and_import"),
        ("n26", "0017_the_budget_is_part_of_the_story"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="materialised_for",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="materialised_defaults",
                to="n26.assignment",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="materialised_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="materialisations",
                to="library.defaultassignment",
            ),
        ),
    ]
