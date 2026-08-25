from django.db import migrations

# The slug and the group name are written out rather than imported: a
# migration must stay frozen, while the code these came from goes on
# changing. Both are only needed to find rows already written.
SLUG = "campaigns"
GROUP_NAME = "N26 Campaigns"


def carry_flags_over(apps, schema_editor):
    """Bring across whatever the edition's own table already held.

    The edition shipped this feature's flag before the table moved, so a
    database that has run those migrations holds a row somebody may already
    have set — and losing it would silently shut a feature that was open, or
    open one that was shut. Rows are matched by slug, which is what code asks
    for and what makes two rows the same flag.

    A database that never had the edition's table simply has nothing to
    carry, and the seed below covers it.
    """
    Old = apps.get_model("n26", "FeatureFlag")
    New = apps.get_model("gyrinxsite", "FeatureFlag")

    for old in Old.objects.all():
        New.objects.update_or_create(
            slug=old.slug,
            defaults={
                "name": old.name,
                "availability": old.availability,
                "group_id": old.group_id,
                "note": old.note,
            },
        )


def seed_campaigns_flag(apps, schema_editor):
    """The row exists from the start, shut, with its group attached.

    Seeding it off rather than leaving it absent is the difference between a
    switch somebody can find and a page they have to know to create. Both
    keep the feature closed; only one of them is discoverable.
    """
    FeatureFlag = apps.get_model("gyrinxsite", "FeatureFlag")
    Group = apps.get_model("auth", "Group")

    FeatureFlag.objects.get_or_create(
        slug=SLUG,
        defaults={
            "name": "Campaigns",
            "availability": "off",
            "group": Group.objects.filter(name=GROUP_NAME).first(),
            "note": (
                "Running a campaign: the campaign itself, who is in it, and "
                "what it owns. Off shuts it for everyone; on the allowlist, "
                "whoever is in the group gets it."
            ),
        },
    )


def drop_carried_flags(apps, schema_editor):
    """Reversing drops what this migration wrote, leaving the edition's own
    table — which the next migration back restores — to hold the answer."""
    FeatureFlag = apps.get_model("gyrinxsite", "FeatureFlag")
    FeatureFlag.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gyrinxsite", "0007_feature_flags_belong_to_the_site"),
        # The edition's table has to still exist to be read from, so this
        # runs before the migration that drops it.
        ("n26", "0026_a_flag_may_only_hold_a_word_that_can_be_read"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(carry_flags_over, drop_carried_flags),
        migrations.RunPython(seed_campaigns_flag, migrations.RunPython.noop),
    ]
