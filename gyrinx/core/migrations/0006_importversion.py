# Generated by Django 5.1.2 on 2024-10-20 17:35

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportVersion",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("uuid", models.UUIDField(db_index=True, editable=False)),
                ("version", models.CharField(db_index=True, max_length=255)),
                (
                    "ruleset",
                    models.CharField(default="necromunda-2018", max_length=255),
                ),
                ("directory", models.CharField(max_length=255)),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
