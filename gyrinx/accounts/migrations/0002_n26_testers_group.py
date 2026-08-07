# The rollout gate for the n26 edition: membership of this group (or staff)
# is what opens every /n26/ page — see gyrinx.middleware.N26TestersGateMiddleware.
# A data migration rather than a fixture so every environment gets the group
# the moment it deploys, with nothing to remember to click.

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
