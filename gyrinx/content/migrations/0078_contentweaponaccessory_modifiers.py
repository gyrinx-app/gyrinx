# Generated by Django 5.1.6 on 2025-02-16 14:19

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0077_contentmod_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentweaponaccessory",
            name="modifiers",
            field=models.ManyToManyField(
                blank=True,
                help_text="Modifiers to apply to the weapon's statline and traits.",
                to="content.contentmod",
            ),
        ),
    ]
