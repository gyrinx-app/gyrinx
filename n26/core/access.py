"""Which collections a fighter can browse.

There is no access table. Having a list is an assignment (a collection is
an assignable — see ``n26.library.models.collection``), so a fighter's
effective collections are **read off the card**:

* collection assignments on their own card — the profile's list arrives
  via its built-ins at hire, a Legacy profile brings its list the same
  way;
* collection assignments hosted on their gang — the shared house list,
  assigned once;
* computed grants — a territory or alliance whose modifier adds a
  collection, present exactly while the granter is.

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


def collections_for(miniature):
    """Every collection this fighter can browse, in discovery order:
    their own, then their gang's, then computed grants. First mention of
    a collection wins, so duplicates collapse towards the more direct
    source."""
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    found = {}

    def add(collection, source, is_computed=False):
        if collection.pk not in found:
            found[collection.pk] = CollectionAccess(
                collection=collection, source=source, computed=is_computed
            )

    # The gang's own lists ride the card now (as broadcast nodes), so this
    # one walk finds a fighter's lists and their gang's alike — no second
    # query, no second code path. A gang-held list names whatever brought
    # it, which after founding is the gang *type*; assigned by hand it has
    # no cause, so the gang itself answers for it.
    gang = miniature.gang
    nodes_by_key = {node.key: node for node in card.all_nodes()}
    for node in card.all_nodes():
        if node.assignment is not None and node.assignment.collection_id is not None:
            cause = nodes_by_key.get(node.caused_by_key)
            if cause is not None:
                source = cause.name
            else:
                source = str(gang) if node.broadcast and gang is not None else None
            add(node.assignable, source)

    for contribution in computed.collections:
        add(contribution.thing, contribution.source, is_computed=True)

    return list(found.values())
