# Generated by Django 5.2.2 on 2025-06-08 09:26

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0057_add_unique_constraint_fighter_injury"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicallistfighter",
            name="injury_state",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("recovery", "Recovery"),
                    ("convalescence", "Convalescence"),
                    ("dead", "Dead"),
                ],
                default="active",
                help_text="The current injury state of the fighter in campaign mode.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="listfighter",
            name="injury_state",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("recovery", "Recovery"),
                    ("convalescence", "Convalescence"),
                    ("dead", "Dead"),
                ],
                default="active",
                help_text="The current injury state of the fighter in campaign mode.",
                max_length=20,
            ),
        ),
    ]
