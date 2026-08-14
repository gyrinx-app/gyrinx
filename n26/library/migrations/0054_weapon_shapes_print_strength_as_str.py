# Every shape a weapon is drawn to heads its Strength column "Str",
# the way the weapon tables print it. Only shapes some weapon actually
# uses are touched: a model's shape shares the same Strength row and
# goes on printing "S".

from django.db import migrations

#: What a weapon's Strength column is headed.
WEAPON_STRENGTH = "Str"

#: The abbreviation the shared Strength definition carries, which is
#: the model's.
MODEL_STRENGTH = "S"


def name_it_str(apps, schema_editor):
    _set_override(apps, WEAPON_STRENGTH)


def name_it_after_the_stat(apps, schema_editor):
    _set_override(apps, "")


def _set_override(apps, override):
    StatlineTypeStat = apps.get_model("library", "StatlineTypeStat")
    StatlineTypeStat.objects.filter(
        stat__short_name=MODEL_STRENGTH, statline_type__weapons__isnull=False
    ).update(short_name_override=override)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0053_a_shape_may_head_a_column_its_own_way"),
    ]

    operations = [
        migrations.RunPython(name_it_str, name_it_after_the_stat),
    ]
