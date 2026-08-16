"""Model cards — a model's assignments, in memory, from a fixed fetch.

A card is what a model looks like: its profile, its weapons, the ammo and
accessories hung off them. Building one costs **one** assignment query, then a
fixed set of narrow hydration passes (``hydrate_rows``) — narrow because
Postgres plans a join across every content kind in tens of milliseconds
and executes it in one, and the planning is paid on every query. The tree
is not walked in the database; every assignment carries the model at the
top of its chain, so they all come back flat and are reassembled here by
parent.

The point of doing it this way is that the ergonomic reads — a node's
rating, its children, its total with extras — are then plain Python on
assignments already in memory, with no chance of a query hiding behind a
property.
Tests assert the query count so that stays true.
"""

# Deferred annotations: Node refers to itself, and the host runs 3.12,
# where class-body annotations still evaluate eagerly.
from __future__ import annotations

from dataclasses import dataclass, field

from n26.core.effects import ModifierIndex
from n26.core.models import Assignment, Reason
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.library.models.assignable import OPTION_OFFER_PATHS
from n26.library.models.modifier import GANG, MODEL


@dataclass
class Node:
    """One line on a card, with whatever hangs off it.

    A card is usually built from a player's assignments, but not always: a
    hire preview is built from a profile's built-ins, where no assignment
    exists yet. So a node describes itself — its identity, rating, cause and
    role are its own fields — and ``assignment`` is present only when the
    card came from stored assignments. Nothing downstream reaches through it.
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
    #: it draws no line and adds no rating, because the model does not own
    #: it. Scoped by host, where a ``Hidden`` is scoped by kind.
    broadcast: bool = False
    #: True when this line was worked out at read time and written
    #: nowhere — a weapon a modifier grants. Nothing paid for it, so it
    #: is worth nothing and there is nothing to sell.
    computed: bool = False
    #: True when a modifier has taken this line away
    #: (``n26.core.effects``). The assignment stays exactly where it is
    #: and stops being drawn, so removing whatever cancelled it brings the
    #: line back on the next read. Only ever set on an assignment nobody
    #: paid for, which is why a card's rating is the same either way.
    suppressed: bool = False
    #: What a counter member opens at, on a card built from library alone
    #: — a preview's Starting XP. A stored card ignores it: the value
    #: lives on the assignment, and this is what the hire will write
    #: there.
    opens_at: int = 0
    #: The stored assignment, when this card was built from stored ones.
    assignment: Assignment | None = None

    @property
    def name(self):
        return str(self.assignable)

    @property
    def rating_with_extras(self):
        """This line plus everything hung off it — a gun with its paid ammo."""
        return self.rating + sum(child.rating_with_extras for child in self.children)

    @property
    def carries_money(self):
        """Whether anything was paid for this line, or it is worth anything.

        The question a removal asks before it hides an assignment: free
        kit and assignments something else brought carry nothing, and a
        purchase carries either the credits paid for it or the worth it
        added — a gift with a rating counts as bought, because the gang is
        worth more for holding it. A card built from the library alone keeps
        no ledger, so what the line is worth is all it can say.
        """
        entry = (
            getattr(self.assignment, "ledger_entry", None) if self.assignment else None
        )
        if entry is not None:
            return bool(entry.paid or entry.trade_points or entry.rating_contribution)
        return bool(self.rating)

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
    #: The whole pool's worth, whatever this card selects. Rating never
    #: varies by card — a weapon is bought once and counted once.
    full_rating: int = 0

    #: Lines a modifier granted: a weapon the bearer never bought, with
    #: its free firing lines beneath it. Filled in by
    #: ``n26.core.effects.compute``, which clears and rebuilds the list on
    #: every run — a card nobody has computed has none. Apart from
    #: ``roots`` because ``roots`` are things the gang owns: these are
    #: worth nothing, appear on no ledger, and cannot be sold, so
    #: anything asking what a model *has* reads ``roots`` and anything
    #: asking what a model's card *shows* reads both.
    granted: list[Node] = field(default_factory=list)

    #: The characteristics this model's owner set by hand, keyed by the
    #: statline cell each stands in. Loaded with the rest of the build,
    #: because a render may not query. Empty on a card built without
    #: statlines, and on one built from the library alone: a preview
    #: depicts nobody, so there is nobody's settings to honour.
    stat_overrides: dict = field(default_factory=dict)

    #: The gang's own card, when this card belongs to one of its models.
    #: The gang's own assignments already ride here as broadcast nodes;
    #: what the gang holds by *grant* has no assignment to ride, so its
    #: card comes along and ``n26.core.effects`` reads those acquisitions
    #: off it. Built from assignments this build already fetched, so it
    #: costs no query of its own.
    gang_card: object = None

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
        for root in (*self.roots, *self.granted):
            yield from root.walk()

    def weapon_profile_nodes(self):
        """Every weapon profile on the card — what weapon-scoped modifiers reach.

        Granted lines included, which is what lets one modifier hand a
        beast its claws and a second name those claws and arm them.
        """
        return [node for node in self.all_nodes() if node.is_weapon_profile]

    def find(self, name):
        """First node whose display name matches — for tests and lookups."""
        return next((n for n in self.all_nodes() if n.name == name), None)

    def model_matchable(self):
        """The model as selector food: its entry, its type, its subtypes
        and the specialisation it chose.

        The **base** adapter: printed facts — stored assignments — only.
        During ``compute`` each round layers what earlier rounds settled on
        top of this (``n26.effects._Facts``), so a filtered scope sees
        unconditional grants; ``usability_for`` layers the final state the
        same way. Called bare, it answers from the assignments alone.

        A specialisation counts as a possession for the same reason a
        subtype does: "(Gunner specialist only)" asks what this fighter
        *is*, and what they chose says so.
        """
        from n26.core import select
        from n26.library.models import Counter, Specialisation, Subtype

        profile = None
        possessions = []
        counts = []
        for node in self.all_nodes():
            if node.broadcast:
                # The gang-hosted assignments ride the card for their
                # effects; they are not facts about this model.
                continue
            if node.suppressed:
                # Taken away, so no longer a fact about anyone: a rule
                # reaching Leaders must not reach a fighter whose Leader
                # assignment something cancelled.
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
    """The gang's own card: what *it* holds, as first-class assignments.

    The same assignments ride every member's card marked ``broadcast`` so
    gang-wide modifiers reach the fighters; here they are the content.
    Everything a test wants to say about the gang as a thing — its founding
    assignment, its house list, its choice slots, its stash — asserts
    against this structure and the ``ComputedGang`` built from it
    (design/gang-sheet.md); renderables derive from those.
    """

    gang: object
    #: Gang-hosted assignment trees: the founding, the house list, rules,
    #: counters, choice slots and what was chosen for them.
    roots: list[Node] = field(default_factory=list)
    #: Stash-hosted trees. On the card so the sheet can draw them,
    #: but not in ``all_nodes()``: nothing in the stash is a fact about
    #: the gang, and nothing in it computes (design/gang-sheet.md,
    #: out of scope until something needs it).
    stash_roots: list[Node] = field(default_factory=list)
    #: Every member's ``Card``, keyed by miniature id, from the same
    #: fetch family — so a whole sheet stays a fixed number of queries.
    members: dict = field(default_factory=dict)
    #: Lines a modifier granted, as on a model's card. A gang is handed
    #: nothing today — a granted weapon goes to whoever carries it — but
    #: both card kinds are computed by one function, and one that read
    #: its own grants on one card and not the other would be a trap.
    granted: list[Node] = field(default_factory=list)
    #: The flat assignments each member's card was dealt from, kept so a
    #: selection can re-deal the cards without another fetch — see
    #: ``members_under``.
    member_rows: dict = field(default_factory=dict, repr=False)
    #: The gang-hosted assignments that ride every member's card as
    #: broadcast.
    shared_rows: list = field(default_factory=list, repr=False)
    #: What each member's owner set by hand, keyed by model id, so a
    #: re-deal under a selection carries the settings without a second
    #: fetch.
    stat_overrides: dict = field(default_factory=dict, repr=False)
    #: What the gang holds by grant rather than by assignment, worked out
    #: on the first compute of this card and kept: every member's card asks
    #: the same question of the same assignments, so the answer is the same
    #: for all of them. None until something asks.
    acquired: tuple | None = field(default=None, repr=False)

    host_kind = GANG

    @property
    def stash_rating(self):
        return sum(node.rating_with_extras for node in self.stash_roots)

    def members_under(self, assignment_set):
        """Every member's card re-dealt under a selection — in memory.

        The assignments are already on this card; only the assembly differs, so
        a print run's ticked weapons never pay for a second fetch. With
        no selection the cards as dealt are the answer.
        """
        if assignment_set is None:
            return self.members
        return {
            miniature_id: assemble(
                None,
                rows,
                assignment_set=assignment_set,
                broadcast=self.shared_rows,
                gang_card=self,
                stat_overrides=self.stat_overrides.get(miniature_id, {}),
            )
            for miniature_id, rows in self.member_rows.items()
        }

    def all_nodes(self):
        for root in (*self.roots, *self.granted):
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
        subtypes, so its facts are simply its own assignments, which is what a
        ``Has(house list)`` or a gang-level ``CounterAtLeast`` asks about.
        """
        from n26.core import select
        from n26.library.models import Counter

        possessions = []
        counts = []
        for node in self.all_nodes():
            if node.suppressed:
                continue
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


def _flat_rows(**filters):
    """The bare assignment fetch a card build starts from — one query.

    Only the money rides the join: every build reads each assignment's
    ledger entry and the table is narrow. The assignable an assignment
    names is loaded afterwards, in narrow passes — see ``hydrate_rows``.
    """
    return list(
        Assignment.objects.filter(archived=False, **filters).select_related(
            "ledger_entry"
        )
    )


def hydrate_rows(rows, with_statlines=False, with_options=False):
    """Load everything a card build reads off ``rows`` — narrow passes,
    never a wide join.

    Joined, the assignable kinds and their chains make a select so wide
    that Postgres spends tens of milliseconds *planning* it and one
    executing it — and with no prepared statements the planning is paid
    on every query. As narrow prefetches each pass plans in microseconds,
    a kind no assignment names never queries at all, and two lists of
    assignments hydrated together pay once.

    ``with_statlines`` pulls each profile's characteristics along too,
    which rendering needs and plain assignment work does not.

    ``with_options`` pulls what each copy was bought with — the sets
    recorded against it and the offer they were picked from. Only the
    screens that name a copy's options ask for it: a printed sheet says
    what a fighter carries and never how it was chosen, and would pay
    these passes for an answer it does not print.
    """
    from django.db.models import prefetch_related_objects

    paths = [
        *ASSIGNABLE_FIELDS,
        "profile_role",
        "counter_value",
        "profile__profile_type",
        # A chosen-mode placement reads the chosen token's home off
        # the assignment already in memory — never by a query.
        "skill_tree__category",
        # A firing line's home is its gun's, so a scope narrowed to a
        # category asks each profile for its weapon. Without this the
        # asking is a query per profile, from inside compute.
        "weapon_profile__weapon",
    ]
    if with_statlines:
        paths += [
            "profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__traits",
            # The shape a statline is drawn to, which is the type's and not
            # the stored values'. Without these, padding a statline short of
            # a stat asks its type for the full set — a query per profile.
            "profile__profile_type__statline_type__stats__stat",
            "weapon_profile__weapon__statline_type__stats__stat",
        ]
    if with_options:
        paths += ["chosen_options", *(f"wargear__{p}" for p in OPTION_OFFER_PATHS)]
    prefetch_related_objects(rows, *paths)
    return rows


def set_by_hand(**filters):
    """The characteristics owners have set themselves, by model and cell.

    ``{model id: {statline cell id: value}}`` — one query for however
    many models the filter reaches, so a whole gang's settings cost what
    one model's does. A blank is not a setting: the cell falls back to
    what the model's entry prints.
    """
    from n26.core.models import StatOverride

    grouped = {}
    for row in StatOverride.objects.filter(**filters):
        if row.value:
            grouped.setdefault(row.miniature_id, {})[row.statline_type_stat_id] = (
                row.value
            )
    return grouped


def card_rows(with_statlines=False, with_options=False, **filters):
    """The flat fetch every card build starts from: one assignment query,
    hydrated. Builds fetching more than one list of assignments hydrate
    them together instead — one pass covers any number of fetches.
    """
    return hydrate_rows(
        _flat_rows(**filters), with_statlines=with_statlines, with_options=with_options
    )


def gang_rows(gang):
    """What the gang itself holds, bare: its founding, and what that
    brought.

    Hosted on the gang with no model of their own, so they belong to
    every member's card and to none of their ratings. Hydrate with the
    rest of the build's assignments — see ``hydrate_rows``.
    """
    if gang is None:
        return []
    return _flat_rows(
        gang_root=gang,
        miniature_root__isnull=True,
        # The stash is the gang's too, but it is storage, not a fact
        # about every member — nothing in it may broadcast onto cards.
        stash_root__isnull=True,
    )


def assemble(
    miniature,
    rows,
    assignment_set=None,
    broadcast=(),
    gang_card=None,
    stat_overrides=None,
):
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
    card = Card(
        miniature=miniature,
        roots=roots,
        gang_card=gang_card,
        stat_overrides=stat_overrides or {},
    )
    # Only what the model owns. The gang-hosted assignments ride the card
    # so their modifiers reach it; they are not part of what it is worth.
    card.full_rating = sum(
        row.ledger_entry.rating_contribution
        for row in rows
        if getattr(row, "ledger_entry", None)
    )
    return card


def build_card(
    miniature, with_statlines=False, assignment_set=None, with_options=False
):
    """A model's card: everything it owns, or one named selection.

    Two assignment queries rather than one — the model's own, then the
    gang's, which ride along so gang-wide modifiers reach this card —
    hydrated together in one pass. A whole gang's worth still costs a
    fixed number — see ``build_cards_for_gang``, where both come back
    in the same fetch.

    The gang-hosted assignments are also assembled into the gang's own
    card and carried on this one, so that what the gang holds by grant
    reaches this model too. No further fetch: they are the ones already
    in hand.
    """
    membership = miniature.membership if miniature is not None else None
    gang = membership.gang if membership else None
    own = _flat_rows(miniature_root=miniature)
    shared = gang_rows(gang)
    hydrate_rows(
        [*own, *shared], with_statlines=with_statlines, with_options=with_options
    )
    return assemble(
        miniature,
        own,
        assignment_set=assignment_set,
        broadcast=shared,
        gang_card=(
            None
            if gang is None
            else GangCard(gang=gang, roots=_forest(shared), shared_rows=shared)
        ),
        stat_overrides=(
            set_by_hand(miniature=miniature).get(miniature.pk, {})
            if with_statlines and miniature is not None
            else {}
        ),
    )


def build_cards_for_gang(gang, with_statlines=True):
    """Every model's card in the gang, keyed by model id — one flat fetch.

    The gang's own assignments come back in the same query (they share a
    ``gang_root``) and are handed to every model's card rather than
    thrown away, which is what makes the broadcast free here.
    """
    return build_gang_card(gang, with_statlines=with_statlines).members


def _forest(rows):
    """Trees from a flat list of assignments, parents resolved in memory."""
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


def build_gang_card(gang, with_statlines=True, assignment_set=None, with_options=False):
    """The gang's own card, its stash, and every member's card.

    The same fetch family as ever: one assignment query for everything
    hosted on the gang except the stash, plus one for its contents — kept
    apart because the stash's assignments belong on no member's card and
    nothing in them broadcasts (storage, not facts about anyone) — then
    one shared hydration pass over both.

    An ``assignment_set`` filters every member's card through the same
    seam ``build_card`` uses — a selection of equipment roots that may
    span the whole gang, as a print run's ticked weapons do.
    """
    grouped = {}
    shared = []
    rows = _flat_rows(gang_root=gang, stash_root__isnull=True)
    # The stash's assignments ride the same hydration pass as everyone's
    # — a second pass would repeat every narrow query for a handful.
    stash_rows = _flat_rows(gang_root=gang, stash_root__isnull=False)
    hydrate_rows(
        [*rows, *stash_rows], with_statlines=with_statlines, with_options=with_options
    )
    for row in rows:
        if row.miniature_root_id is None:
            shared.append(row)
        else:
            grouped.setdefault(row.miniature_root_id, []).append(row)
    card = GangCard(
        gang=gang,
        roots=_forest(shared),
        stash_roots=_forest(stash_rows),
        member_rows=grouped,
        shared_rows=shared,
        # One query for the whole roster's settings, dealt out below —
        # asking model by model is how a gang's budget starts growing
        # with the number of models in it.
        stat_overrides=(
            set_by_hand(miniature__membership__gang=gang) if with_statlines else {}
        ),
    )
    # Every member's card carries the gang's, so what the gang holds by
    # grant is dealt onto all of them from one computation of it.
    card.members = {
        miniature_id: assemble(
            None,
            rows,
            assignment_set=assignment_set,
            broadcast=shared,
            gang_card=card,
            stat_overrides=card.stat_overrides.get(miniature_id, {}),
        )
        for miniature_id, rows in grouped.items()
    }
    return card


def build_card_from_profile(profile, option=None, base=None):
    """The card a hire *would* produce, built from library alone.

    No gang, no model, no assignments: this is what a player sees while
    deciding. It mirrors ``Operation.hire`` exactly — the built-ins, then
    every set the selection takes (each one-of group's head unless named),
    each member caused by the profile, weapons carrying their free
    profiles and bundled ammo hanging off its weapon — so a preview and
    the thing you get are the same card.

    ``base`` replaces the profile's *own* price, which is what a
    collection's override means: a list offering a Chaos Spawn at 90 has
    not made its weapon swaps free. Everything the hire comes with keeps
    its own price, so the card's rating composes exactly as it does at
    reference.
    """
    from n26.library.models import Weapon, WeaponProfile

    taken = profile.resolve_selection(option)
    counter = iter(range(1, 10_000))

    root = Node(
        assignable=profile,
        key=next(counter),
        rating=profile.price_with(taken, base=base),
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
                # A counter's opening value — Starting XP — so the preview
                # says what the hire will write.
                opens_at=member.amount,
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

    A fixed number of queries regardless of how many models or how much
    kit: one narrow query per assignable kind per level, then one small
    query per relation the modifiers' sentences read. ``compute`` then
    runs entirely off this, touching the database not at all.
    """
    from django.db.models import Prefetch, prefetch_related_objects

    from n26.library.models import CounterAtLeast
    from n26.library.models.modifier import (
        COUNTABLE_FIELDS,
        EFFECT_FIELDS,
        GRANTABLE_FIELDS,
        SCOPE_FIELDS,
    )

    related = (
        *SCOPE_FIELDS,
        *EFFECT_FIELDS,
        # Without these, naming a choice's kind or a placed category
        # queries once per slot or placement.
        "offers_choice__of_kind",
        "places_category__category",
        "places_category__section__collection",
        "requires_companions__for_each",
        "requires_companions__of",
        *(f"allows_at_most__{name}" for name in COUNTABLE_FIELDS),
        *(f"adds_assignable__{name}" for name in GRANTABLE_FIELDS),
        *(f"removes_assignable__{name}" for name in GRANTABLE_FIELDS),
        "changes_stat__stat",
    )
    #: Condition rows are reverse relations, so they cannot ride
    #: select_related — without these a scope's narrowing costs a query
    #: per card to learn who it reaches.
    also_prefetch = (
        "targets_miniature__has_subtypes__subtypes",
        "targets_miniature__is_profile__profiles",
        Prefetch(
            "targets_miniature__counter_at_least",
            queryset=CounterAtLeast.objects.select_related("counter"),
        ),
        "targets_weapons__has_traits__traits",
        "targets_weapons__in_categories__categories",
        "targets_weapons__is_one_of__weapons",
        # A granted weapon is put on the card as lines, statlines and all,
        # by ``compute``, which may not query. Its firing lines and what
        # they are printed with therefore have to be here.
        "adds_assignable__weapon__profiles__traits",
        "adds_assignable__weapon__profiles__statline__stats__statline_type_stat__stat",
        "adds_assignable__weapon__statline_type__stats__stat",
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

        # The attachment rows first — one narrow query per kind, onto the
        # objects we already hold. What the modifiers' halves read is then
        # hydrated once, over the distinct modifiers of the whole level:
        # a small query per path. Joining every path into each kind's
        # fetch instead would make a many-join select whose *planning*
        # costs more than all of these run in.
        for things in by_model.values():
            prefetch_related_objects(things, "modifiers")
        hydrated = {}
        for things in by_model.values():
            for thing in things:
                for modifier in thing.modifiers.all():
                    hydrated.setdefault(modifier.pk, modifier)
        prefetch_related_objects(list(hydrated.values()), *related, *also_prefetch)

        granted = []
        for things in by_model.values():
            for thing in things:
                # A carrier reached from two kinds must resolve to the one
                # hydrated instance, or the other copy answers compute
                # with the lazy queries it is forbidden to make.
                modifiers = [hydrated[m.pk] for m in thing.modifiers.all()]
                index.add(thing, modifiers)
                for modifier in modifiers:
                    granted_thing = getattr(modifier.effect, "thing", None)
                    if granted_thing is not None:
                        granted.append(granted_thing)
        frontier = granted

    return index
