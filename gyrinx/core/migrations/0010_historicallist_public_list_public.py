# Generated by Django 5.1.4 on 2024-12-31 13:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_alter_historicallist_archived_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicallist",
            name="public",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="list",
            name="public",
            field=models.BooleanField(default=True),
        ),
    ]
