"""Back-link the weapon-profile members that already exist.

A live profile member whose set brings exactly one live matching weapon
member takes that member as its gun. Anything else stays null — the
member rides whatever matching weapon the acquirer holds, which is the
meaning null keeps. Zero matches is the cross-set shape; several
matches cannot say which gun was meant, and null preserves exactly the
standing behaviour until an author anchors it in the UI.
"""

from django.db import migrations


def link_profile_members(apps, schema_editor):
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    profile_members = DefaultAssignment.objects.filter(
        weapon_profile__isnull=False,
        gun_member__isnull=True,
        archived=False,
    ).select_related("weapon_profile")
    for member in profile_members:
        matches = list(
            DefaultAssignment.objects.filter(
                default_set_id=member.default_set_id,
                archived=False,
                weapon_id=member.weapon_profile.weapon_id,
            )
        )
        if len(matches) != 1:
            continue
        member.gun_member = matches[0]
        member.save(update_fields=["gun_member"])


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0065_an_extra_profile_names_its_gun_member"),
    ]

    operations = [
        migrations.RunPython(link_profile_members, migrations.RunPython.noop),
    ]
