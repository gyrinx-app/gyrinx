# Generated by Django 5.1.4 on 2025-01-05 16:38

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0037_remove_contentfighterdefaultassignment_weapon_profiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentfighterdefaultassignment",
            name="weapon_profiles_field",
            field=models.ManyToManyField(blank=True, to="content.contentweaponprofile"),
        ),
    ]
