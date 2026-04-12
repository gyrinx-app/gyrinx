"""Remove the Custom Content group — content pack features are now available to all users."""

from django.db import migrations


def remove_custom_content_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Custom Content").delete()


def recreate_custom_content_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Custom Content")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0140_add_patreon_fields_to_user_profile"),
    ]

    operations = [
        migrations.RunPython(
            remove_custom_content_group,
            recreate_custom_content_group,
        ),
    ]
