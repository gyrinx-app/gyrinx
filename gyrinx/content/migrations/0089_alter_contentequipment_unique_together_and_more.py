# Generated by Django 5.2 on 2025-04-13 13:48

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0088_alter_contentequipment_unique_together"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="contentequipment",
            unique_together={("name", "category_obj")},
        ),
        migrations.RemoveField(
            model_name="historicalcontentequipment",
            name="category",
        ),
        migrations.RemoveField(
            model_name="contentequipment",
            name="category",
        ),
    ]
