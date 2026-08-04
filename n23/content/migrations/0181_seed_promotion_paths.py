from django.db import migrations

# Frozen snapshot of the two promotions that were hardcoded in
# AdvancementTypeForm.ADVANCEMENT_CONFIGS at the time of this migration. Deliberately inlined
# (not imported from n23.content.models.promotion) so this historical migration stays
# reproducible regardless of how the live DEFAULT_PROMOTIONS evolves in later phases.
# The live constant remains the source of truth going forward; later paths (e.g. the per-house
# Prospect promotions) ship as their own migrations or admin-authored content rather than by
# mutating this one.
SEED = [
    {
        "name": "Promote to Specialist",
        "kind": "RELABEL",
        "from_category": "GANGER",
        "to_category": "SPECIALIST",
        "rank": 1,
        "xp_cost": 6,
        "cost_increase": 20,
        "rolls": [2, 12],
        "grants_skill": "primary_random",
        "timing": "POST_BATTLE",
    },
    {
        "name": "Promote to Champion",
        "kind": "TYPE_CHANGE",
        "from_category": "SPECIALIST",
        "to_category": "CHAMPION",
        "rank": 2,
        "xp_cost": 12,
        "cost_increase": 40,
        "rolls": [],
        "grants_skill": "primary_random",
        "timing": "POST_BATTLE",
    },
]

_DEFAULT_FIELDS = (
    "name",
    "kind",
    "rank",
    "xp_cost",
    "cost_increase",
    "rolls",
    "grants_skill",
    "timing",
)


def forwards(apps, schema_editor):
    model = apps.get_model("content", "ContentPromotionPath")
    for entry in SEED:
        model.objects.update_or_create(
            from_category=entry["from_category"],
            to_category=entry["to_category"],
            defaults={field: entry[field] for field in _DEFAULT_FIELDS},
        )


def backwards(apps, schema_editor):
    model = apps.get_model("content", "ContentPromotionPath")
    for entry in SEED:
        model.objects.filter(
            from_category=entry["from_category"], to_category=entry["to_category"]
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0180_add_content_promotion_path"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
