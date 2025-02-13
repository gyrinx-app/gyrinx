# Generated by Django 5.1.4 on 2025-01-14 21:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0050_alter_contentskillcategory_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contentfighter",
            name="primary_skill_categories",
            field=models.ManyToManyField(
                blank=True,
                related_name="primary_fighters",
                to="content.contentskillcategory",
                verbose_name="Primary Skill Trees",
            ),
        ),
        migrations.AlterField(
            model_name="contentfighter",
            name="secondary_skill_categories",
            field=models.ManyToManyField(
                blank=True,
                related_name="secondary_fighters",
                to="content.contentskillcategory",
                verbose_name="Secondary Skill Trees",
            ),
        ),
    ]
