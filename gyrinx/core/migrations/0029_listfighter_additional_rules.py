# Generated by Django 5.1.5 on 2025-02-11 20:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0072_alter_contenthouse_house_additional_rules_name_and_more"),
        ("core", "0028_historicallistfighterequipmentassignment_upgrade_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="listfighter",
            name="additional_rules",
            field=models.ManyToManyField(
                blank=True,
                help_text="Additional rules for this fighter. Must be from the same house as the fighter.",
                limit_choices_to={"tree__house": models.F("list__content_house")},
                to="content.contenthouseadditionalrule",
            ),
        ),
    ]
