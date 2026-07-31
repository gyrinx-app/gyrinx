from django.db import migrations
from django.db.models import Q

# ContentRule.shed_on_promotion shipped in #2023 but the live content never got the
# authoring pass, so type-changed fighters (incl. #1468 leader nominations) kept their
# old type's scaffolding rules on display. Flag the type-scoped scaffolding families:
# - "Gang Fighter (X)" — gang-composition counting derives from the CURRENT type;
# - "Promotion (…)" — eligibility text for a promotion the fighter has taken/outgrown;
# - "Tools of the Trade (… only)" / "Devout Masses (X)" — parametrised per-type variants
#   (plain "Tools of the Trade" is a real rule and is NOT flagged);
# - "Fast Learner" and "Hot-headed" — the rookie pair on Juve-type rows (named as the
#   canonical shed examples in the #2023 field help);
# - "Wasteland Snipers" — scoped to Ash Waste Nomads Warriors ("Warriors treat long
#   rifles as Basic").
# Target types that keep any of these carry their own copies (e.g. the (Specialist)
# rows carry "Gang Fighter (Specialist)" and "Wasteland Snipers"), so shedding from the
# base type is lossless — audited across every authored promotion path in prod content.
#
# Further house-specific type-scoped rules can be flagged in the admin as they are
# spotted; this migration only covers the unambiguous families.
SHED = (
    Q(name__startswith="Gang Fighter (")
    | Q(name__startswith="Promotion (")
    | Q(name__startswith="Tools of the Trade (")
    | Q(name__startswith="Devout Masses (")
    | Q(name="Fast Learner")
    | Q(name="Hot-headed")
    | Q(name="Wasteland Snipers")
)


def forwards(apps, schema_editor):
    ContentRule = apps.get_model("content", "ContentRule")
    ContentRule.objects.filter(SHED).update(shed_on_promotion=True)


def backwards(apps, schema_editor):
    ContentRule = apps.get_model("content", "ContentRule")
    ContentRule.objects.filter(SHED).update(shed_on_promotion=False)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0187_seed_leader_nomination"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
