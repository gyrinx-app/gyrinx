# A group planted by data migration rather than by a fixture, so every
# environment has it the moment it deploys, with nothing to remember to click.
# Nothing in the app reads it: who may see the n26 edition is decided by each
# view's own guard.

from django.db import migrations

GROUP_NAME = "N26 Testers"


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_move_userprofile_to_accounts"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
