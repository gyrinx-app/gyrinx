from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0021_a_grant_names_the_member_it_came_from"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.CheckConstraint(
                condition=models.Q(("removes", False))
                | models.Q(("materialised_from__isnull", True)),
                name="assignment_removal_carries_no_provenance",
            ),
        ),
    ]
