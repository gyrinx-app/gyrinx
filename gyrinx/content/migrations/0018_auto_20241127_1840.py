from pathlib import Path

import yaml
from django.db import migrations

from gyrinx.content.models import ContentHouse as ContentHouseModel


def do_migration(apps, schema_editor):
    ContentHouse: type[ContentHouseModel] = apps.get_model("content", "ContentHouse")

    # Resolve the content folder relative to this file
    root = Path(__file__).parent / "../../../content/necromunda-2018/data"
    houses = root / "house.yaml"

    with open(houses, "r") as file:
        data = yaml.safe_load(file)
        houses = data["house"]
        for h in houses:
            house, created = ContentHouse.objects.get_or_create(**h)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0017_alter_contentweaponprofile_cost_sign_and_more"),
    ]

    operations = [migrations.RunPython(do_migration, elidable=True)]
