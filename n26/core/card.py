"""Load model cards as assignment trees with a fixed query budget.

Fetch assignments flat using their denormalised roots, then assemble the
parent tree in memory. ``hydrate_rows`` loads content in narrow passes:
a join across every content kind adds substantial PostgreSQL planning time.
Node properties read the loaded assignments without additional queries.

Gang builds share hydration across all cards, keeping query count fixed
as the roster and its equipment grow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from n26.core.effects import ModifierIndex, is_orphan_pick
from n26.core.models import Assignment, Reason
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.library.models.assignable import Family, Optioned
from n26.library.models.modifier import GANG, MODEL

#: Gear kinds whose display reads a category. Join the category during
#: hydration to avoid queries while rendering.
GEAR_WITH_A_CATEGORY = ("wargear", "weapon_accessory")


@dataclass
class Node:
    """A stored or preview assignable and its child nodes.

    Identity, rating, cause and role are available directly. ``assignment``
    is present for stored cards and absent for library-only hire previews.
    """

    assignable: object
    #: Assignment primary key, or a generated preview key. Compare only
    #: within the same card.
    key: object
    children: list[Node] = field(default_factory=list)
    #: What this line contributes on its own.
    rating: int = 0
    #: The key of the node that brought this one, if any.
    caused_by_key: object = None
    #: Source assignment key for this pick's choice.
    chosen_for_key: object = None
    #: Slot identity distinguishes multiple choices from the same source.
    chosen_for_slot_id: object = None
    chosen_for_status_revision: int | None = None
    #: A holding-origin choice names the holding and its ownership period,
    #: rather than an assignment that the gang does not own.
    chosen_for_holding_key: object = None
    chosen_for_holding_revision: int | None = None
    #: Offer identity for a modifier-provided choice. Without it, resolve
    #: by matching the selection against available offer selectors.
    chosen_for_offer_id: object = None
    #: The ledger's reason, for a line that has one.
    reason: str | None = None
    is_weapon_profile: bool = False
    #: A fighter profile — the hire, or a Venator's Legacy alongside it.
    is_profile: bool = False
    #: The one profile whose statline and type the card is drawn from.
    is_primary_profile: bool = False
    #: Gang-hosted node included on member cards so its modifiers can reach
    #: them. It contributes no member line or rating. Unlike Hidden content,
    #: its exclusion is determined by host rather than assignable kind.
    broadcast: bool = False
    #: Computed equipment has no stored assignment, payment or sale action.
    computed: bool = False
    #: The immediate grant source may itself have no node on this card.
    granted_by: str | None = None
    granted_by_kind: str | None = None
    #: A removal hides this unpaid assignment without changing storage.
    #: Removing the source restores the line on the next computation.
    suppressed: bool = False
    #: Counter opening value used by previews and written at hire.
    #: Stored cards read the value from the assignment instead.
    opens_at: int = 0
    #: Acquisition time, or None for library-only nodes. Stat limits apply
    #: in acquisition order, which can affect each change's contribution.
    acquired: object = None
    #: The stored assignment, when this card was built from stored ones.
    assignment: Assignment | None = None

    @property
    def name(self):
        return str(self.assignable)

    @property
    def rating_with_extras(self):
        """This node's rating plus its descendants' ratings."""
        return self.rating + sum(child.rating_with_extras for child in self.children)

    @property
    def carries_money(self):
        """Whether this node has payment or rating that prevents suppression.

        Stored nodes use paid credits, Trade Points and rating contribution from
        their ledger entry. Library-only previews use the node's rating.
        """
        entry = (
            getattr(self.assignment, "ledger_entry", None) if self.assignment else None
        )
        if entry is not None:
            return bool(entry.paid or entry.trade_points or entry.rating_contribution)
        return bool(self.rating)

    @property
    def paid_trade_points(self):
        """Whether this node or any descendant was bought with Trade Points.

        Used to offer refunds to gangs without a credit budget. Entries are
        already loaded, so traversing the subtree issues no queries. Library-only
        previews have no recorded payment.
        """
        return any(_paid_trade_points(node) for node in self.walk())

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def _paid_trade_points(node):
    """Whether Trade Points were handed over for this one line."""
    assignment = node.assignment
    entry = getattr(assignment, "ledger_entry", None) if assignment else None
    return entry is not None and bool(entry.trade_points)


def node_for(assignment):
    """A node describing one stored assignment."""
    entry = getattr(assignment, "ledger_entry", None)
    role = getattr(assignment, "profile_role", None)
    return Node(
        assignable=assignment.assignable,
        key=assignment.pk,
        rating=assignment.rating,
        caused_by_key=assignment.caused_by_id,
        chosen_for_key=assignment.chosen_for_id,
        chosen_for_slot_id=assignment.chosen_for_slot_id,
        chosen_for_status_revision=assignment.chosen_for_status_revision,
        chosen_for_holding_key=assignment.chosen_for_holding_id,
        chosen_for_holding_revision=assignment.chosen_for_holding_revision,
        chosen_for_offer_id=assignment.chosen_for_offer_id,
        reason=entry.reason if entry else None,
        is_weapon_profile=assignment.weapon_profile_id is not None,
        is_profile=assignment.profile_id is not None,
        is_primary_profile=(
            assignment.profile_id is not None
            and (role is None or role.role == "primary")
        ),
        acquired=assignment.created,
        assignment=assignment,
    )


@dataclass
class Card:
    miniature: object
    roots: list[Node] = field(default_factory=list)
    #: The whole pool's worth, whatever this card selects. The gang counts
    #: each purchase once; an equipment card shows only its selected kit.
    full_rating: int = 0
    #: Current and recorded hire contributions when a manual override remains.
    base_rating_override: tuple[int, int] | None = None

    #: Computed equipment, including free weapon profiles. ``compute``
    #: clears and rebuilds this output on each run. These nodes add no ledger
    #: entry or rating. Possession readers use roots; display readers use both.
    granted: list[Node] = field(default_factory=list)

    #: Owner overrides keyed by statline cell, loaded before rendering.
    #: Empty when statlines are omitted or the card is a library-only preview.
    stat_overrides: dict = field(default_factory=dict)

    #: Owner-authored removal assignments, excluded from the node tree.
    #: ``effects`` applies them as unconditional removals.
    removals: list = field(default_factory=list)

    #: The gang card supplies computed grants to member cards in addition
    #: to the gang-hosted broadcast nodes. It uses already fetched assignments.
    gang_card: object = None

    #: Current campaign holdings whose model-scoped modifiers reach this
    #: member. They add no equipment line or member rating.
    holdings: list = field(default_factory=list, repr=False)
    #: Batched cards carry two model facts without a separate roster query.
    #: A bound miniature supplies them instead, including preview projections.
    status: str | None = None
    status_revision: int = 0

    #: The host kind distinguishes model and gang targets during scoping.
    host_kind = MODEL

    @property
    def rating(self):
        """Everything on *this* card. For an unfiltered card this equals
        ``full_rating``; for a named selection it may be less."""
        return sum(node.rating_with_extras for node in self.roots if not node.broadcast)

    @property
    def current_status(self):
        return getattr(self.miniature, "status", self.status)

    @property
    def current_status_revision(self):
        return getattr(self.miniature, "status_revision", self.status_revision)

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
        """Expose stored model facts to selectors before computed effects.

        Include the primary profile and type, live subtypes, counters and picks.
        Exclude suppressed nodes and orphan picks. Gang-held picks count as facts
        about every member; other broadcast assignments do not.

        ``n26.core.effects._Facts`` adds earlier rounds' results during computation;
        ``usability_for`` adds the final computed state for access checks.
        """
        from n26.core import select
        from n26.library.models import Counter, Pickable, Subtype

        profile = None
        possessions = []
        counts = []
        for node in self.all_nodes():
            if node.suppressed:
                # Suppressed assignments cannot satisfy model selectors.
                continue
            if is_orphan_pick(node):
                continue
            if node.broadcast and not isinstance(node.assignable, Pickable):
                # Broadcast assignments supply effects without becoming model facts.
                continue
            if node.is_primary_profile:
                profile = node.assignable
                possessions.append(profile.profile_type)
            elif isinstance(node.assignable, (Subtype, Pickable)):
                possessions.append(node.assignable)
            elif isinstance(node.assignable, Counter):
                held = (
                    getattr(node.assignment, "counter_value", None)
                    if node.assignment is not None
                    else None
                )
                counts.append(
                    (
                        select.key(node.assignable),
                        max(
                            node.assignable.minimum,
                            held.value if held else node.opens_at,
                        ),
                    )
                )
        base = select.matchable(profile, assignables=possessions)
        return select.Matchable(
            thing=base.thing,
            assignables=base.assignables,
            counts=tuple(counts),
            status=self.current_status,
        )


@dataclass
class GangCard:
    """The gang's own assignments, stash and member cards.

    Gang-hosted assignments also appear as broadcast nodes on member cards
    so their modifiers can affect fighters. ``ComputedGang`` and render
    structures derive from this card. See ``design/gang-sheet.md``.
    """

    gang: object
    #: Gang-hosted assignment trees: the founding, the house list, rules,
    #: counters, choice slots and what was chosen for them.
    roots: list[Node] = field(default_factory=list)
    #: Stash contents are available for display but excluded from all_nodes:
    #: stored equipment contributes no gang facts or computed effects.
    stash_roots: list[Node] = field(default_factory=list)
    #: Every member's ``Card``, keyed by miniature id, from the same
    #: fetch family — so a whole sheet stays a fixed number of queries.
    members: dict = field(default_factory=dict)
    #: Computed grant output, sharing the fighter card interface used by
    #: ``compute``.
    granted: list[Node] = field(default_factory=list)
    #: Retain loaded assignments to rebuild selections without refetching.
    #: See ``members_under``.
    member_rows: dict = field(default_factory=dict, repr=False)
    #: Gang-hosted assignments broadcast to every member.
    shared_rows: list = field(default_factory=list, repr=False)
    #: Owner overrides keyed by model ID, retained when rebuilding selections.
    stat_overrides: dict = field(default_factory=dict, repr=False)
    #: Settled gang grants, cached on first computation and shared by all
    #: member cards. None until computed.
    acquired: tuple | None = field(default=None, repr=False)
    #: Current campaign holdings. These are modifier carriers rather than
    #: assignment nodes and contribute no gang rating.
    holdings: list = field(default_factory=list, repr=False)

    host_kind = GANG

    @property
    def stash_rating(self):
        return sum(node.rating_with_extras for node in self.stash_roots)

    def members_under(self, assignment_set):
        """Reassemble member cards under an equipment selection without refetching.

        Return the existing cards when no selection is supplied.
        """
        if assignment_set is None:
            return self.members
        return {
            miniature_id: assemble(
                None,
                rows,
                status=self.members[miniature_id].current_status,
                status_revision=self.members[miniature_id].current_status_revision,
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
        """Expose the gang's held assignables and counter values to selectors.

        Gang selectors use all live, non-orphan assignments rather than the
        fighter-specific profile and subtype policy.
        """
        from n26.core import select
        from n26.library.models import Counter

        possessions = []
        counts = []
        for node in self.all_nodes():
            if node.suppressed or is_orphan_pick(node):
                continue
            possessions.append(node.assignable)
            if isinstance(node.assignable, Counter):
                held = (
                    getattr(node.assignment, "counter_value", None)
                    if node.assignment is not None
                    else None
                )
                counts.append(
                    (
                        select.key(node.assignable),
                        max(
                            node.assignable.minimum,
                            held.value if held else node.opens_at,
                        ),
                    )
                )
        base = select.matchable(self.gang, assignables=possessions)
        return select.Matchable(
            thing=base.thing, assignables=base.assignables, counts=tuple(counts)
        )


def advancement_rated():
    """Whether an advancement added an assignment's rating contribution.

    An advancement records the assignments it made. A clone has no such
    record, so its ledger entry carries the answer copied from the source.
    """
    from django.db.models import Exists, OuterRef, Q

    from n26.core.models import AdvancementSelection

    return Q(ledger_entry__cloned_from_advancement=True) | Exists(
        AdvancementSelection.objects.filter(
            Q(pick_assignment_id=OuterRef("pk"))
            | Q(promotion_assignment_id=OuterRef("pk"))
        )
    )


def _flat_rows(*, with_status=False, **filters):
    """Fetch assignments and their ledger entries in one query.

    Batch builds also join membership status. Load assignables separately
    through ``hydrate_rows`` to avoid a wide join.
    """
    from django.db.models import Case, F, OuterRef, Subquery, Sum, When
    from django.db.models.functions import Coalesce

    from n26.core.models import LedgerEvent

    overrides = (
        LedgerEvent.objects.filter(
            assignment_id=OuterRef("pk"),
            kind__in=[LedgerEvent.Kind.RATING_SET, LedgerEvent.Kind.RATING_RESET],
        )
        .order_by()
        .values("assignment_id")
        .annotate(total=Sum("rating_delta"))
        .values("total")
    )
    rows = Assignment.objects.filter(archived=False, **filters)
    if with_status:
        # Only the membership row joins a model; two scalar facts keep the
        # batched card usable without loading a second roster.
        rows = rows.annotate(
            member_status=F("member__status"),
            member_status_revision=F("member__status_revision"),
        )
    return list(
        rows.select_related("ledger_entry").annotate(
            rating_from_advancement=advancement_rated(),
            base_rating_override_delta=Case(
                When(
                    gang__isnull=False,
                    profile__isnull=False,
                    miniature_root__isnull=False,
                    then=Coalesce(Subquery(overrides), 0),
                ),
                default=0,
            ),
        )
    )


def rating_assignments(miniature):
    """Recorded rating contributions without loading the library content."""
    return _flat_rows(miniature_root=miniature, removes=False)


def hydrate_rows(rows, with_statlines=False, with_options=False):
    """Load assignment content through narrow, batched prefetches.

    Each present assignable kind uses a separate query, avoiding PostgreSQL's
    planning overhead for joins across every kind. Hydrate combined assignment
    lists together so they share these passes.

    ``with_statlines`` loads characteristic values needed for rendering.
    ``with_options`` loads the selected sets and offers needed by screens
    that describe purchase options. Printed sheets can omit those queries.
    """
    from django.apps import apps
    from django.db.models import Prefetch, prefetch_related_objects

    paths = [
        *ASSIGNABLE_FIELDS,
        "profile_role",
        "counter_value",
        "profile__profile_type",
        # Load chosen categories and slot types before query-free computation.
        "asset__asset_type",
        "asset__base_income_modifier",
        "pickable__category",
        "pickable__slot_type",
        # Choice notes read the slot type's repeat policy without querying.
        # The picker also needs the preloaded picklist.
        "slot__slot_type",
        "slot__picklist",
        "action__usable_by_profile_types",
        "action__usable_by_subtypes",
        "action__usable_by_profiles",
        # Weapon-scoped category selectors need each profile's weapon preloaded.
        "weapon_profile__weapon",
    ]
    # These Gear kinds read category display settings. Join the category
    # within their hydration pass instead of querying it per card.
    paths = [
        Prefetch(
            field,
            queryset=apps.get_model(ASSIGNABLE_FIELDS[field]).objects.select_related(
                # Category ordering reads its section's name; preload sections to avoid
                # one query per category.
                "category__section",
            ),
        )
        if field in GEAR_WITH_A_CATEGORY
        else field
        for field in paths
    ]
    if with_statlines:
        paths += [
            "profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__statline__stats__statline_type_stat__stat",
            "weapon_profile__traits",
            # Preload all type stats so incomplete statlines can be padded without
            # querying per profile.
            "profile__profile_type__statline_type__stats__stat",
            "weapon_profile__weapon__statline_type__stats__stat",
        ]
    if with_options:
        paths += ["chosen_options", *_option_offer_paths()]
    prefetch_related_objects(rows, *paths)
    return rows


def _option_offer_paths():
    """Discover option-offer prefetch paths from the library's families.

    Only possession kinds need these paths. Selected set IDs are already
    available on option records, so the sets themselves need no prefetch.
    """
    for name in ASSIGNABLE_FIELDS:
        kind = Assignment._meta.get_field(name).related_model
        if issubclass(kind, Optioned) and getattr(kind, "family", None) == Family.GEAR:
            yield f"{name}__options__group"


def set_by_hand(**filters):
    """Load characteristic overrides as ``{model ID: {cell ID: value}}``.

    One query covers every matching model. Empty values fall back to the
    profile's printed characteristic.
    """
    from n26.core.models import StatOverride

    grouped = {}
    for row in StatOverride.objects.filter(**filters):
        if row.value:
            grouped.setdefault(row.miniature_id, {})[row.statline_type_stat_id] = (
                row.value
            )
    return grouped


def card_rows(with_statlines=False, **filters):
    """The flat fetch every card build starts from: one assignment query,
    hydrated. Builds fetching more than one list of assignments hydrate
    them together instead — one pass covers any number of fetches.
    """
    return hydrate_rows(_flat_rows(**filters), with_statlines=with_statlines)


def gang_rows(gang):
    """Fetch gang-hosted assignments without hydrating them.

    Their modifiers can affect every member, but they contribute no member
    rating. Hydrate them with the rest of the build's assignments.
    """
    if gang is None:
        return []
    return _flat_rows(
        gang_root=gang,
        miniature_root__isnull=True,
        # Stash equipment must not broadcast modifiers to member cards.
        stash_root__isnull=True,
    )


def held_assets(gang):
    """Load this gang's current campaign holdings and their content in one query.

    A holding counts only while its membership remains open, even if the
    asset still references a closed membership.
    """
    from n26.core.models import CampaignAsset

    if gang is None:
        return []
    return list(
        CampaignAsset.objects.filter(
            holder__gang=gang, holder__left__isnull=True
        ).select_related("asset__asset_type", "income_override__contributes_to_counter")
    )


def _without_inactive_holding_choices(rows, holdings):
    """Keep choices from current ownership periods and their ordinary trees.

    A lost or deleted holding cannot leave an active answer behind, even if
    its archival write has not reached this fetch. The preloaded holdings
    supply the whole lifetime check; reading a choice never follows its FK.
    """
    held = {(holding.pk, holding.ownership_revision) for holding in holdings}
    dropped = {
        row.pk
        for row in rows
        if (
            row.chosen_for_holding_id is not None
            or row.chosen_for_holding_revision is not None
        )
        and (row.chosen_for_holding_id, row.chosen_for_holding_revision) not in held
    }
    if not dropped:
        return rows
    changed = True
    while changed:
        changed = False
        for row in rows:
            if row.pk not in dropped and (
                row.parent_id in dropped
                or row.caused_by_id in dropped
                or row.chosen_for_id in dropped
            ):
                dropped.add(row.pk)
                changed = True
    return [row for row in rows if row.pk not in dropped]


def assemble(
    miniature,
    rows,
    assignment_set=None,
    broadcast=(),
    gang_card=None,
    stat_overrides=None,
    status=None,
    status_revision=0,
):
    """Assemble loaded assignments into a card's parent tree.

    An ``assignment_set`` may query its selection. Exclude unselected equipment
    roots and their descendants; retain profiles, subtypes, skills and injuries.
    """
    holdings = list(gang_card.holdings) if gang_card is not None else []
    active = {
        row.pk
        for row in _without_inactive_holding_choices([*rows, *broadcast], holdings)
    }
    rows = [row for row in rows if row.pk in active]
    broadcast = [row for row in broadcast if row.pk in active]
    # Extract removals before applying the equipment selection, which must
    # not restore suppressed facts.
    removals = [row for row in rows if row.removes]
    kept = [row for row in rows if not row.removes]
    rows = kept
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
        status=status,
        status_revision=status_revision,
        roots=roots,
        gang_card=gang_card,
        stat_overrides=stat_overrides or {},
        removals=removals,
        holdings=holdings,
    )
    # Exclude broadcast gang assignments from member rating.
    card.full_rating = sum(
        row.ledger_entry.rating_contribution
        for row in rows
        if getattr(row, "ledger_entry", None)
    )
    for row in rows:
        if not row.gang_id or not row.miniature_root_id or not row.profile_id:
            continue
        delta = getattr(row, "base_rating_override_delta", 0)
        if delta:
            current = row.ledger_entry.rating_contribution
            card.base_rating_override = (current, current - delta)
            break
    return card


def build_card(
    miniature, with_statlines=False, assignment_set=None, with_options=False
):
    """Build one model's card, optionally filtering its equipment selection.

    Fetch the model's assignments and the gang's assignments separately,
    then hydrate them together. Load campaign holdings in another query.
    Assemble the gang's own card from the same assignments so its computed
    grants can affect the model without another fetch.
    """
    membership = miniature.membership if miniature is not None else None
    gang = membership.gang if membership else None
    own = _flat_rows(miniature_root=miniature)
    shared = gang_rows(gang)
    holdings = held_assets(gang)
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
            else GangCard(
                gang=gang,
                roots=_forest(shared, holdings),
                shared_rows=shared,
                holdings=holdings,
            )
        ),
        stat_overrides=(
            set_by_hand(miniature=miniature).get(miniature.pk, {})
            if with_statlines and miniature is not None
            else {}
        ),
    )


def build_cards_for_gang(gang, with_statlines=True):
    """Build member cards keyed by model ID from one assignment fetch.

    Gang-hosted assignments share ``gang_root`` and become broadcast nodes
    on every member card without another assignment query.
    """
    return build_gang_card(gang, with_statlines=with_statlines).members


def _forest(rows, holdings=()):
    """Trees from a flat list of assignments, parents resolved in memory."""
    rows = _without_inactive_holding_choices(rows, holdings)
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


def build_gang_card(gang, with_statlines=True, assignment_set=None):
    """Build the gang card, stash and member cards with shared hydration.

    Fetch roster and gang-hosted assignments together, with stash contents
    separate so stored equipment cannot broadcast modifiers to fighters.
    Load campaign holdings separately because they are not assignments.

    ``assignment_set`` filters equipment roots through the same assembly
    path as ``build_card`` and may span several models.
    """
    grouped = {}
    shared = []
    rows = _flat_rows(gang_root=gang, stash_root__isnull=True, with_status=True)
    # Hydrate stash and roster assignments together to share narrow queries.
    stash_rows = _flat_rows(gang_root=gang, stash_root__isnull=False)
    hydrate_rows([*rows, *stash_rows], with_statlines=with_statlines)
    holdings = held_assets(gang)
    active = {
        row.pk
        for row in _without_inactive_holding_choices([*rows, *stash_rows], holdings)
    }
    rows = [row for row in rows if row.pk in active]
    stash_rows = [row for row in stash_rows if row.pk in active]
    for row in rows:
        if row.miniature_root_id is None:
            shared.append(row)
        else:
            grouped.setdefault(row.miniature_root_id, []).append(row)
    card = GangCard(
        gang=gang,
        roots=_forest(shared, holdings),
        stash_roots=_forest(stash_rows, holdings),
        member_rows=grouped,
        shared_rows=shared,
        holdings=holdings,
        # Load every model's overrides together to keep the query count fixed.
        stat_overrides=(
            set_by_hand(miniature__membership__gang=gang) if with_statlines else {}
        ),
    )
    # All member cards share one computation of gang grants.
    statuses = {
        row.miniature_root_id: (row.member_status, row.member_status_revision)
        for row in rows
        if row.member_status is not None
    }
    card.members = {
        miniature_id: assemble(
            None,
            rows,
            status=statuses.get(miniature_id, (None, 0))[0],
            status_revision=statuses.get(miniature_id, (None, 0))[1],
            assignment_set=assignment_set,
            broadcast=shared,
            gang_card=card,
            stat_overrides=card.stat_overrides.get(miniature_id, {}),
        )
        for miniature_id, rows in grouped.items()
    }
    return card


def build_gang_cards(gangs, holdings):
    """Build gang-hosted cards for several gangs with a fixed query count.

    Campaign tables need gang counters, grants and holdings without member
    cards. Fetch all gang-hosted assignments together and share hydration and
    the modifier index across their computations.

    ``holdings`` maps gang IDs to assets already loaded by the caller.
    An absent gang ID means that gang holds no assets.
    """
    by_gang = {gang.pk: gang for gang in gangs}
    if not by_gang:
        return {}
    rows = _flat_rows(
        gang_root__in=list(by_gang),
        miniature_root__isnull=True,
        stash_root__isnull=True,
    )
    hydrate_rows(rows)
    theirs = {pk: [] for pk in by_gang}
    for row in rows:
        theirs[row.gang_root_id].append(row)
    return {
        pk: GangCard(
            gang=gang,
            roots=_forest(theirs[pk], holdings.get(pk, ())),
            shared_rows=theirs[pk],
            holdings=list(holdings.get(pk, ())),
        )
        for pk, gang in by_gang.items()
    }


def build_card_from_profile(profile, option=None, base=None):
    """Preview the card a hire would create, using library content only.

    Mirror ``Operation.hire``: include built-ins and selected option sets,
    using each one-of group's default when no selection is given. Attach
    free weapon profiles and bundled ammunition to their weapons.

    ``base`` overrides only the profile's own price. Built-ins and selected
    options retain their prices when computing the preview's rating.
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
    #: Weapon nodes keyed by set member, keeping identical weapons distinct
    #: for anchored ammunition.
    member_guns = {}
    #: Newest node per weapon type for ammunition without a member anchor.
    latest_guns = {}
    ammo = []

    for default_set in (profile.built_ins, *taken):
        if default_set is None:
            continue
        for member in default_set.members.all():
            # Filter in memory to retain the hire list's prefetched members.
            if member.archived:
                continue
            assignable = member.assignable
            if assignable is None:
                continue
            if isinstance(assignable, WeaponProfile):
                ammo.append(member)
                continue
            node = Node(
                assignable=assignable,
                key=next(counter),
                caused_by_key=root.key,
                reason=Reason.DEFAULT,
                # Preview the counter value that hire will write.
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
                member_guns[member.pk] = node
                latest_guns[assignable.pk] = node
            roots.append(node)
            if member.default_pickable_id is not None:
                # Preview the starting pick that hire will write.
                roots.append(
                    Node(
                        assignable=member.default_pickable,
                        key=next(counter),
                        caused_by_key=node.key,
                        chosen_for_key=node.key,
                        chosen_for_slot_id=assignable.pk,
                        reason=Reason.DEFAULT,
                    )
                )

    # Attach ammunition after all selected weapons exist. Prefer its named
    # weapon member, otherwise the newest matching weapon.
    for member in ammo:
        weapon_profile = member.assignable
        if member.gun_member_id is not None:
            host = member_guns.get(member.gun_member_id)
        else:
            host = latest_guns.get(weapon_profile.weapon_id)
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
    # The preview prices the package; a stored hire records that rating
    # on its membership while included assignments remain free.
    card.full_rating = root.rating
    return card


def build_modifier_index(assignables, max_depth=3):
    """Load modifiers and recursively granted content before computation.

    Each level uses one narrow query per assignable kind, plus queries for
    relations used by modifiers. ``compute`` then runs without database access.
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
        "offers_choice__power_access_collection",
        "places_category__category",
        "hides_categories__collection",
        "randomises_skill_advancements__from_section__collection",
        "places_category__section__collection",
        "requires_companions__for_each",
        "requires_companions__of",
        *(f"allows_at_most__{name}" for name in COUNTABLE_FIELDS),
        *(f"adds_assignable__{name}" for name in GRANTABLE_FIELDS),
        # A granted slot's starting pick is also a modifier carrier.
        "adds_assignable__with_pick",
        *(f"removes_assignable__{name}" for name in GRANTABLE_FIELDS),
        "changes_stat__stat",
        "contributes_to_counter__counter",
        "contributes_to_counter__per_counter",
        "excludes_campaign_assets__asset_type",
        "adds_assignable__asset__asset_type",
        "removes_assignable__asset__asset_type",
    )
    #: Reverse condition relations require prefetches; select_related
    #: cannot load them for query-free scope evaluation.
    also_prefetch = (
        "hides_categories__categories",
        "targets_miniature__has_subtypes__subtypes",
        "targets_miniature__is_profile__profiles",
        "targets_miniature__is_profile_type__profile_types",
        Prefetch(
            "targets_miniature__counter_at_least",
            queryset=CounterAtLeast.objects.select_related("counter"),
        ),
        "targets_miniature__has_pickable__pickables",
        "targets_miniature__has_status",
        "targets_gang__has_gang_pickable__pickables",
        "targets_weapons__has_traits__traits",
        # Granted slots need their type and picklist loaded before computation
        # and picker rendering.
        "adds_assignable__slot__slot_type",
        "adds_assignable__slot__picklist",
        "adds_assignable__action__usable_by_profile_types",
        "adds_assignable__action__usable_by_subtypes",
        "adds_assignable__action__usable_by_profiles",
        "targets_weapons__in_categories__categories",
        "targets_weapons__is_one_of__weapons",
        # Load profiles and printed values for granted weapons before compute.
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

        # Fetch attachments per kind, then hydrate modifiers across the whole
        # level. Combining every path in one join increases planning overhead.
        for model, things in by_model.items():
            prefetch_related_objects(things, _modifiers_path(model))
            if hasattr(model, "income_override"):
                prefetch_related_objects(things, "income_override")
            via = getattr(model, "carries_modifiers_of", None)
            assets = [getattr(thing, via) if via else thing for thing in things]
            assets = [
                asset for asset in assets if hasattr(asset, "base_income_modifier_id")
            ]
            if assets:
                # The catalogue amount remains available when its Income
                # option is unanswered or another option is selected.
                prefetch_related_objects(assets, "base_income_modifier")
        hydrated = {}
        modifier_instances = []
        for things in by_model.values():
            for thing in things:
                modifiers = _modifiers_of(thing)
                asset = _modifier_carrier(thing)
                base = getattr(asset, "base_income_modifier", None)
                if base is not None:
                    modifiers.append(base)
                if getattr(thing, "income_override_id", None) and getattr(
                    asset, "base_income_modifier_id", None
                ):
                    modifiers.append(thing.income_override)
                for modifier in modifiers:
                    hydrated.setdefault(modifier.pk, modifier)
                    modifier_instances.append(modifier)
        # An M2M attachment can return separate instances of one modifier
        # for different assets. Hydrate every copy: catalogue Income
        # readers use the carrier's own prefetched attachments, including
        # the base figure replaced by a holding's override.
        prefetch_related_objects(modifier_instances, *related, *also_prefetch)

        granted = []
        for things in by_model.values():
            for thing in things:
                # Reuse the fully hydrated instance when multiple kinds reach one
                # carrier, preventing lazy queries during compute.
                modifiers = [hydrated[m.pk] for m in _modifiers_of(thing)]
                if getattr(thing, "income_override_id", None) and not getattr(
                    _modifier_carrier(thing), "base_income_modifier_id", None
                ):
                    from n26.library.income import is_income_contribution

                    modifiers = [
                        m
                        for m in modifiers
                        if m.pk == thing.income_override_id
                        or not is_income_contribution(m)
                    ]
                index.add(thing, modifiers)
                for modifier in modifiers:
                    granted_thing = getattr(modifier.effect, "thing", None)
                    if granted_thing is not None:
                        granted.append(granted_thing)
                    # Starting picks can carry modifiers and must enter the next frontier.
                    with_pick = getattr(modifier.effect, "with_pick", None)
                    if with_pick is not None:
                        granted.append(with_pick)
        frontier = granted

    return index


def _modifiers_path(model):
    """Where a carrier of this kind keeps its modifiers, as a prefetch path.

    An assignable carries its own. ``carries_modifiers_of`` names a
    carrier's library relation, so its effects are credited to the carrier.
    A campaign holding's income override is loaded separately.
    """
    via = getattr(model, "carries_modifiers_of", None)
    return f"{via}__modifiers" if via else "modifiers"


def _modifiers_of(thing):
    """The modifiers one carrier runs, already prefetched."""
    carrier = _modifier_carrier(thing)
    modifiers = list(carrier.modifiers.all())
    if getattr(thing, "income_override_id", None) and not getattr(
        carrier, "base_income_modifier_id", None
    ):
        modifiers.append(thing.income_override)
    return modifiers


def _modifier_carrier(thing):
    via = getattr(type(thing), "carries_modifiers_of", None)
    return getattr(thing, via) if via else thing


def carriers(*cards):
    """Collect assignables and campaign holdings whose modifiers affect these cards.

    Member cards include the gang card's holdings because their computed
    grants may affect every member. Nodes alone omit those modifiers.
    """
    things = []
    for card in cards:
        things.extend(node.assignable for node in card.all_nodes())
        gang_card = (
            card
            if getattr(card, "host_kind", None) == GANG
            else getattr(card, "gang_card", None)
        )
        if gang_card is not None:
            things.extend(gang_card.holdings)
    return things
