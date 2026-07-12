from django.db import migrations

from gyrinx.content.house_icons import attach_custom_gang_icon, attach_house_icons


def refresh_icons(apps, schema_editor):
    """Re-copy the bundled SVGs onto every house, replacing the stored copies.

    The source SVGs were re-exported as merged single-path shapes (the
    per-pixel <rect> versions left anti-alias hairlines). Houses already carry
    the old copies on ``ContentHouse.icon``, so ``overwrite=True`` is required —
    the default skips any house that already has an icon, making this a no-op.
    """
    ContentHouse = apps.get_model("content", "ContentHouse")
    CustomContentPackItem = apps.get_model("core", "CustomContentPackItem")
    attach_house_icons(ContentHouse, overwrite=True)
    attach_custom_gang_icon(ContentHouse, CustomContentPackItem, overwrite=True)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0171_attach_custom_gang_icon"),
        ("core", "0126_add_custom_content_pack_models"),
    ]

    operations = [
        migrations.RunPython(refresh_icons, migrations.RunPython.noop),
    ]
