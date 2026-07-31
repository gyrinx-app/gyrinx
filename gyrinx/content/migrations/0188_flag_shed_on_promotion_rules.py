from django.db import migrations
from django.db.models import Q

# ContentRule.shed_on_promotion shipped in #2023 but the live content never got the
# authoring pass, so type-changed fighters (incl. #1468 leader nominations) kept their
# old type's scaffolding rules on display. Flag the two universal scaffolding families —
# every "Gang Fighter (X)" (gang-composition counting derives from the CURRENT type) and
# every "Promotion (…)" (eligibility text for a promotion the fighter has now taken or
# outgrown) — plus "Wasteland Snipers", which the rules scope to Ash Waste Nomads
# Warriors ("Warriors treat long rifles as Basic"). Target types that keep any of these
# carry their own copies (e.g. the (Specialist) rows carry "Gang Fighter (Specialist)"
# and "Wasteland Snipers"), so shedding from the base type is lossless.
#
# Further house-specific type-scoped rules can be flagged in the admin as they are
# spotted; this migration only covers the unambiguous families.
SHED = (
    Q(name__startswith="Gang Fighter (")
    | Q(name__startswith="Promotion (")
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
