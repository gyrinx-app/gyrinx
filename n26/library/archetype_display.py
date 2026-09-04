"""Drawing an Outcast gang's archetype on the models it governs.

The leader picks the archetype, the gang holds it, and every model in
the gang plays by it — every model but the Champions, who pick one of
their own. A pick the gang holds rides each member's card without being
listed on it, so the line that says which archetype a model plays by is
a modifier the pickable carries: reaching every model except Champions,
and drawing the pick there.

One modifier, shared by every archetype on the leader's list, because
they all say the same thing about who sees the line. It hangs on the
pickables the leader may pick and on nothing else, which is what keeps
a Champion's own archetype off everyone else's cards.

Written here rather than inside the migration that performs it so it can
be read, run and tested as ordinary code. It adds and never takes away:
running it a second time finds what the first run made.
"""

#: The stored value of ``TargetsMiniature.Reach.EVERY_MODEL``. Written
#: out because a migration's historical models carry fields and nothing
#: else; a test holds the two together.
EVERY_MODEL = "every_model"

#: What the modifier is called in the authoring pages. Looked up by this
#: name, so changing it makes a second modifier rather than renaming the
#: first.
MODIFIER_NAME = "Archetype: drawn on every model except Champions"

#: The rank that plays by an archetype of its own, named as the one
#: exception so a rank authored later is reached without anyone
#: revisiting the condition.
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

    # Matched without regard to case, because the name is unique per pack
    # that way: an exact-match lookup would miss a differently-cased row
    # and then trip the constraint on the way in.
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
