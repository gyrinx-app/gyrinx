from django.db import migrations

# Written out rather than imported: a migration must stay frozen, and the
# slug and group name it seeds will go on being read by code that changes.
SLUG = "campaigns"
GROUP_NAME = "N26 Campaigns"


def seed_campaigns_flag(apps, schema_editor):
    """The row exists from the start, shut, with its group already attached.

    Seeding it off rather than leaving it absent is the difference between a
    switch somebody can find and a page they have to know to create. Both
    keep the feature closed; only one of them is discoverable.
    """
    FeatureFlag = apps.get_model("n26", "FeatureFlag")
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


def drop_campaigns_flag(apps, schema_editor):
    FeatureFlag = apps.get_model("n26", "FeatureFlag")
    FeatureFlag.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0023_a_feature_may_be_opened_from_the_admin"),
    ]

    operations = [
        migrations.RunPython(seed_campaigns_flag, drop_campaigns_flag),
    ]
