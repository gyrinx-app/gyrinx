# Reach becomes what the author said, never what carriage implies.
#
# ``targets the model`` used to reach whoever could see the carrier: the
# bearer for a fighter-held thing, every member for a gang-held one, with
# a ``when_directly_assigned`` flag opting back out. The reach is now a
# stated choice — ``bearer`` or ``every_model`` — so existing rows are
# converted to whichever preserves what they were doing, read off what
# carries them. Every decision that changes a row to ``every_model``, and
# every row that could not be decided from its carriers, is printed for
# the maintainer to review.

from django.db import migrations, models

#: Kinds whose carriers land on the gang: their targets-model modifiers
#: only ever reached members through the gang, so the reach they meant is
#: every model.
GANG_SIDE = ("Affiliation", "Archetype", "GangType")

#: Kinds that can be assigned to either a gang or a model, where the
#: carrier's live use decides. A pickable's host follows its slot, so a
#: gang-held pick's payload is a gang-side modifier.
EITHER_SIDE = ("Rule", "Hidden", "Pickable", "Slot")

#: Every kind that may carry modifiers and is neither of the above —
#: fighter-side, where the bearer already was the behaviour.
FIGHTER_SIDE = (
    "Profile",
    "Wargear",
    "Weapon",
    "WeaponProfile",
    "WeaponAccessory",
    "Subtype",
    "Skill",
    "SkillTree",
    "Specialisation",
    "Power",
    "Collection",
    "Counter",
    "Trait",
)


def _carrier_kinds(apps, modifier_ids):
    """The kind names carrying any of these modifiers, with the rows."""
    found = []
    for kind in (*GANG_SIDE, *EITHER_SIDE, *FIGHTER_SIDE):
        try:
            model = apps.get_model("library", kind)
        except LookupError:
            continue
        try:
            model._meta.get_field("modifiers")
        except Exception:
            continue
        for carrier in model.objects.filter(modifiers__in=modifier_ids).distinct():
            found.append((kind, carrier))
    return found


def _used_on_a_gang(apps, kind, carrier):
    """Whether this rule/hidden reaches gangs anywhere: a live assignment
    hosted on a gang, or a place in any gang type's founding built-ins."""
    Assignment = apps.get_model("n26", "Assignment")
    GangType = apps.get_model("library", "GangType")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    column = kind.lower()
    if (
        Assignment.objects.filter(archived=False, gang__isnull=False)
        .filter(**{column: carrier})
        .exists()
    ):
        return True
    founding = GangType.objects.filter(built_ins__isnull=False).values_list(
        "built_ins", flat=True
    )
    return (
        DefaultAssignment.objects.filter(default_set__in=founding)
        .filter(**{column: carrier})
        .exists()
    )


def say_the_reach(apps, schema_editor=None):
    TargetsMiniature = apps.get_model("library", "TargetsMiniature")
    Modifier = apps.get_model("library", "Modifier")
    for scope in TargetsMiniature.objects.all():
        # The flag said bearer outright; ``bearer`` is also the new
        # column's default, so only the other decisions write.
        if getattr(scope, "when_directly_assigned", False):
            continue
        modifiers = list(
            Modifier.objects.filter(targets_miniature=scope).values_list(
                "pk", flat=True
            )
        )
        names = list(
            Modifier.objects.filter(targets_miniature=scope).values_list(
                "name", flat=True
            )
        )
        carriers = _carrier_kinds(apps, modifiers) if modifiers else []
        gang_use = False
        for kind, carrier in carriers:
            if kind in GANG_SIDE:
                gang_use = True
            elif kind in EITHER_SIDE and _used_on_a_gang(apps, kind, carrier):
                gang_use = True
                said = getattr(carrier, "name", None) or carrier.pk
                print(
                    f"[reach] {names}: carried by {kind} “{said}”, "
                    "which reaches gangs — converted to all models."
                )
        if not carriers and modifiers:
            print(
                f"[reach] {names}: nothing carries it — left as the model "
                "carrying it; revisit when it is attached."
            )
        if gang_use:
            fighter_kinds = [k for k, _ in carriers if k in FIGHTER_SIDE]
            if fighter_kinds:
                print(
                    f"[reach] {names}: MIXED carriage (gang-side and "
                    f"{fighter_kinds}) — converted to all models; the "
                    "fighter-side use now reaches everyone. Review."
                )
            scope.reach = "every_model"
            scope.save(update_fields=["reach"])


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0060_slots_and_picks_help_in_the_maintainers_words"),
        ("n26", "0012_a_pick_names_the_slot_it_settles"),
    ]

    operations = [
        migrations.AddField(
            model_name="targetsminiature",
            name="reach",
            field=models.CharField(
                choices=[
                    ("bearer", "the model carrying it"),
                    ("every_model", "all models in the gang"),
                ],
                default="bearer",
                help_text=(
                    "The model carrying it: only the model this is directly "
                    "assigned to. All models in the gang: everyone, however "
                    "it is carried."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="targetsgang",
            name="echoes",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Whether what this gives the gang also reaches every "
                    "model. Off, it is the gang's alone."
                ),
            ),
        ),
        migrations.RunPython(say_the_reach, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="targetsminiature",
            name="when_directly_assigned",
        ),
    ]
