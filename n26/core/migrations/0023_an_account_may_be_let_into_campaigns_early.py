from django.db import migrations

# Kept in sync with the campaigns Flag in n26/core/flags.py. Written out
# here because a migration must stay frozen and may not import application
# code that will go on changing.
GROUP_NAME = "N26 Campaigns"


def create_campaigns_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def remove_campaigns_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0022_a_removal_carries_no_provenance"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            create_campaigns_group,
            remove_campaigns_group,
        ),
    ]
