from django.db import migrations

from gyrinx.content.house_icons import attach_house_icons


def apply_icons(apps, schema_editor):
    ContentHouse = apps.get_model("content", "ContentHouse")
    attach_house_icons(ContentHouse)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0169_contentrule_name_unique"),
    ]

    operations = [
        migrations.RunPython(apply_icons, migrations.RunPython.noop),
    ]
