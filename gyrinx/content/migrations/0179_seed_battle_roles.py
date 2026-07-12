from django.db import migrations


def seed_battle_roles(apps, schema_editor):
    """Seed the default Attacker/Defender battle role and its options."""
    ContentBattleRole = apps.get_model("content", "ContentBattleRole")
    ContentBattleRoleOption = apps.get_model("content", "ContentBattleRoleOption")

    role, _ = ContentBattleRole.objects.get_or_create(
        name="Attacker/Defender",
        defaults={
            "description": "The standard attacker versus defender roles used by "
            "most scenarios.",
        },
    )
    for option_name in ["Attacker", "Defender"]:
        ContentBattleRoleOption.objects.get_or_create(
            role=role,
            name=option_name,
        )


def unseed_battle_roles(apps, schema_editor):
    ContentBattleRole = apps.get_model("content", "ContentBattleRole")
    ContentBattleRole.objects.filter(name="Attacker/Defender").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0178_battle_roles"),
    ]

    operations = [
        migrations.RunPython(seed_battle_roles, unseed_battle_roles),
    ]
