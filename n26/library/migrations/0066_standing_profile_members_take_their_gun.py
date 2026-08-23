"""Back-link the weapon-profile members that already exist.

A live profile member whose set brings exactly one live matching weapon
member takes that member as its gun. Zero matches stays null — the
member rides whatever matching weapon the acquirer holds, which is the
cross-set meaning null keeps. More than one match is refused outright:
nothing can say which gun was meant, and an anchor guessed here would
quietly rehome ammo, so the migration stops and the author anchors it
by hand first.
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
        if not matches:
            continue
        if len(matches) > 1:
            raise RuntimeError(
                f"Default set {member.default_set_id} brings the weapon of "
                f"profile member {member.pk} {len(matches)} times — no "
                f"anchor can be derived. Set gun_member on that member by "
                f"hand, then migrate again."
            )
        member.gun_member = matches[0]
        member.save(update_fields=["gun_member"])


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0065_an_extra_profile_names_its_gun_member"),
    ]

    operations = [
        migrations.RunPython(link_profile_members, migrations.RunPython.noop),
    ]
