# Generated by Django 5.1.4 on 2025-01-14 21:50

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0049_contentfighter_primary_skill_categories_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="contentskillcategory",
            options={
                "ordering": ["name"],
                "verbose_name": "Skill Tree",
                "verbose_name_plural": "Skill Trees",
            },
        ),
        migrations.AlterModelOptions(
            name="historicalcontentskillcategory",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "historical Skill Tree",
                "verbose_name_plural": "historical Skill Trees",
            },
        ),
        migrations.AddField(
            model_name="contentskillcategory",
            name="restricted",
            field=models.BooleanField(
                default=False,
                help_text="If checked, this skill tree is only available to specific gangs.",
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentskillcategory",
            name="restricted",
            field=models.BooleanField(
                default=False,
                help_text="If checked, this skill tree is only available to specific gangs.",
            ),
        ),
        migrations.AlterField(
            model_name="contentskill",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="skills",
                to="content.contentskillcategory",
                verbose_name="tree",
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentskill",
            name="category",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="content.contentskillcategory",
                verbose_name="tree",
            ),
        ),
    ]
