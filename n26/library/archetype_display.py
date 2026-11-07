"""Display a gang's Outcast archetype on every model except Champions.

The gang-held pickable carries a shared DrawsPick modifier scoped to
non-Champions. Champions use their own pick and must not broadcast it.
Match existing identifiers and preserve them on repeated runs.
"""

#: The stored reach value supports historical models, which have no enum constants.
EVERY_MODEL = "every_model"

#: The lookup name is an idempotency key; changing it would create another modifier.
MODIFIER_NAME = "Archetype: drawn on every model except Champions"

#: Exclude Champions because they choose their own archetype.
EXCEPTED_SUBTYPE = "Champion"

#: The archetypes an Outcast leader picks for the gang, in the order the
#: list offers them.
GANG_ARCHETYPE_IDS = (
    "01M0G937MFA7PQQ09MF5BVF50C",
    "01M0G937Q8PS2XCMAWC9HJE4ZK",
    "01M0G937SXCCQ20DQ8FGHKERSE",
    "01M0G937WKKC28RHJM25T3GQ5S",
    "01M0G937Z5EJSVP5JPY3EZJ2T8",
)


def draw_gang_archetypes(
    apps,
    pickable_ids=GANG_ARCHETYPE_IDS,
    name=MODIFIER_NAME,
    excepted=EXCEPTED_SUBTYPE,
):
    """Hang the drawing modifier on each archetype named, and give it back.

    ``apps`` is a model registry — a migration's historical one, or
    Django's own. Gives back ``None`` where the content is not there: a
    database with no default pack, no archetypes or no such rank has
    nothing to say this about, and a fresh one has none of the three.
    """
    from django.conf import settings

    ContentPack = apps.get_model("library", "ContentPack")
    Modifier = apps.get_model("library", "Modifier")
    Pickable = apps.get_model("library", "Pickable")
    Subtype = apps.get_model("library", "Subtype")

    pack = ContentPack.objects.filter(slug=settings.DEFAULT_CONTENT_PACK_SLUG).first()
    if pack is None:
        return None
    rank = Subtype.objects.filter(pack=pack, name__iexact=excepted).first()
    pickables = list(Pickable.objects.filter(pk__in=pickable_ids))
    if rank is None or not pickables:
        return None

    # Use the same case-insensitive matching as the unique name constraint.
    row = Modifier.objects.filter(pack=pack, name__iexact=name).first()
    if row is None:
        row = _compose(apps, pack, name, rank)
    for pickable in pickables:
        pickable.modifiers.add(row)
    return row


def _compose(apps, pack, name, rank):
    """The modifier itself: one scope, one condition row, one effect."""
    DrawsPick = apps.get_model("library", "DrawsPick")
    HasSubtypes = apps.get_model("library", "HasSubtypes")
    Modifier = apps.get_model("library", "Modifier")
    TargetsMiniature = apps.get_model("library", "TargetsMiniature")

    scope = TargetsMiniature.objects.create(reach=EVERY_MODEL)
    condition = HasSubtypes.objects.create(scope=scope, negate=True)
    condition.subtypes.set([rank])
    return Modifier.objects.create(
        pack=pack,
        name=name,
        targets_miniature=scope,
        draws_pick=DrawsPick.objects.create(),
    )
