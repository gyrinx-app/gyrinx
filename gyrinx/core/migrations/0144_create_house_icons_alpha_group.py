from django.db import migrations

# Kept in sync with HOUSE_ICONS_ALPHA_GROUP in
# gyrinx/core/templatetags/color_tags.py. Hardcoded here because migrations
# must stay frozen and not import application code.
GROUP_NAME = "House Icons Alpha"


def create_house_icons_alpha_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def remove_house_icons_alpha_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0143_campaign_content_pack_through"),
    ]

    operations = [
        migrations.RunPython(
            create_house_icons_alpha_group,
            remove_house_icons_alpha_group,
        ),
    ]
