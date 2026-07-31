from django.db import migrations

# Frozen snapshot of the generic "Nominate as leader" path (#1468) at the time of this
# migration. Deliberately inlined (not imported from gyrinx.content.models.promotion) so
# this historical migration stays reproducible regardless of how the live
# LEADER_NOMINATION constant evolves — the same pattern as 0181_seed_promotion_paths.
SEED = {
    "name": "Nominate as leader",
    "kind": "TYPE_CHANGE",
    "from_category": "",
    "to_category": "LEADER",
    "dynamic_targets_category": "LEADER",
    "rank": 3,
    "xp_cost": 0,
    "cost_increase": 0,
    "rolls": [],
    "grants_skill": "none",
    "timing": "LEADER_DEATH",
}

_DEFAULT_FIELDS = (
    "name",
    "kind",
    "dynamic_targets_category",
    "rank",
    "xp_cost",
    "cost_increase",
    "rolls",
    "grants_skill",
    "timing",
)


def forwards(apps, schema_editor):
    model = apps.get_model("content", "ContentPromotionPath")
    model.objects.update_or_create(
        from_category=SEED["from_category"],
        to_category=SEED["to_category"],
        defaults={field: SEED[field] for field in _DEFAULT_FIELDS},
    )


def backwards(apps, schema_editor):
    model = apps.get_model("content", "ContentPromotionPath")
    model.objects.filter(
        from_category=SEED["from_category"], to_category=SEED["to_category"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0186_add_dynamic_promotion_targets"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
