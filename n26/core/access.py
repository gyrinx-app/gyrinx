"""Discover browsable collections from effective model and gang cards.

Equipment access comes from held collection assignments, including personal
built-ins, gang-hosted assignments and computed grants. Gang-granted collections
also reach members through the gang card.

Skills access comes from computed category placements into collection sections.
A profile without those placements has no skills listing.

Access informs, never polices: these are the collections purchase controls
offer. ``Operation.buy`` does not enforce this discovery policy.
"""

from dataclasses import dataclass

from n26.core.card import build_card, build_modifier_index, carriers
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


@dataclass(frozen=True)
class ActionAccess:
    """One action a fighter may use, and what provides it."""

    action: object
    source: str | None = None
    computed: bool = False

    @property
    def name(self):
        return str(self.action)

    @property
    def usability(self):
        return self.action.usable_by_words()


@dataclass(frozen=True)
class RankTableAccess:
    """One rank table a fighter holds, and what provides it."""

    rank_table: object
    source: str | None = None
    computed: bool = False

    @property
    def name(self):
        return str(self.rank_table)


def actions_for(miniature, card=None, computed=None):
    """Every effective action this fighter holds, with duplicate grants collapsed."""
    from n26.library.models import Action

    return _access_for(miniature, Action, ActionAccess, "action", card, computed)


def rank_tables_for(miniature, card=None, computed=None):
    """Every effective rank table this fighter holds, with duplicate grants collapsed."""
    from n26.library.models import RankTable

    return _access_for(
        miniature, RankTable, RankTableAccess, "rank_table", card, computed
    )


def rank_table_for(miniature, counter, card=None, computed=None):
    """The effective rank table for one counter, or ``None``.

    More than one matching table is conflicting content. Refuse explicitly
    instead of choosing whichever assignment happened to be read first.
    """
    matches = [
        access
        for access in rank_tables_for(miniature, card=card, computed=computed)
        if access.rank_table.counter_id == counter.pk
    ]
    if len(matches) > 1:
        from n26.core.operations import Refusal

        names = ", ".join(access.name for access in matches)
        raise Refusal(
            f"{miniature.name} has more than one rank table for {counter}: {names}."
        )
    return matches[0] if matches else None


def _access_for(miniature, model, access_type, attribute, card=None, computed=None):
    """Read one assignable kind from the same stored and computed card sources."""
    if card is None:
        card = build_card(miniature)
    if computed is None:
        computed = compute(card, build_modifier_index(carriers(card)))

    found = {}
    nodes_by_key = {node.key: node for node in card.all_nodes()}
    for node in card.all_nodes():
        if node.suppressed or node.assignment is None:
            continue
        if getattr(node.assignment, f"{attribute}_id", None) is None:
            continue
        cause = nodes_by_key.get(node.caused_by_key)
        found.setdefault(
            node.assignable.pk,
            access_type(node.assignable, cause.name if cause is not None else None),
        )

    for contribution in (*computed.acquired, *computed.echoed):
        if isinstance(contribution.thing, model):
            found.setdefault(
                contribution.thing.pk,
                access_type(contribution.thing, contribution.source, computed=True),
            )
    return list(found.values())


def collections_for(miniature, card=None, computed=None):
    """Read effective collections from this fighter's stored and computed card.

    First occurrence determines provenance for duplicates. Supply ``card`` and
    ``computed`` to reuse a build already performed by the caller.
    """
    if card is None:
        card = build_card(miniature)
    if computed is None:
        index = build_modifier_index(carriers(card))
        computed = compute(card, index)

    # Broadcast nodes expose gang-held collections during the same walk.
    return _collections_on(card, computed, miniature.gang)


def hidden_categories_for(collection, computed):
    """Combine active restrictions on this collection without querying."""
    return {
        category
        for hidden in computed.hidden_categories
        if hidden.collection.pk == collection.pk
        for category in hidden.categories
    }


def gang_collections(gang, card=None, computed=None):
    """Read the gang's assigned and computed collections for hire discovery.

    Reuse supplied card and computed state, otherwise build both here.
    """
    from n26.core.card import build_gang_card
    from n26.core.effects import compute_gang

    if card is None:
        card = build_gang_card(gang, with_statlines=False)
    if computed is None:
        index = build_modifier_index(carriers(card))
        computed = compute_gang(card, index)
    return _collections_on(card, computed, gang, gang_hosted=True)


def _collections_on(card, computed, gang, gang_hosted=False):
    """Merge stored and computed collection access, then order by collection position.

    Skip suppressed assignments. First occurrence determines provenance for duplicate
    collections, and equal positions retain discovery order. Gang-hosted sources
    use their cause's name, or the gang when manually assigned.
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

    # Computed gang grants also provide member collection access. Gang cards
    # read these as acquisitions; member cards read them as echoed grants.
    for contribution in computed.echoed:
        if isinstance(contribution.thing, Collection):
            add(contribution.thing, contribution.source, is_computed=True)

    # A stable sort, so ties keep the order the walk found them in.
    return sorted(found.values(), key=lambda access: access.collection.position)


def model_collections():
    """Load collections containing selectable model identities or abilities in one query.

    Use the library family rather than a fixed kind list. Roster callers share
    this result across cards; equipment placements cannot open a skills listing.
    """
    from n26.library.models import Collection, Family

    return list(Collection.objects.containing(Family.MODEL))


def placed_collections(computed):
    """Return collection IDs reached by the computed category placements without querying."""
    return {str(placement.section.collection_id) for placement in computed.placements}


def selectable_for(computed, among=None):
    """Restrict placed collections to families holding model abilities or identity.

    Require both effective placement and the family test, excluding equipment collections.
    """
    placed = placed_collections(computed)
    return [
        collection
        for collection in (model_collections() if among is None else among)
        if str(collection.pk) in placed
    ]
