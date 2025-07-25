# Generated by Django 5.2.4 on 2025-07-18 09:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0121_alter_contentfighter_category_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentfighter",
            name="hide_house_restricted_gear",
            field=models.BooleanField(
                default=False,
                help_text="If checked, house restricted gear section will not be displayed on fighter card.",
            ),
        ),
        migrations.AddField(
            model_name="contentfighter",
            name="hide_skills",
            field=models.BooleanField(
                default=False,
                help_text="If checked, skills section will not be displayed on fighter card.",
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentfighter",
            name="hide_house_restricted_gear",
            field=models.BooleanField(
                default=False,
                help_text="If checked, house restricted gear section will not be displayed on fighter card.",
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentfighter",
            name="hide_skills",
            field=models.BooleanField(
                default=False,
                help_text="If checked, skills section will not be displayed on fighter card.",
            ),
        ),
    ]
