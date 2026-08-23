from django.db import migrations

# Kept in sync with the campaigns Flag in n26/core/flags.py. Written out
# here because a migration must stay frozen and may not import application
# code that will go on changing.
GROUP_NAME = "N26 Campaigns"


def create_campaigns_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def remove_campaigns_group(apps, schema_editor):
    """Undo the creation, and only the creation.

    The forward operation accepts a group that was already there, so
    reversing cannot tell one it made from one it found. Anybody in the
    group is the evidence: a group with members is somebody's, and deleting
    it would take those memberships with it. An empty one is what this
    migration leaves behind, and is safe to take away.
    """
    Group = apps.get_model("auth", "Group")
    for group in Group.objects.filter(name=GROUP_NAME):
        if not group.user_set.exists():
            group.delete()


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
