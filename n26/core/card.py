"""Model cards — a model's assignments, in memory, in one query.

A card is what a model looks like: its profile, its weapons, the ammo and
accessories hung off them. Building one costs **one** database query. The
tree is not walked in the database; every assignment carries the model at
the top of its chain, so they all come back flat and are reassembled here
by parent.

The point of doing it this way is that the ergonomic reads — a node's
rating, its children, its total with extras — are then plain Python on rows
already in memory, with no chance of a query hiding behind a property.
Tests assert the query count so that stays true.
"""

# Deferred annotations: Node refers to itself, and the host runs 3.12,
# where class-body annotations still evaluate eagerly.
from __future__ import annotations

from dataclasses import dataclass, field

from n26.core.effects import ModifierIndex
from n26.core.models import Assignment, Reason
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.library.models.modifier import GANG, MODEL


@dataclass
class Node:
    """One line on a card, with whatever hangs off it.

    A card is usually built from a player's assignments, but not always: a
    hire preview is built from a profile's default equipment, where no row
    exists yet. So a node describes itself — its identity, rating, cause and
    role are its own fields — and ``assignment`` is present only when the
    card came from stored rows. Nothing downstream reaches through it.
    """

    assignable: object
    #: Identity within one card. An assignment's primary key when there is
    #: one, otherwise a number handed out while building. Only ever compared
    #: with other keys from the same card.
    key: object
    children: list[Node] = field(default_factory=list)
    #: What this line contributes on its own.
    rating: int = 0
    #: The key of the node that brought this one, if any.
    caused_by_key: object = None
    #: The ledger's reason, for a line that has one.
    reason: str | None = None
    is_weapon_profile: bool = False
    #: A fighter profile — the hire, or a Venator's Legacy alongside it.
    is_profile: bool = False
    #: The one profile whose statline and type the card is drawn from.
    is_primary_profile: bool = False
    #: Held by the *gang*, not this model: the gang type's founding and
    #: whatever it brought. Such a node rides every member's card so that
    #: gang-wide modifiers reach them and can be named as a source — but
    #: it draws no row and adds no rating, because the model does not own
    #: it. Scoped by host, where a ``Hidden`` is scoped by kind.
    broadcast: bool = False
    #: The stored row, when this card was built from stored rows.
    assignment: Assignment | None = None

    @property
    def name(self):
        return str(self.assignable)

    @property
    def rating_with_extras(self):
        """This line plus everything hung off it — a gun with its paid ammo."""
        return self.rating + sum(child.rating_with_extras for child in self.children)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def node_for(assignment):
    """A node describing one stored assignment."""
    entry = getattr(assignment, "ledger_entry", None)
    role = getattr(assignment, "profile_role", None)
    return Node(
        assignable=assignment.assignable,
        key=assignment.pk,
        rating=assignment.rating,
        caused_by_key=assignment.caused_by_id,
        reason=entry.reason if entry else None,
        is_weapon_profile=assignment.weapon_profile_id is not None,
        is_profile=assignment.profile_id is not None,
        is_primary_profile=(
            assignment.profile_id is not None
            and (role is None or role.role == "primary")
        ),
        assignment=assignment,
    )


@dataclass
class Card:
    miniature: object
    roots: list[Node] = field(default_factory=list)
    #: The whole pool's worth, whatever this card selects. Cost never varies
    #: by card — a weapon is bought once and counted once.
    full_rating: int = 0

    #: What kind of thing this card belongs to. Scopes read it — an
    #: unfiltered ``TargetsMiniature`` must not swallow a gang, nor
    #: ``TargetsGang`` a model — so each card type says what it hosts.
    host_kind = MODEL

    @property
    def rating(self):
        """Everything on *this* card. For an unfiltered card this equals
        ``full_rating``; for a named selection it may be less."""
        return sum(node.rating_with_extras for node in self.roots)

    def all_nodes(self):
        for root in self.roots:
            yield from root.walk()

    def weapon_profile_nodes(self):
        """Every weapon profile on the card — what weapon-scoped modifiers reach."""
        return [node for node in self.all_nodes() if node.is_weapon_profile]

    def find(self, name):
        """First node whose display name matches — for tests and lookups."""
        return next((n for n in self.all_nodes() if n.name == name), None)

    def model_matchable(self):
        """The model as selector food: its entry, its type, its subtypes
        and the specialisation it chose.

        The **base** adapter: printed facts — stored rows — only. During
        ``compute`` each round layers what earlier rounds settled on top
        of this (``n26.effects._Facts``), so a filtered scope sees
        unconditional grants; ``usability_for`` layers the final state
        the same way. Called bare, it answers from the rows alone.

        A specialisation counts as a possession for the same reason a
        subtype does: "(Gunner specialist only)" asks what this fighter
        *is*, and the choice is the answer.
        """
        from n26.core import select
        from n26.library.models import Counter, Specialisation, Subtype

        profile = None
        possessions = []
        counts = []
        for node in self.all_nodes():
            if node.broadcast:
                # The gang's rows ride the card for their effects; they
                # are not facts about this model.
                continue
            if node.is_primary_profile:
                profile = node.assignable
                possessions.append(profile.profile_type)
            elif isinstance(node.assignable, (Subtype, Specialisation)):
                possessions.append(node.assignable)
            elif isinstance(node.assignable, Counter):
                held = (
                    getattr(node.assignment, "counter_value", None)
                    if node.assignment is not None
                    else None
                )
                counts.append((select.key(node.assignable), held.value if held else 0))
        base = select.matchable(profile, assignables=possessions)
        return select.Matchable(
            thing=base.thing, assignables=base.assignables, counts=tuple(counts)
        )


@dataclass
class GangCard:
    """The gang's own card: what *it* holds, as first-class rows.

    The same rows ride every member's card marked ``broadcast`` so
    gang-wide modifiers reach the fighters; here they are the content.
    Everything a test wants to say about the gang as a thing — its
    founding row, its house list, its choice slots, its stash — asserts
    against this structure and the ``ComputedGang`` built from it
    (design/gang-sheet.md); renderables derive from those.
    """

    gang: object
    #: Gang-hosted assignment trees: the founding, the house list, rules,
    #: counters, choice slots and their answers.
    roots: list[Node] = field(default_factory=list)
    #: Stash-hosted trees. On the card so the sheet can draw them,
    #: but not in ``all_nodes()``: nothing in the stash is a fact about
    #: the gang, and nothing in it computes (design/gang-sheet.md,
    #: out of scope until something needs it).
    stash_roots: list[Node] = field(default_factory=list)
    #: Every member's ``Card``, keyed by miniature id, from the same
    #: fetch family — so a whole sheet stays a fixed number of queries.
    members: dict = field(default_factory=dict)

    host_kind = GANG

    @property
    def stash_rating(self):
        return sum(node.rating_with_extras for node in self.stash_roots)

    def all_nodes(self):
        for root in self.roots:
            yield from root.walk()

    def weapon_profile_nodes(self):
        return [node for node in self.all_nodes() if node.is_weapon_profile]

    def find(self, name):
        return next((n for n in self.all_nodes() if n.name == name), None)

    def stash_find(self, name):
        return next(
            (
                node
                for root in self.stash_roots
                for node in root.walk()
                if node.name == name
            ),
            None,
        )

    def model_matchable(self):
        """The gang as selector food: everything it holds, plus counts.

        Broader than a model's policy on purpose — a gang has no type or
        subtypes, so its facts are simply its own rows, which is what a
        ``Has(house list)`` or a gang-level ``CounterAtLeast`` asks about.
        """
        from n26.core import select
        from n26.library.models import Counter

        possessions = []
        counts = []
        for node in self.all_nodes():
            possessions.append(node.assignable)
            if isinstance(node.assignable, Counter):
                held = (
                    getattr(node.assignment, "counter_value", None)
                    if node.assignment is not None
                    else None
                )
                counts.append((select.key(node.assignable), held.value if held else 0))
        base = select.matchable(self.gang, assignables=possessions)
        return select.Matchable(
            thing=base.thing, assignables=base.assignables, counts=tuple(counts)
        )


def card_rows(with_statlines=False, **filters):
    """The flat fetch every card build starts from — one query.

    ``with_statlines`` pulls each profile's characteristics along too, which
    rendering needs and plain assignment work does not. It costs a few more
    queries, but a *fixed* few: without it, rendering a gang would query per
    model.
    """
    rows = Assignment.objects.filter(archived=False, **filters).select_related(
        *ASSIGNABLE_FIELDS,
        "ledger_entry",
        "profile_role",
        "counter_value",
        "profile__profile_type",
        # A chosen-mode placement reads the answering token's home off
        # the row already in memory — never by a query.
        "skill_tree__category",
    )
    if with_statlines:
        rows = rows.prefetch_related(
            "profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__traits",
        )
    return list(rows)


def gang_rows(gang, with_statlines=False):
    """What the gang itself holds: its founding, and what that brought.

    Hosted on the gang with no model of their own, so they belong to
    every member's card and to none of their ratings.
    """
    if gang is None:
        return []
    return card_rows(
        with_statlines=with_statlines,
        gang_root=gang,
        miniature_root__isnull=True,
        # The stash is the gang's too, but it is storage, not a fact
        # about every member — nothing in it may broadcast onto cards.
        stash_root__isnull=True,
    )


def assemble(miniature, rows, assignment_set=None, broadcast=()):
    """Reassemble a flat list of assignments into a tree. No queries beyond
    the set's selection, when one is given.

    With an ``assignment_set``, unselected equipment roots — and everything
    beneath them — are left off the card. Non-equipment (the profile,
    subtypes, skills, injuries) always rides.
    """
    kept = rows
    if assignment_set is not None:
        from n26.core.models.assignment_set import SELECTABLE_FIELDS

        selected = assignment_set.selected_ids()
        dropped = {
            row.pk
            for row in rows
            if row.parent_id is None
            and row.pk not in selected
            and any(
                getattr(row, f"{field}_id") is not None for field in SELECTABLE_FIELDS
            )
        }
        # Children follow their parents off the card, at any depth.
        changed = True
        while changed:
            changed = False
            for row in rows:
                if row.parent_id in dropped and row.pk not in dropped:
                    dropped.add(row.pk)
                    changed = True
        kept = [row for row in rows if row.pk not in dropped]

    nodes = {row.pk: node_for(row) for row in kept}
    for row in broadcast:
        node = node_for(row)
        node.broadcast = True
        nodes[row.pk] = node
    roots = []
    for row in [*kept, *broadcast]:
        node = nodes[row.pk]
        parent = nodes.get(row.parent_id)
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    card = Card(miniature=miniature, roots=roots)
    # Only what the model owns. The gang's own rows ride the card so their
    # modifiers reach it; they are not part of what it is worth.
    card.full_rating = sum(
        row.ledger_entry.rating_contribution
        for row in rows
        if getattr(row, "ledger_entry", None)
    )
    return card


def build_card(miniature, with_statlines=False, assignment_set=None):
    """A model's card: everything it owns, or one named selection.

    Two queries rather than one: the model's own rows, then the gang's,
    which ride along so gang-wide modifiers reach this card. A whole
    gang's worth still costs a fixed number — see ``build_cards_for_gang``,
    where both come back in the same fetch.
    """
    membership = miniature.membership if miniature is not None else None
    return assemble(
        miniature,
        card_rows(miniature_root=miniature, with_statlines=with_statlines),
        assignment_set=assignment_set,
        broadcast=gang_rows(
            membership.gang if membership else None, with_statlines=with_statlines
        ),
    )


def build_cards_for_gang(gang, with_statlines=True):
    """Every model's card in the gang, keyed by model id — one flat fetch.

    The gang's own rows come back in the same query (they share a
    ``gang_root``) and are handed to every model's card rather than
    thrown away, which is what makes the broadcast free here.
    """
    return build_gang_card(gang, with_statlines=with_statlines).members


def _forest(rows):
    """Trees from flat assignment rows, parents resolved in memory."""
    nodes = {row.pk: node_for(row) for row in rows}
    roots = []
    for row in rows:
        node = nodes[row.pk]
        parent = nodes.get(row.parent_id)
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def build_gang_card(gang, with_statlines=True):
    """The gang's own card, its stash, and every member's card.

    The same fetch family as ever: one query for everything hosted under
    the gang except the stash, plus one for its contents — kept
    apart because stash rows belong on no member's card and nothing in
    them broadcasts (storage, not facts about anyone).
    """
    grouped = {}
    shared = []
    rows = card_rows(
        gang_root=gang, stash_root__isnull=True, with_statlines=with_statlines
    )
    for row in rows:
        if row.miniature_root_id is None:
            shared.append(row)
        else:
            grouped.setdefault(row.miniature_root_id, []).append(row)
    return GangCard(
        gang=gang,
        roots=_forest(shared),
        stash_roots=_forest(
            card_rows(
                gang_root=gang,
                stash_root__isnull=False,
                # Storage, drawn as names and ratings — nobody reads a
                # statline off it, so its fetch never pays for them.
                with_statlines=False,
            )
        ),
        members={
            miniature_id: assemble(None, rows, broadcast=shared)
            for miniature_id, rows in grouped.items()
        },
    )


def build_card_from_profile(profile, option=None):
    """The card a hire *would* produce, built from library alone.

    No gang, no model, no assignments: this is what a player sees while
    deciding. It mirrors ``Operation.hire`` exactly — the built-ins, then
    every set the selection takes (each one-of group's head unless named),
    each member caused by the profile, weapons carrying their free
    profiles and bundled ammo hanging off its weapon — so a preview and
    the thing you get are the same card.
    """
    from n26.library.models import Weapon, WeaponProfile

    taken = profile.resolve_selection(option)
    counter = iter(range(1, 10_000))

    root = Node(
        assignable=profile,
        key=next(counter),
        rating=profile.price_with(taken),
        is_profile=True,
        is_primary_profile=True,
        reason=Reason.BOUGHT,
    )
    roots = [root]
    weapon_nodes = {}
    ammo = []

    for default_set in (profile.built_ins, *taken):
        if default_set is None:
            continue
        for member in default_set.members.all():
            assignable = member.assignable
            if assignable is None:
                continue
            if isinstance(assignable, WeaponProfile):
                ammo.append(assignable)
                continue
            node = Node(
                assignable=assignable,
                key=next(counter),
                caused_by_key=root.key,
                reason=Reason.DEFAULT,
            )
            if isinstance(assignable, Weapon):
                node.children.extend(
                    Node(
                        assignable=weapon_profile,
                        key=next(counter),
                        caused_by_key=node.key,
                        reason=Reason.DEFAULT,
                        is_weapon_profile=True,
                    )
                    for weapon_profile in assignable.profiles.all()
                    if weapon_profile.price == 0
                )
                weapon_nodes[assignable.pk] = node
            roots.append(node)

    # Bundled ammo stacks under its weapon, wherever in the selection the
    # weapon arrived — the same order of business as the hire itself.
    for weapon_profile in ammo:
        host = weapon_nodes.get(weapon_profile.weapon_id)
        if host is None:
            raise ValueError(
                f"{profile.name} grants {weapon_profile}, but nothing in "
                f"this hire brings its weapon ({weapon_profile.weapon})."
            )
        host.children.append(
            Node(
                assignable=weapon_profile,
                key=next(counter),
                caused_by_key=host.key,
                reason=Reason.DEFAULT,
                is_weapon_profile=True,
            )
        )

    card = Card(miniature=None, roots=roots)
    # Content prices the package outright; a hired card reaches the same
    # number by summing ledger lines whose items are all free.
    card.full_rating = root.rating
    return card


def build_modifier_index(assignables, max_depth=3):
    """Load every modifier reachable from these assignables, and from what
    they grant, and from what *those* grant.

    A fixed number of queries — one per assignable kind per level of the
    grant chain — regardless of how many models or how much kit. ``compute``
    then runs entirely off this, touching the database not at all.
    """
    from django.db.models import Prefetch, prefetch_related_objects

    from n26.library.models import CounterAtLeast, Modifier
    from n26.library.models.modifier import (
        EFFECT_FIELDS,
        GRANTABLE_FIELDS,
        SCOPE_FIELDS,
    )

    related = (
        *SCOPE_FIELDS,
        *EFFECT_FIELDS,
        "targets_weapons__with_trait",
        # Without these, naming a choice's kind or a placed category
        # queries once per slot or placement.
        "offers_choice__of_kind",
        "places_category__category",
        "places_category__section__collection",
        "requires_companions__for_each",
        "requires_companions__of",
        *(f"adds_assignable__{name}" for name in GRANTABLE_FIELDS),
        *(f"removes_assignable__{name}" for name in GRANTABLE_FIELDS),
        "changes_stat__stat",
    )
    #: Condition rows are reverse relations, so they cannot ride
    #: select_related — without these a scope's narrowing costs a query
    #: per card to learn who it reaches.
    also_prefetch = (
        "targets_miniature__has_subtypes__subtypes",
        Prefetch(
            "targets_miniature__counter_at_least",
            queryset=CounterAtLeast.objects.select_related("counter"),
        ),
    )

    index = ModifierIndex()
    seen = set()
    frontier = list(assignables)

    for _ in range(max_depth):
        by_model = {}
        for thing in frontier:
            key = ModifierIndex.key(thing)
            if key in seen:
                continue
            seen.add(key)
            by_model.setdefault(type(thing), []).append(thing)
        if not by_model:
            break

        granted = []
        for things in by_model.values():
            # One query per kind, straight onto the objects we already hold —
            # re-fetching them would double the count for nothing.
            prefetch_related_objects(
                things,
                Prefetch(
                    "modifiers",
                    queryset=Modifier.objects.select_related(*related).prefetch_related(
                        *also_prefetch
                    ),
                ),
            )
            for thing in things:
                modifiers = list(thing.modifiers.all())
                index.add(thing, modifiers)
                for modifier in modifiers:
                    granted_thing = getattr(modifier.effect, "thing", None)
                    if granted_thing is not None:
                        granted.append(granted_thing)
        frontier = granted

    return index
