"""Which collections a fighter — or the gang itself — can browse.

There is no access table. Having a list is an assignment (a collection is
an assignable — see ``n26.library.models.collection``), so a fighter's
effective collections are **read off the card**:

Skills work the other way round and for the same reason. Nobody is
assigned a skills collection; a fighter reaches one exactly where their
**grid** — the placements their profile and subtypes carry — puts a
category into one of its sections. The grid is the access, the way a
card is the access to an equipment list, so a profile whose grid nobody
has authored has no skills screen at all.

* collection assignments on their own card — the profile's list arrives
  via its built-ins at hire, a Legacy profile brings its list the same
  way;
* collection assignments hosted on their gang — the shared house list,
  assigned once;
* computed grants — a territory or alliance whose modifier adds a
  collection, present exactly while the granter is. A list granted to the
  *gang* is one of these too: it rides every member's card the way the
  gang-hosted assignments do.

Access informs, never polices: this is what a buying UI *offers*, and
``Operation.buy`` deliberately never consults it.
"""

from dataclasses import dataclass

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute


@dataclass(frozen=True)
class CollectionAccess:
    """One collection a fighter can browse, and why."""

    collection: object
    source: str | None = None  # what brought it: the profile, the territory…
    computed: bool = False

    @property
    def name(self):
        return str(self.collection)


def collections_for(miniature, card=None, computed=None):
    """Every collection this fighter can browse, in discovery order:
    their own, then their gang's, then computed grants. First mention of
    a collection wins, so duplicates collapse towards the more direct
    source.

    A caller that already built this fighter's card — and computed it —
    passes both, and this reads them instead of paying for the same
    build twice.
    """
    if card is None:
        card = build_card(miniature)
    if computed is None:
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute(card, index)

    # The gang's own lists ride the card now (as broadcast nodes), so one
    # walk finds a fighter's lists and their gang's alike — no second
    # query, no second code path.
    return _collections_on(card, computed, miniature.gang)


def gang_collections(gang, card=None, computed=None):
    """Every collection the gang itself carries: assigned to it, or granted.

    The gang-side twin of :func:`collections_for`, and the same reading of
    the same two sources — the collection assignments the card holds, then
    the computed grants an affiliation or a territory makes. A hire screen
    asks this to find the collections that offer fighters.

    A caller holding the gang's card and its computed form passes both;
    otherwise both are built here, at the usual fixed cost.
    """
    from n26.core.card import build_gang_card
    from n26.core.effects import compute_gang

    if card is None:
        card = build_gang_card(gang, with_statlines=False)
    if computed is None:
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute_gang(card, index)
    return _collections_on(card, computed, gang, gang_hosted=True)


def _collections_on(card, computed, gang, gang_hosted=False):
    """The collections a computed card reaches — the shared walk.

    Stored assignments first, in the order the card holds them, then the
    computed grants; first mention of a collection wins, so a list reached
    twice collapses towards the more direct source. A list something has taken
    away is not somewhere to buy from: the card no longer shows it, so it
    opens nothing either.

    A held list names whatever brought it, which after founding is the
    gang *type*; assigned by hand it has no cause, so the gang itself
    answers for it. ``gang_hosted`` says the card's own assignments are
    the gang's — true of a gang card, where a model's card marks the same
    assignments ``broadcast``.
    """
    from n26.library.models import Collection

    found = {}

    def add(collection, source, is_computed=False):
        if collection.pk not in found:
            found[collection.pk] = CollectionAccess(
                collection=collection, source=source, computed=is_computed
            )

    nodes_by_key = {node.key: node for node in card.all_nodes()}
    for node in card.all_nodes():
        if node.suppressed:
            continue
        if node.assignment is not None and node.assignment.collection_id is not None:
            cause = nodes_by_key.get(node.caused_by_key)
            if cause is not None:
                source = cause.name
            elif (gang_hosted or node.broadcast) and gang is not None:
                source = str(gang)
            else:
                source = None
            add(node.assignable, source)

    for contribution in computed.collections:
        add(contribution.thing, contribution.source, is_computed=True)

    # A list the gang was granted is somewhere its fighters buy from, exactly
    # as the house list assigned to the gang is. It rides a member's card
    # as the gang's guest, drawing no line, so it is read from the guests
    # — of which the gang's own card has none, the grant being its own.
    for contribution in computed.echoed:
        if isinstance(contribution.thing, Collection):
            add(contribution.thing, contribution.source, is_computed=True)

    return list(found.values())


def model_collections():
    """Every collection holding what a model *is* — skills, powers.

    One query, and the caller decides when to pay it: a roster asks once
    and tests every card against the answer, so a sheet of sixteen costs
    what a sheet of one does. Asked by family rather than by naming
    kinds, so a new sort of thing a model learns qualifies its
    collections the day it exists — and a placement aimed at a *gear*
    collection's schema, which content may perfectly well write, never
    opens a skills screen.
    """
    from n26.library.models import Collection, Family

    return list(Collection.objects.containing(Family.MODEL))


def placed_collections(computed):
    """The collections this fighter's grid reaches, by id.

    Pure reading of a computed card — no queries — because a placement
    already carries the collection section it aims at, and a collection
    section belongs to one collection.
    """
    return {str(placement.section.collection_id) for placement in computed.placements}


def learnable_for(computed, among=None):
    """The collections this fighter may learn from: the ones their grid
    places a category into, kept to those holding what a model is.

    Both halves matter. Without the grid every fighter would be handed
    the whole skill library, which is the library rather than their own;
    without the family test a placement into an equipment list's schema
    would open a learn screen onto gear.
    """
    placed = placed_collections(computed)
    return [
        collection
        for collection in (model_collections() if among is None else among)
        if str(collection.pk) in placed
    ]
