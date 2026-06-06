from django.db import migrations

from gyrinx.content.house_icons import attach_custom_gang_icon


def apply_icon(apps, schema_editor):
    ContentHouse = apps.get_model("content", "ContentHouse")
    CustomContentPackItem = apps.get_model("core", "CustomContentPackItem")
    attach_custom_gang_icon(ContentHouse, CustomContentPackItem)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0170_attach_house_icons"),
        ("core", "0126_add_custom_content_pack_models"),
    ]

    operations = [
        migrations.RunPython(apply_icon, migrations.RunPython.noop),
    ]
