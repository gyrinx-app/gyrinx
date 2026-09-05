"""The staged-content flag exists from the start, shut, with its group.

Staff see staged content by right. This flag is how anyone else does: on
the allowlist, whoever is in the group is shown the library as it will
stand once everything staged is live; open to everyone, the whole site is
— a rehearsal of a release, with a way back. Seeded shut rather than left
absent so the switch is a row somebody can find.
"""

from django.db import migrations

# Written out rather than imported: a migration must stay frozen, and the
# slug is read by code that will go on changing. Nothing looks the group up
# by name — which group the allowlist reads is a foreign key chosen on the
# admin page — so renaming it there costs nothing.
SLUG = "staged-content"
GROUP_NAME = "N26 Staged content"


def seed_staged_content_flag(apps, schema_editor):
    FeatureFlag = apps.get_model("gyrinxsite", "FeatureFlag")
    Group = apps.get_model("auth", "Group")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    FeatureFlag.objects.get_or_create(
        slug=SLUG,
        defaults={
            "name": "Staged content",
            "availability": "off",
            "group": group,
            "note": (
                "Seeing content authors have staged but not yet put live, "
                "everywhere a player adds to a gang. Staff always see it. On "
                "the allowlist, whoever is in the group sees it too; open to "
                "everyone, every signed-in player does."
            ),
        },
    )


def drop_staged_content_flag(apps, schema_editor):
    """Undo the seeding, and only the seeding.

    The forward operation accepts a group that was already there, so this
    cannot tell one it made from one it found. Anybody in the group is the
    evidence: a group with members is somebody's, and deleting it would
    take those memberships with it. An empty one is what the forward
    operation leaves behind, and is safe to take away.
    """
    FeatureFlag = apps.get_model("gyrinxsite", "FeatureFlag")
    Group = apps.get_model("auth", "Group")

    FeatureFlag.objects.filter(slug=SLUG).delete()
    for group in Group.objects.filter(name=GROUP_NAME):
        if not group.user_set.exists():
            group.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0090_content_can_be_staged_before_it_is_live"),
        ("gyrinxsite", "0008_the_flags_an_edition_held_move_to_the_site"),
        # Named although the chain may already reach it: this reads the
        # Group model, and a dependency inherited through a parent stops
        # holding the moment that parent is re-parented.
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_staged_content_flag, drop_staged_content_flag),
    ]
