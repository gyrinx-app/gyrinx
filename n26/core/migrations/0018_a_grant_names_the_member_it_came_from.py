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
            name="materialised_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="library.defaultassignment",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="materialised_for",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="n26.assignment",
            ),
        ),
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("archived", False)),
                fields=("materialised_from", "materialised_for"),
                name="assignment_one_live_materialisation",
            ),
        ),
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("materialised_for__isnull", True),
                    ("materialised_from__isnull", True),
                )
                | models.Q(
                    ("materialised_for__isnull", False),
                    ("materialised_from__isnull", False),
                ),
                name="assignment_provenance_is_a_pair",
            ),
        ),
    ]
