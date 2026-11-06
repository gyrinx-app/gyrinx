"""Compute card modifiers from content loaded by ``n26.core.card``.

``compute(card, index)`` issues no database queries. A member card includes
gang-hosted broadcast assignments and grants from the computed gang card.
These sources affect the member without adding equipment lines or rating,
and their stored effects are reported on the gang card only.

Evaluate modifiers in rounds determined by selector specificity. Each
round reads the facts settled before it began. Additions run to a fixed
point with cycle detection, then removals settle. Stat changes are recorded
for the renderer, which applies sets before shifts.

Granted weapons add nodes to ``card.granted`` so weapon-scoped modifiers
and renderers can use their profiles. Clear this output before each run
to prevent duplicate nodes on recomputation. A weapon appears after its
grant's round, so an unconditional scope in that round cannot target it;
a later conditional scope can.

Removals cancel computed grants and suppress unpaid stored assignments.
Never suppress a purchase or an assignment with paid descendants. Track
all granting edges so a grant survives while any source remains.
``_retract`` removes dependent effects and restores removals whose own
source was cancelled, without changing stored assignments.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from n26.library.models.modifier import GANG, MODEL, WEAPON_PROFILE

if TYPE_CHECKING:
    from n26.core.models import CampaignAsset

#: Bound grant recursion to reject cyclic or excessively nested content.
MAX_CHAIN_DEPTH = 5

#: Shared holder label for gang-hosted content on member cards.
THE_GANG = "the gang"


def kind_of(thing):
    """Return the public kind label, or empty for internal carrier kinds.

    Hidden carriers, slots, picks, tables and actions have useful display
    names but no kind label on player-facing lines. Campaign assets use
    their campaign type's authored asset label.
    """
    from n26.core.models import CampaignAsset
    from n26.library.models import Action, AssetTable, Hidden, Pickable, RankTable, Slot

    if isinstance(thing, (Hidden, Slot, Pickable, AssetTable, Action, RankTable)):
        return ""
    if isinstance(thing, CampaignAsset):
        # A campaign asset is named by what its campaign type calls the
        # asset type — "territory", "settlement" — never by the table it sits in.
        return thing.type_label
    return str(thing._meta.verbose_name)


def is_orphan_pick(node):
    """Whether a pick lacks both an assignment choice and a complete holding origin.

    Orphan picks add no line, modifier or matchable fact to the card.
    """
    from n26.library.models import Pickable

    return (
        isinstance(node.assignable, Pickable)
        and node.chosen_for_key is None
        and (
            node.chosen_for_holding_key is None
            or node.chosen_for_holding_revision is None
        )
    )


@dataclass(frozen=True)
class Contribution:
    """Something a modifier added, and what added it."""

    thing: object
    source: str
    source_kind: str = ""
    #: Whether the granting scope makes this gang grant affect members.
    #: Unused for grants directly to a model.
    echoes: bool = True
    #: Stored root of the grant chain. Computed grants have no assignment,
    #: so their choices use this anchor and disappear when it is removed.
    root_key: object = None
    #: A computed chain rooted in a campaign holding has no assignment anchor.
    holding: CampaignAsset | None = None

    @property
    def name(self):
        return str(self.thing)


@dataclass
class StatChange:
    """One pending change to one characteristic."""

    stat: object
    mode: str
    amount: int
    source: str
    source_kind: str = ""
    #: When the line carrying this change was written onto the card, so
    #: changes fold in the order they were acquired — the order a stat's
    #: limits are met in decides what each change was worth. ``None`` for
    #: a change nothing stored stands behind: a built-in, a preview.
    acquired: object = None


@dataclass
class CounterContribution:
    """A modifier's transient addition to a counter, with its source.

    Readings combine stored values with active contributions. Without a
    stored assignment, the contributions alone determine the reading.
    """

    counter: object
    amount: int
    source: str
    source_kind: str = ""
    #: The assignment at the root of the contributing grant chain.
    root_key: object = None
    #: Direct holding grants have no assignment at their root.
    holding: CampaignAsset | None = None
    #: The actual carrier distinguishes catalogue Income from the same
    #: modifier reached through a chosen grant.
    modifier: object = None
    carrier_key: object = None
    #: The modifier that actually substituted this contribution's amount.
    #: None when the authored effect ran, including an unselected override.
    applied_override: object = None
    per_counter: object = None
    per_counter_value: int = 0
    per_counter_rate: int = 0


@dataclass
class ComputedWeapon:
    """A weapon profile's computed additions."""

    node: object
    added_traits: list[Contribution] = field(default_factory=list)
    removed_traits: list[Contribution] = field(default_factory=list)
    stat_changes: list[StatChange] = field(default_factory=list)

    @property
    def trait_names(self):
        """Printed traits plus computed ones, minus computed removals."""
        removed = {c.name for c in self.removed_traits}
        printed = set(self.node.assignable.trait_names)
        added = {c.name for c in self.added_traits}
        return sorted((printed | added) - removed)


def count_mark(count):
    """Return ``" (x3)"`` for repeated copies, or empty for a single copy."""
    return f" (x{count})" if count > 1 else ""


@dataclass(frozen=True)
class StackedName:
    """A distinct name and the number of copies it represents."""

    name: str
    count: int = 1

    @property
    def text(self):
        return f"{self.name}{count_mark(self.count)}"


def stacked_name_items(names):
    """Count identical names, retaining their first-seen order."""
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return [StackedName(name, count) for name, count in counts.items()]


def stacked_names(names):
    """Combine repeated names as ``Name (xn)`` in first-seen order.

    Only presentation changes; stored selections remain separate.
    """
    return ", ".join(item.text for item in stacked_name_items(names))


@dataclass
class ChoiceSlot:
    """A computed choice provided by a modifier or assigned slot.

    The choice exists while its source remains present; selections are
    stored separately. Slot choices may hold several picks, linked to an
    assignment or campaign holding's ownership period.
    """

    kind_label: str
    source: str
    source_kind: str
    anchor: object  # the card node asking — the offer's carrier, or the slot
    #: The card nodes chosen for it, in the order they were written.
    picks: list = field(default_factory=list)
    #: The offer itself, so a picker can ask what this fighter may choose
    #: (``n26.core.browse.offered_by``). Its section narrowing needs the card,
    #: which the slot does not carry — hence asking rather than storing.
    offer: object = None
    #: The ``Slot`` asking, where one is. None for a modifier's offer.
    slot: object = None
    #: How many picks the card expects, and how many it holds. A
    #: modifier's offer is one and exactly one; a slot says for itself.
    min_picks: int = 1
    max_picks: int = 1
    status_revision: int | None = None
    #: The holding asking this gang choice; mutually exclusive with anchor.
    holding: CampaignAsset | None = None

    @property
    def resolved_with(self):
        """The first pick — what a surface drawing one thing shows."""
        return self.picks[0] if self.picks else None

    @property
    def is_resolved(self):
        return bool(self.picks)

    @property
    def is_full(self):
        """Whether the choice holds all the picks it will take."""
        return len(self.picks) >= self.max_picks

    @property
    def allow_dismissal(self):
        return self.slot.allow_dismissal if self.slot is not None else True

    @property
    def current_picks(self):
        """The picks that belong among current choices rather than in history."""
        return [
            node
            for node in self.picks
            if not getattr(getattr(node, "assignable", None), "record_only", False)
        ]

    @property
    def is_history_only(self):
        return self.is_full and bool(self.picks) and not self.current_picks

    @property
    def chosen_name(self):
        picks = self.current_picks
        return stacked_names(node.name for node in picks) if picks else None

    @property
    def identity(self):
        """The offer or slot identity that distinguishes choices on one anchor."""
        return self.slot if self.slot is not None else self.offer


@dataclass(frozen=True)
class HiddenCategories:
    """Categories hidden from one collection, with their modifier's source."""

    collection: object
    categories: tuple
    source: str
    source_kind: str


@dataclass(frozen=True)
class CategoryPlacement:
    """A modifier's placement of a category within a fighter's sections.

    Placements are recomputed with their sources. Unplaced categories use
    the Other section when browsed.
    """

    category: object
    #: The collection section this places into — the collection's own
    #: schema, carrying the section's name, its position, and which
    #: collection this placement is scoped to.
    section: object
    source: str
    source_kind: str


@dataclass(frozen=True)
class DrawnPick:
    """A gang-held selection displayed on a member's card by a modifier.

    Display it as a fact. The originating choice remains actionable only
    on the card where the choice was offered.
    """

    #: The pick's line — the gang's assignment, riding this card.
    node: object
    #: What sort of thing was picked, by its slot type's name:
    #: "Archetype". Never the slot's own label, which names one question
    #: among several.
    kind_label: str
    source: str
    source_kind: str

    @property
    def name(self):
        return self.node.name


@dataclass(frozen=True)
class StoredEffect:
    """An acquisition effect described on a card without executing it.

    Operations execute these effects when an assignable arrives, including
    those that create pets. Previews and stored cards both describe them.
    """

    description: str
    source: str
    source_kind: str
    happened: bool


@dataclass
class PlannedStep:
    """A modifier's execution order, scope, effect and outcome.

    ``ComputedCard.plan`` records each round as plain data for inspection.
    """

    source: object
    modifier: object
    #: The scope's specificity — which round this step belongs to.
    round: int
    #: The round it actually executed in (later than ``round`` for a
    #: carrier granted mid-computation).
    ran_in: int
    #: What became of it. ``reached`` the target, ``skipped`` it,
    #: ``noted`` (a stored effect, read but never run here — and never
    #: retracted, because the assignments it wrote are still there),
    #: ``retracted`` — it ran, and then whatever carried it was itself
    #: taken away, so its work was undone — or ``refused``, a removal
    #: that found only assignments somebody had paid for.
    outcome: str = "pending"
    granted: tuple = ()
    #: What a removal actually cancelled: a grant, a stored assignment, or
    #: both.
    took_away: tuple = ()
    #: What a removal left alone because money stands behind it.
    refused: tuple = ()
    #: True when the carrier arrived via a grant rather than the card.
    discovered: bool = False
    #: Gang-owned source affecting this member without a display line.
    #: Report its stored effects once on the gang card.
    echoed: bool = False
    #: The card node carrying this modifier — None for discovered
    #: carriers. What "the weapon I am attached to" anchors on.
    node: object = None
    #: The written line this carrier stands on: its own where the card
    #: holds it, and otherwise the one at the foot of the grants that
    #: brought it here. What a choice it gives is addressed on.
    root_key: object = None
    #: The original holding, retained through computed carriers such as Hidden.
    holding: CampaignAsset | None = None

    @property
    def scope(self):
        """Format the scope description lazily when the plan is inspected."""
        return str(self.modifier.scope)

    @property
    def effect(self):
        return str(self.modifier.effect)

    def __str__(self):
        did = ""
        if self.granted:
            did += f" -> granted {', '.join(self.granted)}"
        if self.took_away:
            did += f" -> took away {', '.join(self.took_away)}"
        if self.refused:
            did += f" -> left {', '.join(self.refused)} (paid for)"
        return (
            f"round {self.ran_in}: [{self.scope}] {self.effect} "
            f"(from {self.source}) — {self.outcome}{did}"
        )


class _OwnersRemoval:
    """Describe an owner's removal in the same plan shape as a modifier.

    Targets are fixed, so this adapter supplies descriptions without a scope.
    """

    def __init__(self, thing):
        self.thing = thing
        self.name = ""

    @property
    def scope(self):
        return "the model"

    @property
    def effect(self):
        return f"takes away {self.thing}"


class _TheOwner:
    """A source identity for owner-authored removals that cannot be retracted."""

    class _meta:
        label_lower = "owner"

    pk = None

    def __str__(self):
        return "your edits"


THE_OWNER = _TheOwner()


def _own_removals(card):
    """Prepare owner-authored removal assignments for round zero.

    Conditional scopes see their targets as removed. Later grants of the
    same content remain cancelled during retraction.
    """
    from n26.library.models.modifier import MODEL, Target

    prepared = []
    for assignment in getattr(card, "removals", ()):
        thing = assignment.assignable
        step = PlannedStep(
            source=THE_OWNER,
            modifier=_OwnersRemoval(thing),
            round=0,
            ran_in=0,
        )
        step.outcome = "reached"
        prepared.append(
            (
                Target(MODEL),
                Contribution(thing=thing, source=str(THE_OWNER)),
                ("edit", assignment.pk),
                step,
            )
        )
    return prepared


@dataclass
class _Placed:
    """A grant edge retained for retraction, including duplicate sources.

    ``payload=None`` when another source already supplied the content.
    Keeping every edge allows the grant to survive removal of one source.
    """

    source_key: object
    thing_key: object
    contribution: Contribution
    #: Where the entry went: the ComputedCard, one ComputedWeapon, or the
    #: card itself for a granted weapon's line. None for a kind that draws
    #: no line at all — a hidden carrier is a grant with nothing to show.
    holder: object
    field: str
    #: The entry appended, or None where a same-named one already stood.
    payload: object = None


@dataclass
class _Applied:
    """A non-grant effect and its source, retained for retraction.

    Remove its exact list entry by identity without disturbing equal entries.
    """

    source_key: object
    holder: object
    field: str
    payload: object


@dataclass
class _TakenAway:
    """A removal and its effects, retained until source survival is known.

    Retraction propagates a surviving removal through its target's dependants,
    or restores its effects when the removal's source was cancelled.
    """

    source_key: object
    thing: object
    step: PlannedStep
    #: What the scope selected. Only a model's or a gang's cancellation
    #: retracts a chain; on a weapon's line a removal is one trait.
    kind: str
    holder: object = None
    field: str = ""
    #: Entries taken out of a computed list, kept so they can go back.
    dropped: tuple = ()
    #: An entry put in — a weapon's removed trait — to be taken out again.
    added: object = None
    #: Stored assignments this hid, and stored assignments it left alone
    #: because money stands behind them.
    hidden: tuple = ()
    refused: tuple = ()
    #: Campaign-default suppression leaves other grants of the asset intact.
    defaults_only: bool = False


@dataclass
class _Offers:
    """Collect modifier offers and granted slots before resolving their selections.

    The wrapper lets retraction remove an offer through the ordinary effect path.
    """

    items: list = field(default_factory=list)


@dataclass
class _Log:
    """Effects from one compute run, keyed by carrier for later retraction."""

    placed: list = field(default_factory=list)
    applied: list = field(default_factory=list)
    removals: list = field(default_factory=list)
    #: Category re-filings in order — the last one still standing wins.
    recategorisations: list = field(default_factory=list)


@dataclass
class ComputedCard:
    """What a card looks like once its modifiers have been worked out."""

    card: object
    #: The plan-and-trace: every step in execution order. See PlannedStep.
    plan: list[PlannedStep] = field(default_factory=list)
    subtypes: list[Contribution] = field(default_factory=list)
    skills: list[Contribution] = field(default_factory=list)
    #: Powers granted computedly — a psyker entry that starts knowing one.
    #: Known while the granter stands, like a granted skill.
    powers: list[Contribution] = field(default_factory=list)
    #: Collections granted computedly — Tech Bazaar's standing Trading Post
    #: access. Access to browse, gone when the granter goes.
    collections: list[Contribution] = field(default_factory=list)
    #: Named special rules granted computedly — a gang type's "all our
    #: fighters may…", reaching each member through the broadcast.
    rules: list[Contribution] = field(default_factory=list)
    #: Picks a grant dealt onto the card beside the slot they settle — a
    #: Clan House choice that makes the gang count as a Goliath gang.
    #: Facts, not lines: a granted slot is hidden, so nothing draws them,
    #: but a condition asking "has picked Goliath" sees them exactly as
    #: it sees a written pick. Their source is the slot, so they go the
    #: moment it does.
    picks: list[Contribution] = field(default_factory=list)
    #: Asset tables granted computedly — a journal's territory table given
    #: to every gang of its House. Facts, not lines: nothing draws a table,
    #: but "holds this table" is what says a gang may roll on it, and a
    #: condition or a roll control reads a granted one exactly as it reads
    #: a table the gang was given at joining.
    tables: list[Contribution] = field(default_factory=list)
    #: Where skill sets and power families sit for this fighter — see
    #: ``CategoryPlacement``.
    placements: list[CategoryPlacement] = field(default_factory=list)
    hidden_categories: list[HiddenCategories] = field(default_factory=list)
    random_skill_advancements: list = field(default_factory=list)
    stat_changes: list[StatChange] = field(default_factory=list)
    #: What modifiers add to counters this card reads. Kept apart from
    #: the stored values so a reading can state both and neither is
    #: mistaken for the other.
    counter_contributions: list[CounterContribution] = field(default_factory=list)
    #: The category heading this model sorts under on the gang sheet,
    #: when a rule re-files them — None sorts by the profile's own.
    sorted_under: object = None
    weapons: dict = field(default_factory=dict)
    choices: list[ChoiceSlot] = field(default_factory=list)
    #: Picks the gang holds that this card draws all the same, because a
    #: modifier on the pickable says so — see ``DrawnPick``. Empty on
    #: every card no such modifier reaches, which is most of them.
    drawn_picks: list[DrawnPick] = field(default_factory=list)
    stored_effects: list[StoredEffect] = field(default_factory=list)
    #: Gang-scoped composition asks (``RequiresCompanions``), collected
    #: here and resolved against the roster by ``compute_gang`` — only a
    #: gang card ever gathers any.
    requirements: list = field(default_factory=list)
    #: Composition ceilings (``AllowsAtMost``), collected here and folded
    #: against what is held by ``limit_notes``. A gang card gathers the
    #: ones aimed at the gang and counts the roster; a model's card
    #: gathers the ones aimed at it and counts its own assignments.
    limits: list = field(default_factory=list)
    #: How many granted lines have been dealt. A line's key is built from
    #: it, so a key stays unique even where a grant was taken back and
    #: another dealt after it.
    granted_serial: int = 0
    #: What a modifier put on this card and nothing took back — what the
    #: card holds by grant rather than by assignment, whether or not the grant
    #: drew anything. A gang's are dealt onto every member's card, where
    #: they arrive as ``echoed``.
    acquired: list[Contribution] = field(default_factory=list)
    #: Settled gang grants affecting this member without adding lines or
    #: rating. Empty on gang cards, which expose them through acquired.
    echoed: list[Contribution] = field(default_factory=list)

    def weapon(self, node):
        return self.weapons[node.key]

    def changes_for(self, field_name):
        return [
            change
            for change in self.stat_changes
            if change.stat.field_name == field_name
        ]


class ModifierIndex:
    """Prefetched modifiers keyed by carrier.

    Built by ``n26.core.card`` so ``compute`` needs no database access.
    """

    def __init__(self, by_key=None):
        self._by_key = by_key or {}

    @staticmethod
    def key(thing):
        return (thing._meta.label_lower, thing.pk)

    def add(self, thing, modifiers):
        """Store a modifier with its precomputed selector specificity.

        The index is shared across cards, avoiding repeated selector compilation
        and scoring during each compute call.
        """
        from n26.core import select

        entries = []
        for modifier in modifiers:
            scope = modifier.scope
            spec = select.specificity(scope.as_selector()) if scope else 0
            entries.append((modifier, spec))
        self._by_key[self.key(thing)] = entries

    def for_thing(self, thing):
        """``[(modifier, specificity)]`` for one carrier."""
        return self._by_key.get(self.key(thing), [])

    def __len__(self):
        return len(self._by_key)


def compute(card, index):
    """Compute card facts in rounds ordered by selector specificity.

    Unconditional selectors run in round zero; each condition adds specificity.
    All scopes in a round read the same snapshot of earlier rounds' facts.
    Apply that round's additions before its removals. A newly granted carrier
    runs no earlier than its granting round, using that round's snapshot.

    Record execution in ``computed.plan``. After all rounds, ``_retract``
    propagates cancellations through dependent effects.
    """
    from n26.library.models import Asset, Pickable
    from n26.library.models.modifier import (
        AddsAssignable,
        AllowsAtMost,
        ChangesCategory,
        ChangesStat,
        ContributesToCounter,
        DrawsPick,
        ExcludesCampaignAssets,
        HidesCategories,
        OffersChoice,
        PlacesCategory,
        RandomisesSkillAdvancements,
        RemovesAssignable,
        RequiresCompanions,
    )

    # Granted lines are this function's output, not the card's content, so
    # a card computed twice does not end up carrying two of everything.
    card.granted.clear()

    computed = ComputedCard(
        card=card,
        weapons={
            node.key: ComputedWeapon(node=node) for node in card.weapon_profile_nodes()
        },
    )

    # Two views of the card's own lines, taken in one pass: whether a thing
    # is written down, and the lines by their own identity — the latter
    # being what a chain of grants names when it says what it stands on.
    is_assigned, lines = {}, {}
    for node in card.all_nodes():
        is_assigned[ModifierIndex.key(node.assignable)] = node.assignment is not None
        lines[node.key] = node
    asset_owners = _AssetOrigins(card)
    offers = _Offers()
    given_slots = _Offers()
    #: Gang-held picks a modifier says to draw here, settled once the
    #: card's own questions are known — see ``_fill_drawn_picks``.
    drawn = []
    log = _Log()

    # Chosen assignments by what caused them. What a choice settles on is
    # a stored assignment — a printed fact — so this is built once, before
    # the rounds: a chosen-mode placement in any round reads the same
    # settled assignment a slot does.
    by_cause = {}
    #: Picks by the choice they settle, read off ``chosen_for``.
    by_choice = {}
    by_holding_choice = {}
    for node in card.all_nodes():
        if node.caused_by_key is not None:
            by_cause.setdefault(node.caused_by_key, []).append(node)
        if node.chosen_for_key is not None:
            by_choice.setdefault(node.chosen_for_key, []).append(node)
        if node.chosen_for_holding_key is not None:
            address = (
                node.chosen_for_holding_key,
                node.chosen_for_holding_revision,
                node.chosen_for_slot_id,
            )
            by_holding_choice.setdefault(address, []).append(node)

    #: Plan-display order within a round; application order is fixed
    #: separately (adds settle before removes).
    effect_order = {
        AddsAssignable: 0,
        RemovesAssignable: 1,
        ExcludesCampaignAssets: 1,
        ChangesStat: 2,
        PlacesCategory: 3,
        OffersChoice: 4,
        RequiresCompanions: 5,
        AllowsAtMost: 6,
        ContributesToCounter: 7,
        DrawsPick: 8,
        HidesCategories: 9,
        RandomisesSkillAdvancements: 10,
    }

    def steps_for(
        source,
        discovered,
        found_in_round,
        node=None,
        echoed=False,
        root_key=None,
        holding=None,
    ):
        # A carrier the card holds stands on its own line; one a grant
        # brought stands on whatever the granter stood on, so the foot of
        # a chain however deep is the line somebody wrote down.
        stands_on = node.key if node is not None else root_key
        for modifier, spec in index.for_thing(source):
            if modifier.scope is None or modifier.effect is None:
                continue
            yield PlannedStep(
                source=source,
                modifier=modifier,
                round=spec,
                ran_in=max(spec, found_in_round),
                discovered=discovered,
                node=node,
                echoed=echoed,
                root_key=stands_on,
                holding=holding,
            )

    def frontier_key(thing, holding=None):
        key = ModifierIndex.key(thing)
        if holding is None:
            return key
        return (key, holding.pk, holding.ownership_revision)

    # One run of a carrier's modifiers per NODE, not per distinct thing:
    # owning two Hardpoint conversions costs two Attacks. ``seen`` only
    # dedups the granted frontier. Each holding keeps a separate origin so
    # two territories granting one Slot still ask two independent questions.
    from_the_gang = _from_the_gang(card, index)
    gang_card = getattr(card, "gang_card", None)
    suppressed = (
        {
            node.key
            for node in gang_card.all_nodes()
            if node.suppressed and isinstance(node.assignable, Asset)
        }
        if gang_card
        else set()
    )
    pending = []
    seen = set()
    for node in card.all_nodes():
        # An asset excluded on the gang stops broadcasting its boons too.
        if node.broadcast and node.key in suppressed:
            node.suppressed = True
        if node.suppressed and isinstance(node.assignable, Asset):
            continue
        seen.add(ModifierIndex.key(node.assignable))
        if is_orphan_pick(node):
            # A pickable with no choice behind it does nothing at all —
            # see ``is_orphan_pick``.
            continue
        pending.extend(steps_for(node.assignable, False, 0, node=node))

    # Holdings supply modifiers without assignment nodes or rating. Credit
    # the campaign asset as the source. On member cards, model-wide scopes
    # apply but bearer-only scopes and stored-effect reporting do not.
    guest = getattr(card, "host_kind", MODEL) != GANG
    for campaign_asset in getattr(card, "holdings", ()):
        seen.add(frontier_key(campaign_asset, campaign_asset))
        pending.extend(
            steps_for(campaign_asset, False, 0, echoed=guest, holding=campaign_asset)
        )

    # What the gang holds by grant is dealt on here too. The gang-hosted
    # assignments already ride the card; a thing the gang was *given* has
    # no assignment to ride, and there is no difference between the two
    # from the point of view of applying effects — so it arrives as the
    # gang's guest, drawing nothing and worth nothing, and does everything
    # it does. Something the card already carries is passed over: the
    # assignment it stands on is the more direct telling, and one thing's
    # modifiers run once however many ways it reaches the card.
    # A grant kept on the gang alone does not echo, except an asset:
    # its own boon scopes decide which fighters it reaches.
    echoed = [
        contribution
        for contribution in from_the_gang
        if contribution.echoes
        and frontier_key(contribution.thing, contribution.holding) not in seen
    ]
    # Gang-held picks are facts about every member, including grants whose
    # modifiers are not echoed. Match them alongside broadcast stored picks.
    guest_picks = tuple(
        contribution.thing
        for contribution in from_the_gang
        if isinstance(contribution.thing, Pickable)
    )
    for contribution in echoed:
        seen.add(frontier_key(contribution.thing, contribution.holding))
        # Computed gang grants retain their stored root as a choice anchor.
        # That root is available on the member card as a broadcast node.
        pending.extend(
            steps_for(
                contribution.thing,
                True,
                0,
                echoed=True,
                root_key=contribution.root_key,
                holding=contribution.holding,
            )
        )

    edits = _own_removals(card)
    round_no = 0
    while (pending or edits) and round_no <= MAX_CHAIN_DEPTH:
        # The snapshot every scope in this round sees.
        _scale_counter_contributions(computed)
        facts = _Facts(card, computed, guest_picks)
        adds, removes, exclusions = [], [], []
        # The owner's removals settle with round 0, the reach an
        # unconditional content removal has.
        for edit in edits:
            computed.plan.append(edit[3])
            removes.append(edit)
        edits = []

        for _ in range(MAX_CHAIN_DEPTH):
            batch = [step for step in pending if step.ran_in <= round_no]
            if not batch:
                break
            pending = [step for step in pending if step.ran_in > round_no]
            batch.sort(
                key=lambda step: (
                    effect_order.get(type(step.modifier.effect), 9),
                    str(step.source),
                    step.modifier.name,
                )
            )
            for step in batch:
                scope, effect = step.modifier.scope, step.modifier.effect
                source_key = ModifierIndex.key(step.source)
                if getattr(effect, "is_stored", False):
                    # Describe stored effects without executing them during reads. Report
                    # model-scoped effects on the bearer and gang-scoped effects on the gang;
                    # broadcast and echoed gang sources do not report them on member cards.
                    gang_held = step.echoed or (
                        step.node is not None and step.node.broadcast
                    )
                    if gang_held or not scope.targets(
                        card, facts, carrier=step.node, echoed=step.echoed
                    ):
                        step.outcome = "skipped"
                        computed.plan.append(step)
                        continue
                    note = StoredEffect(
                        description=str(effect),
                        source=str(step.source),
                        source_kind=kind_of(step.source),
                        happened=is_assigned.get(source_key, False),
                    )
                    # Not in the retraction log, deliberately: this note is
                    # about assignments that were written when the thing
                    # arrived, and a removal is a read. The pet it brought
                    # is still on the roster, so the card goes on saying
                    # where it came from.
                    computed.stored_effects.append(note)
                    step.outcome = "noted"
                    computed.plan.append(step)
                    continue

                targets = [
                    target
                    for target in scope.targets(
                        card, facts, carrier=step.node, echoed=step.echoed
                    )
                    if effect.accepts(target.kind)
                ]
                if not targets:
                    step.outcome = "skipped"
                    computed.plan.append(step)
                    continue
                step.outcome = "reached"
                label, label_kind = str(step.source), kind_of(step.source)
                if isinstance(effect, AddsAssignable) and effect.slot_id is not None:
                    # A choice one thing opens by giving another: picking
                    # Clan House opens the House choice. Once per grant
                    # however many targets it reaches — and asked where
                    # the grant *landed*. A local giver's choice is asked
                    # here, whatever it targets; a gang-held giver's is
                    # asked on each card its scope reached a model of —
                    # Water Guild, the gang's pick, opening a Guild Role
                    # on every fighter — and never repeated for merely
                    # riding a card as the gang's copy. The gang's guests
                    # are gang-held too: a rule an alliance gave the gang
                    # asks its choice on each fighter it reaches, and on
                    # none if it reaches only the gang.
                    gang_held = step.echoed or (
                        step.node is not None and step.node.broadcast
                    )
                    if not gang_held or any(target.kind == MODEL for target in targets):
                        # A grant keeps its original assignment anchor or
                        # holding origin through every computed carrier.
                        given = (
                            effect.thing,
                            lines.get(step.root_key),
                            label,
                            label_kind,
                            step.holding,
                        )
                        given_slots.items.append(given)
                        log.applied.append(
                            _Applied(source_key, given_slots, "items", given)
                        )
                for target in targets:
                    if isinstance(effect, AddsAssignable):
                        thing = effect.thing
                        if isinstance(thing, Asset) and not _campaign_gives_type(
                            card, thing.asset_type.campaign_type_id
                        ):
                            step.outcome = "skipped"
                            continue
                        adds.append(
                            (
                                target,
                                Contribution(
                                    thing=thing,
                                    source=label,
                                    source_kind=label_kind,
                                    echoes=isinstance(thing, Asset)
                                    or getattr(scope, "echoes", True),
                                    root_key=step.root_key,
                                    holding=step.holding,
                                ),
                                step.node,
                                source_key,
                            )
                        )
                        step.granted = (*step.granted, str(thing))
                        thing_key = ModifierIndex.key(thing)
                        visited_key = frontier_key(thing, step.holding)
                        if visited_key not in seen:
                            seen.add(visited_key)
                            pending.extend(
                                steps_for(
                                    thing,
                                    True,
                                    round_no,
                                    root_key=step.root_key,
                                    holding=step.holding,
                                    echoed=step.echoed if step.holding else False,
                                )
                            )
                        if effect.with_pick_id is not None:
                            # The pick a granted slot arrives settled on.
                            # Dealt as a second addition whose source is
                            # the *slot*, not the carrier: the retraction
                            # cascade then takes the pick the moment the
                            # slot goes, whether a removal named the slot
                            # or the carrier itself was taken away. A
                            # carrier in its own right too, so what the
                            # pick gives runs from here.
                            pick = effect.with_pick
                            adds.append(
                                (
                                    target,
                                    Contribution(
                                        thing=pick,
                                        source=str(thing),
                                        source_kind=kind_of(thing),
                                        echoes=getattr(scope, "echoes", True),
                                        root_key=step.root_key,
                                        holding=step.holding,
                                    ),
                                    step.node,
                                    thing_key,
                                )
                            )
                            step.granted = (*step.granted, str(pick))
                            visited_key = frontier_key(pick, step.holding)
                            if visited_key not in seen:
                                seen.add(visited_key)
                                pending.extend(
                                    steps_for(
                                        pick,
                                        True,
                                        round_no,
                                        root_key=step.root_key,
                                        holding=step.holding,
                                        echoed=step.echoed if step.holding else False,
                                    )
                                )
                    elif isinstance(effect, ExcludesCampaignAssets):
                        for node in _campaign_asset_defaults(
                            card, effect.asset_type_id
                        ):
                            record = _TakenAway(
                                source_key=source_key,
                                thing=node.assignable,
                                step=step,
                                kind=target.kind,
                                defaults_only=True,
                            )
                            if any(line.carries_money for line in node.walk()):
                                record.refused = (node,)
                            else:
                                node.suppressed = True
                                record.hidden = (node,)
                            exclusions.append(record)
                    elif isinstance(effect, RemovesAssignable):
                        removes.append(
                            (
                                target,
                                Contribution(
                                    thing=effect.thing,
                                    source=label,
                                    source_kind=label_kind,
                                ),
                                source_key,
                                step,
                            )
                        )
                    elif isinstance(effect, ChangesCategory):
                        # Last one standing wins: two rules re-filing one
                        # model is a content oddity, not an order to keep.
                        computed.sorted_under = effect.category
                        log.recategorisations.append((source_key, effect.category))
                    elif isinstance(effect, ChangesStat):
                        change = StatChange(
                            stat=effect.stat,
                            mode=effect.mode,
                            amount=effect.amount,
                            source=label,
                            source_kind=label_kind,
                            acquired=getattr(
                                lines.get(step.root_key), "acquired", None
                            ),
                        )
                        holder = (
                            computed
                            if target.kind == MODEL
                            else computed.weapons[target.node.key]
                        )
                        holder.stat_changes.append(change)
                        log.applied.append(
                            _Applied(source_key, holder, "stat_changes", change)
                        )
                    elif isinstance(effect, ContributesToCounter):
                        # Never written down: the reading is worked out
                        # from these every time it is asked for, so a
                        # carrier taken away takes its figure with it.
                        applied_override = _income_override(
                            step, lines, asset_owners, index
                        )
                        contributed = CounterContribution(
                            counter=effect.counter,
                            amount=(
                                applied_override.contributes_to_counter.amount
                                if applied_override is not None
                                else effect.amount
                            ),
                            source=label,
                            source_kind=label_kind,
                            root_key=step.root_key,
                            holding=step.holding,
                            modifier=step.modifier,
                            carrier_key=source_key,
                            applied_override=applied_override,
                            per_counter=effect.per_counter,
                            per_counter_rate=effect.amount,
                        )
                        computed.counter_contributions.append(contributed)
                        log.applied.append(
                            _Applied(
                                source_key,
                                computed,
                                "counter_contributions",
                                contributed,
                            )
                        )
                    elif isinstance(effect, RandomisesSkillAdvancements):
                        # Retraction removes applications by identity, so a
                        # shared modifier needs one object per carrier.
                        randomised = copy(effect)
                        computed.random_skill_advancements.append(randomised)
                        log.applied.append(
                            _Applied(
                                source_key,
                                computed,
                                "random_skill_advancements",
                                randomised,
                            )
                        )
                    elif isinstance(effect, OffersChoice):
                        # Anchor computed offers to the stored root of their granting chain so
                        # the picker can address them.
                        offer = (
                            effect,
                            label,
                            label_kind,
                            lines.get(step.root_key),
                        )
                        offers.items.append(offer)
                        log.applied.append(_Applied(source_key, offers, "items", offer))
                    elif isinstance(effect, RequiresCompanions):
                        asked = (effect, label, label_kind)
                        computed.requirements.append(asked)
                        log.applied.append(
                            _Applied(source_key, computed, "requirements", asked)
                        )
                    elif isinstance(effect, AllowsAtMost):
                        capped = (effect, label, label_kind)
                        computed.limits.append(capped)
                        log.applied.append(
                            _Applied(source_key, computed, "limits", capped)
                        )
                    elif isinstance(effect, DrawsPick):
                        # Only what the gang holds is drawn this way. A
                        # pick the card carries itself already sits on
                        # its own choice row, and drawing it again would
                        # say it twice.
                        gang_held = step.echoed or (
                            step.node is not None and step.node.broadcast
                        )
                        if not gang_held or step.node is None:
                            step.outcome = "skipped"
                            continue
                        drawn.append((step.node, step))
                    elif isinstance(effect, HidesCategories):
                        hidden = HiddenCategories(
                            collection=effect.collection,
                            categories=tuple(effect.categories.all()),
                            source=label,
                            source_kind=label_kind,
                        )
                        computed.hidden_categories.append(hidden)
                        log.applied.append(
                            _Applied(source_key, computed, "hidden_categories", hidden)
                        )
                    elif isinstance(effect, PlacesCategory):
                        category = _placed_category(effect, step.node, by_cause)
                        if category is None:
                            # A chosen-mode placement with nothing chosen
                            # yet: nothing to place, and the plan says so.
                            step.outcome = "skipped"
                            continue
                        placement = CategoryPlacement(
                            category=category,
                            section=effect.section,
                            source=label,
                            source_kind=label_kind,
                        )
                        computed.placements.append(placement)
                        log.applied.append(
                            _Applied(source_key, computed, "placements", placement)
                        )
                computed.plan.append(step)

        # Settle the round: additions first, then removals (agreed order).
        for target, contribution, carrier, source_key in adds:
            holder, where, payload = _place(computed, target, contribution, carrier)
            # Logged whatever came of it — a grant that drew no line still
            # put the thing on the card, and the thing may be doing plenty.
            log.placed.append(
                _Placed(
                    source_key=source_key,
                    thing_key=ModifierIndex.key(contribution.thing),
                    contribution=contribution,
                    holder=holder,
                    field=where,
                    payload=payload,
                )
            )
        for target, contribution, source_key, step in removes:
            log.removals.append(
                _take_away(computed, target, contribution, source_key, step)
            )
        log.removals.extend(exclusions)
        round_no += 1

    computed.echoed = echoed
    dead = _retract(computed, log)
    _settle_counter_origins(computed, log, dead)
    _scale_counter_contributions(computed)
    computed.acquired = _acquisitions(log, dead)
    # A guest this card's own removals cancelled is not held here either.
    computed.echoed = [
        contribution
        for contribution in echoed
        if ModifierIndex.key(contribution.thing) not in dead
    ]
    _fill_choice_slots(computed, offers.items, by_cause)
    # A question whose slot was itself taken away is not asked: the
    # giver may stand, but the given thing is gone — the Subjugator
    # pattern, where a profile removes the general slot its subtype
    # grants and grants a narrower one of its own.
    _fill_slot_choices(
        computed,
        [
            given
            for given in given_slots.items
            if ModifierIndex.key(given[0]) not in dead
        ],
        by_choice,
        by_holding_choice,
    )
    _fill_drawn_picks(computed, drawn)
    return computed


def _from_the_gang(card, index):
    """Return settled gang grants, cached on ``GangCard.acquired``.

    Every member shares this result, after the gang's removals. Existing
    assignments and the shared index supply all inputs without queries.
    A gang card has no parent gang and receives no such grants.
    """
    gang_card = getattr(card, "gang_card", None)
    if gang_card is None:
        return ()
    if gang_card.acquired is None:
        gang_card.acquired = tuple(compute(gang_card, index).acquired)
    return gang_card.acquired


def _acquisitions(log, dead):
    """Return surviving granted content from the recorded granting edges.

    Include hidden carriers even though they draw no lines. Ordinary grants
    share a library identity; holding grants retain separate ownership origins.
    """
    held = {}
    for placed in log.placed:
        if not _stands(placed, dead):
            continue
        holding = placed.contribution.holding
        key = (
            (placed.thing_key, holding.pk, holding.ownership_revision)
            if holding is not None
            else placed.thing_key
        )
        standing = held.get(key)
        # First giver still standing names it — except that a giver whose
        # grant echoes beats one keeping it the gang's alone, whatever
        # order the batch happened to sort them in: reaching the members
        # must not turn on a modifier's name.
        if standing is None or (placed.contribution.echoes and not standing.echoes):
            held[key] = placed.contribution
    return list(held.values())


def _settle_counter_origins(computed, log, dead):
    """A shared carrier's counters follow its surviving grant chain.

    Grant and choice anchors remain the addresses used during computation.
    Counter provenance is settled separately after cancellations are known.
    """
    if not computed.counter_contributions:
        return
    from n26.library.models import Asset

    granted_assets = {}
    for node in computed.card.all_nodes():
        if node.computed and not node.suppressed and isinstance(node.assignable, Asset):
            granted_assets.setdefault(ModifierIndex.key(node.assignable), []).append(
                node
            )
    nodes = {
        node.key: node
        for node in computed.card.all_nodes()
        if not node.computed and not node.suppressed
    }
    stored = {}
    for node in nodes.values():
        stored.setdefault(ModifierIndex.key(node.assignable), []).append(node)
    edges = {}
    for placed in log.placed:
        if _stands(placed, dead) and placed.contribution.holding is None:
            edges.setdefault(placed.thing_key, []).append(placed)

    def root_for(source_key, preferred, visiting=frozenset()):
        if source_key in dead or source_key in visiting:
            return None
        sources = stored.get(source_key, ())
        # A modifier on a stored assignment belongs to that occurrence,
        # even when a grant also supplies the same library thing.
        if any(node.key == preferred for node in sources):
            return preferred
        if sources:
            return sources[0].key
        # A granted possession draws its own campaign row. Its counters,
        # including those from nested grants, belong to that surviving
        # occurrence rather than to the rule that supplied it.
        assets = granted_assets.get(source_key, ())
        if assets:
            return next(
                (node.key for node in assets if node.caused_by_key == preferred),
                assets[0].key,
            )
        for placed in edges.get(source_key, ()):
            root = root_for(
                placed.source_key,
                placed.contribution.root_key,
                visiting | {source_key},
            )
            if root is not None:
                return root
        # A gang guest arrived from outside this card's granting edges.
        for contribution in computed.echoed:
            if (
                contribution.holding is None
                and ModifierIndex.key(contribution.thing) == source_key
                and contribution.root_key in nodes
            ):
                return contribution.root_key
        return None

    standing = {id(contribution) for contribution in computed.counter_contributions}
    for applied in log.applied:
        if (
            applied.field != "counter_contributions"
            or id(applied.payload) not in standing
        ):
            continue
        contribution = applied.payload
        # Direct holdings have independent frontiers and retain their own
        # ownership origin rather than joining ordinary shared grants.
        if contribution.holding is None:
            contribution.root_key = root_for(applied.source_key, contribution.root_key)


def _placed_category(effect, node, by_cause):
    """Resolve a category placement directly or through its carrier's selection.

    A selected pickable supplies its linked category. No selection means
    no category to place.
    """
    if not effect.the_chosen:
        return effect.category
    if node is None:
        return None  # a discovered carrier is caused by nothing on the card
    for chosen in by_cause.get(node.key, ()):
        home = getattr(chosen.assignable, "category", None)
        if home is not None:
            return home
    return None


@dataclass
class CounterReading:
    """One counter the gang keeps, and where it stands."""

    thing: object
    value: int
    contributions: tuple[CounterContribution, ...] = ()

    @property
    def name(self):
        return str(self.thing)


@dataclass
class ComputedGang:
    """The gang card's choices, grants, counter readings and execution plan.

    ``compute_gang`` uses the same engine as fighter cards and omits fighter-only
    statline and weapon output. See ``design/gang-sheet.md``.
    """

    card: object
    plan: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    collections: list = field(default_factory=list)
    #: Picks a grant dealt onto the gang beside a hidden slot — what a
    #: gang-scoped "has picked" condition reads, and what every member's
    #: facts inherit.
    picks: list = field(default_factory=list)
    #: Asset tables a grant dealt onto the gang — which tables the gang may
    #: roll on beyond the ones it was given at joining. Drawn nowhere.
    tables: list = field(default_factory=list)
    counters: list = field(default_factory=list)
    counter_contributions: list[CounterContribution] = field(default_factory=list)
    #: Empty today — placements land on models — but present so anything
    #: reading placements (``n26.core.browse.offered_by`` shaping a gang-level
    #: pick list) treats both computed kinds alike.
    placements: list = field(default_factory=list)
    #: Always empty, and present for the same reason: a gang deals its
    #: acquisitions onto its members, and nothing is dealt onto the gang.
    #: Whatever reads one computed kind's guests may read the other's.
    echoed: list = field(default_factory=list)
    #: Stored-effect notes whose scope is the gang — a Justicar
    #: alliance's "adds a Magistrate", said once, here.
    effects: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def choice(self, kind_label):
        """First slot by label — for tests and lookups."""
        return next(
            (slot for slot in self.choices if slot.kind_label == kind_label), None
        )


def _scale_counter_contributions(computed):
    """Compute per-point amounts from the current counter values."""
    if not any(item.per_counter is not None for item in computed.counter_contributions):
        return
    from n26.library.models import Counter

    recorded = {}
    for node in computed.card.all_nodes():
        if (
            isinstance(node.assignable, Counter)
            and not node.suppressed
            and not node.broadcast
        ):
            key = ModifierIndex.key(node.assignable)
            held = (
                getattr(node.assignment, "counter_value", None)
                if node.assignment
                else None
            )
            recorded.setdefault(
                key, max(node.assignable.minimum, held.value if held else node.opens_at)
            )
    by_counter = {}
    for contribution in computed.counter_contributions:
        by_counter.setdefault(ModifierIndex.key(contribution.counter), []).append(
            contribution
        )
    resolved = {}

    def reading(counter, visiting=frozenset()):
        key = ModifierIndex.key(counter)
        if key in resolved:
            return resolved[key]
        if key in visiting:
            raise ValueError("Counter contributions cannot form a cycle.")
        if key not in recorded and key not in by_counter:
            return 0
        total = recorded.get(key, 0)
        for contribution in by_counter.get(key, ()):
            if contribution.per_counter is not None:
                contribution.per_counter_value = reading(
                    contribution.per_counter, visiting | {key}
                )
                contribution.amount = (
                    contribution.per_counter_rate * contribution.per_counter_value
                )
            total += contribution.amount
        resolved[key] = total
        return resolved[key]

    for contribution in computed.counter_contributions:
        reading(contribution.counter)


def counter_readings(card, computed=None):
    """Return stored counter values plus active modifier contributions.

    A counter without an assignment still has a computed reading, with
    no stored value to tally.
    """
    from n26.library.models import Counter

    contributed = counter_totals(computed)
    sources = {}
    for contribution in computed.counter_contributions if computed else ():
        key = ModifierIndex.key(contribution.counter)
        sources.setdefault(key, []).append(contribution)
    readings, taken = [], set()
    for node in card.all_nodes():
        if not isinstance(node.assignable, Counter):
            continue
        held = (
            getattr(node.assignment, "counter_value", None)
            if node.assignment is not None
            else None
        )
        thing_key = ModifierIndex.key(node.assignable)
        # Contributions land on the first assignment of a counter and
        # nowhere else: two assignments of one counter are two lines,
        # and adding a figure to each would read as twice what is due.
        additions = () if thing_key in taken else tuple(sources.get(thing_key, ()))
        added = 0 if thing_key in taken else contributed.get(thing_key, 0)
        taken.add(thing_key)
        readings.append(
            CounterReading(
                thing=node.assignable,
                value=max(
                    node.assignable.minimum, held.value if held else node.opens_at
                )
                + added,
                contributions=additions,
            )
        )
    for contribution in computed.counter_contributions if computed else ():
        thing_key = ModifierIndex.key(contribution.counter)
        if thing_key in taken:
            continue
        taken.add(thing_key)
        readings.append(
            CounterReading(
                thing=contribution.counter,
                value=contributed[thing_key],
                contributions=tuple(sources[thing_key]),
            )
        )
    return readings


def counter_totals(computed):
    """What modifiers add to each counter, keyed by the counter's key."""
    totals = {}
    for contribution in computed.counter_contributions if computed else ():
        thing_key = ModifierIndex.key(contribution.counter)
        totals[thing_key] = totals.get(thing_key, 0) + contribution.amount
    return totals


class _AssetOrigins:
    """Asset occurrences behind loaded choices, causes and host links."""

    def __init__(self, card):
        self.nodes = {node.key: node for node in card.all_nodes()}
        self.parents = {
            child.key: node.key
            for node in self.nodes.values()
            for child in node.children
        }
        self.holdings = {
            (holding.pk, holding.ownership_revision): holding
            for holding in getattr(card, "holdings", ())
        }
        self.origins = {}

    def origin(self, key, visiting=frozenset()):
        from n26.library.models import Asset

        if key in self.origins:
            return self.origins[key]
        if key is None or key in visiting or key not in self.nodes:
            return None
        node = self.nodes[key]
        if node.suppressed:
            return None
        if isinstance(node.assignable, Asset):
            result = node
        elif node.computed:
            return None
        elif node.chosen_for_holding_key is not None:
            address = (node.chosen_for_holding_key, node.chosen_for_holding_revision)
            result = self.holdings.get(address)
        else:
            result = next(
                (
                    found
                    for link in (
                        node.chosen_for_key,
                        node.caused_by_key,
                        self.parents.get(key),
                    )
                    if (found := self.origin(link, visiting | {key})) is not None
                ),
                None,
            )
        self.origins[key] = result
        return result

    def for_contribution(self, contribution):
        if contribution.holding is not None:
            return self.holdings.get(
                (contribution.holding.pk, contribution.holding.ownership_revision)
            )
        return self.origin(contribution.root_key)


def asset_origins(card):
    """Each loaded line's owning Asset Node or current CampaignAsset.

    An ordinary asset keeps its assignment identity; a granted possession
    keeps its computed occurrence. A holding keeps its ownership revision,
    so another copy's selection cannot stand in for it.
    Nothing follows an assignment FK or changes a choice's address.
    """
    origins = _AssetOrigins(card)
    return {key: origins.origin(key) for key in origins.nodes}


def _income_override(step, lines, origins, index):
    """The override actually selected through this holding's base choice."""
    from n26.core.models import CampaignAsset
    from n26.library.models import Pickable

    selected = lines.get(step.root_key)
    if (
        selected is None
        or step.node is not selected
        or not isinstance(selected.assignable, Pickable)
    ):
        return None
    owner = origins.origin(selected.key)
    if (
        isinstance(owner, CampaignAsset)
        and selected.chosen_for_holding_key == owner.pk
        and selected.chosen_for_holding_revision == owner.ownership_revision
        and owner.asset.base_income_modifier_id == step.modifier.pk
        and owner.income_override_id is not None
        and any(
            modifier.adds_assignable_id is not None
            and modifier.adds_assignable.slot_id == selected.chosen_for_slot_id
            for modifier, _ in index.for_thing(owner)
        )
    ):
        # Substitute before the next round builds its counter facts. The
        # shared library modifier still holds the catalogue amount.
        return owner.income_override
    return None


def counter_contributions_by_holding(computed):
    """Standing contributions grouped by holding and ownership revision."""
    from n26.core.models import CampaignAsset

    origins = _AssetOrigins(computed.card)
    grouped = {}
    for contribution in computed.counter_contributions:
        owner = origins.for_contribution(contribution)
        if isinstance(owner, CampaignAsset):
            address = (owner.pk, owner.ownership_revision)
            grouped.setdefault(address, []).append(contribution)
    return grouped


def counter_contributions_by_asset_assignment(computed):
    """Standing contributions grouped by their displayed Asset occurrence key."""
    from n26.core.card import Node

    origins = _AssetOrigins(computed.card)
    grouped = {}
    for contribution in computed.counter_contributions:
        owner = origins.for_contribution(contribution)
        if isinstance(owner, Node) and not owner.broadcast:
            grouped.setdefault(owner.key, []).append(contribution)
    return grouped


def compute_gang(gang_card, index):
    """Work out the gang's own card. Query-free, like ``compute``."""
    computed = compute(gang_card, index)
    # Kept on the card for the members: what the gang holds by grant is
    # dealt onto every one of their cards, and it is one answer for all of
    # them however many ask.
    gang_card.acquired = tuple(computed.acquired)
    return ComputedGang(
        card=gang_card,
        plan=computed.plan,
        choices=computed.choices,
        rules=computed.rules,
        collections=computed.collections,
        picks=computed.picks,
        tables=computed.tables,
        counters=counter_readings(gang_card, computed),
        counter_contributions=computed.counter_contributions,
        placements=computed.placements,
        effects=computed.stored_effects,
        notes=[
            *choice_notes(computed),
            *_companion_notes(gang_card, computed),
            *_limit_notes(gang_card, computed),
        ],
    )


def _held(nodes):
    """Count model profiles, ranks and equipment by content identity.

    Skip broadcast nodes to avoid counting gang equipment once per member.
    Skip suppressed assignments because their facts do not satisfy composition
    requirements while removed.
    """
    from n26.library.models import Profile, Subtype, Wargear

    counted = {}
    for node in nodes:
        if node.broadcast or node.suppressed:
            continue
        thing = node.assignable
        if not isinstance(thing, (Profile, Subtype, Wargear)):
            continue
        # Only the primary profile defines the model's identity for selectors.
        if isinstance(thing, Profile) and not node.is_primary_profile:
            continue
        key = ModifierIndex.key(thing)
        counted[key] = counted.get(key, 0) + 1
    return counted


def _roster_holdings(gang_card):
    """The census a gang-scoped composition rule is read against."""
    return _held(
        node for member in gang_card.members.values() for node in member.all_nodes()
    )


def _companion_notes(gang_card, computed):
    """Describe roster composition shortfalls without removing models.

    Count each member's printed hierarchy subtypes, established at hire.
    """
    from n26.core.notes import WARNING, Note

    if not computed.requirements:
        return []
    tallies = _roster_holdings(gang_card)

    notes = []
    for effect, source, _kind in computed.requirements:
        anchors = tallies.get(ModifierIndex.key(effect.for_each), 0)
        needed = anchors * effect.at_least
        held = tallies.get(ModifierIndex.key(effect.of), 0)
        if anchors and held < needed:
            notes.append(
                Note(
                    text=(
                        f"{anchors} {effect.for_each} need {needed} "
                        f"{effect.of}; the gang has {held} ({source})"
                    ),
                    about=effect.of,
                    level=WARNING,
                )
            )
    return notes


def _limit_notes(gang_card, computed):
    """Describe breaches of gang-level ``AllowsAtMost`` limits.

    Within-limit holdings produce no note, and no holding is refused.
    """
    if not computed.limits:
        return []
    return _over_the_limit(computed.limits, _roster_holdings(gang_card), "the gang")


def limit_notes(card, computed):
    """Describe breaches of per-model ``AllowsAtMost`` limits.

    Count the model's own assignments without querying.
    """
    if not computed.limits:
        return []
    return _over_the_limit(computed.limits, _held(card.all_nodes()), "this model")


def _over_the_limit(limits, tallies, holder):
    """One note per ceiling the holder has gone past, and none otherwise."""
    from n26.core.notes import WARNING, Note

    notes = []
    for effect, source, _kind in limits:
        thing = effect.thing
        if thing is None:
            continue
        count = tallies.get(ModifierIndex.key(thing), 0)
        if count <= effect.at_most:
            continue
        allowance = f"at most {effect.at_most}" if effect.at_most else "none allowed"
        notes.append(
            Note(
                text=f"{holder} holds {count} {thing}; {allowance} ({source})",
                about=thing,
                level=WARNING,
            )
        )
    return notes


def choice_notes(computed):
    """Describe unresolved or repeated choices on the card offering them."""
    return [*_repeat_notes(computed), *_shortfall_notes(computed)]


def _repeat_notes(computed):
    """Report repeated selections when their slot type forbids repeats.

    Modifier offers have no repeat policy, so repeated selections across
    them always produce a note.
    """
    from n26.core.notes import WARNING, Note

    notes = []
    first_chosen_for = {}
    for slot in computed.choices:
        if slot.slot is not None and slot.slot.slot_type.allows_repeats:
            continue
        for pick in slot.picks:
            thing = pick.assignable
            held = first_chosen_for.get(ModifierIndex.key(thing))
            if held is not None:
                notes.append(
                    Note(
                        text=(
                            f"{thing} is chosen for both {held.source} "
                            f"and {slot.source}"
                        ),
                        about=thing,
                        level=WARNING,
                    )
                )
            else:
                first_chosen_for[ModifierIndex.key(thing)] = slot
    return notes


def _shortfall_notes(computed):
    """Report slots with fewer selections than required, without blocking use.

    Modifier offers omit this note; their unresolved choice already remains visible.
    """
    from n26.core.notes import WARNING, Note

    return [
        Note(
            text=f"{slot.kind_label} — {len(slot.picks)} of {slot.min_picks} chosen",
            about=slot.slot,
            level=WARNING,
        )
        for slot in computed.choices
        if slot.slot is not None and len(slot.picks) < slot.min_picks
    ]


class _Facts:
    """The stored facts and earlier rounds' results shared by one round's scopes."""

    def __init__(self, card, computed, guest_picks=()):
        from n26.core import select

        self._select = select
        self._computed = computed
        self._weapons = {}
        # Counter contributions are part of what a threshold reads, and
        # they settle round by round like everything else here: a
        # contribution made in one round is asked about from the next.
        # Granted picks settle the same way, and the gang's granted picks
        # (``guest_picks``) are facts about the member from the start.
        self._model = (
            card.model_matchable()
            .also(
                *(contribution.thing for contribution in computed.subtypes),
                *(contribution.thing for contribution in computed.picks),
                *(contribution.thing for contribution in computed.tables),
                *guest_picks,
            )
            .counting(counter_totals(computed))
        )

    def model(self):
        return self._model

    def weapon(self, node):
        cached = self._weapons.get(node.key)
        if cached is not None:
            return cached
        self._weapons[node.key] = built = self._weapon(node)
        return built

    def _weapon(self, node):
        select = self._select
        base = select.matchable(node.assignable)
        computed_weapon = self._computed.weapons.get(node.key)
        if computed_weapon is None:
            return base
        added = {
            select.key(contribution.thing)
            for contribution in computed_weapon.added_traits
        }
        removed = {
            select.key(contribution.thing)
            for contribution in computed_weapon.removed_traits
        }
        return select.Matchable(
            thing=node.assignable,
            assignables=frozenset((base.assignables | added) - removed),
        )


def _fill_choice_slots(computed, offers, by_cause):
    """Resolve modifier offers from the selections linked to their anchor.

    Resolve explicitly identified offers first, then assign each unmatched
    selection to the first compatible offer. Consume a selection once so
    one pick cannot resolve two choices.

    Treat selections whose offer ID is absent from the current card as
    unnamed. Recreating a modifier offer must not discard existing selections.
    """
    from n26.core import select

    #: The questions this card asks, and the answers already spoken for —
    #: an answer settles one question and no more.
    asked = {effect.pk for effect, _, _, _ in offers}
    claimed, settled = set(), {}

    for order, (effect, _, _, anchor) in enumerate(offers):
        if anchor is None:
            continue
        for node in by_cause.get(anchor.key, []):
            if node.key not in claimed and node.chosen_for_offer_id == effect.pk:
                settled[order] = node
                claimed.add(node.key)
                break

    for order, (effect, _, _, anchor) in enumerate(offers):
        if anchor is None or order in settled:
            continue
        selector = effect.selector()
        for node in by_cause.get(anchor.key, []):
            if node.key in claimed or node.chosen_for_offer_id in asked:
                continue
            if not selector.matches(select.matchable(node.assignable)):
                continue
            settled[order] = node
            claimed.add(node.key)
            break

    for order, (effect, source, source_kind, anchor) in enumerate(offers):
        resolved = settled.get(order)
        computed.choices.append(
            ChoiceSlot(
                kind_label=effect.kind_label,
                source=source,
                source_kind=source_kind,
                anchor=anchor,
                picks=[resolved] if resolved is not None else [],
                offer=effect,
            )
        )


def _fill_slot_choices(computed, given, by_choice, by_holding_choice):
    """Resolve assigned and granted slots on their host card.

    Gang-hosted slots appear only on the gang card. Hidden slots retain
    their effects without displaying a choice. Match selections by anchor
    and slot identity, in acquisition order.

    ``given`` contains computed grants anchored to their stored source.
    Campaign holdings instead anchor choices to their current ownership period.
    """
    from n26.library.models import Slot

    asked = []
    for node in computed.card.all_nodes():
        if not isinstance(node.assignable, Slot):
            continue
        if node.broadcast or node.suppressed:
            continue
        asked.append(
            (
                node.assignable,
                node,
                str(node.assignable),
                kind_of(node.assignable),
                None,
            )
        )
    asked.extend(
        (slot, anchor, source, source_kind, holding)
        for slot, anchor, source, source_kind, holding in given
        if anchor is not None
        or (holding is not None and computed.card.host_kind == GANG)
    )
    # Ordered by what the author said, once the given ones are in: where
    # a choice sits on the card is the slot's own business, and one
    # handed over by a modifier does not belong at the bottom for that
    # reason alone. Stable, so two slots of one position keep the order
    # they arrived in.
    asked.sort(key=lambda part: (part[0].position, part[0].name))

    holding_questions = set()
    for slot, anchor, source, source_kind, holding in asked:
        if slot.hidden or (slot.follows_status and computed.card.host_kind == GANG):
            continue
        if holding is None:
            picks = [
                node
                for node in by_choice.get(anchor.key, ())
                if node.chosen_for_slot_id == slot.pk
            ]
        else:
            address = (holding.pk, holding.ownership_revision, slot.pk)
            if address in holding_questions:
                continue
            holding_questions.add(address)
            picks = by_holding_choice.get(address, ())
        revision = (
            computed.card.current_status_revision if slot.follows_status else None
        )
        picks = (
            [node for node in picks if node.chosen_for_status_revision == revision]
            if slot.follows_status
            else [
                node
                for node in picks
                if not getattr(node.assignable, "record_only", False)
            ]
        )
        computed.choices.append(
            ChoiceSlot(
                status_revision=revision,
                kind_label=slot.choice_label,
                source=str(holding) if holding is not None else source,
                source_kind=kind_of(holding) if holding is not None else source_kind,
                anchor=anchor,
                holding=holding,
                picks=picks,
                slot=slot,
                min_picks=slot.min_picks,
                max_picks=slot.max_picks,
            )
        )


def _fill_drawn_picks(computed, drawn):
    """Add gang-held pick lines after resolving the card's own choices.

    Omit picks already shown in a choice on this card, deduplicate requested
    lines, and exclude modifiers whose carrier was retracted.
    """
    from n26.library.models import Pickable

    asked_here = {pick.key for slot in computed.choices for pick in slot.picks}
    seen = set()
    for node, step in drawn:
        if step.outcome != "reached":
            # Whatever carried it was itself taken away; the plan has
            # already said so and there is nothing to draw.
            continue
        if (
            not isinstance(node.assignable, Pickable)
            or node.key in asked_here
            or node.key in seen
        ):
            step.outcome = "skipped"
            continue
        seen.add(node.key)
        computed.drawn_picks.append(
            DrawnPick(
                node=node,
                kind_label=node.assignable.slot_type.name,
                source=THE_GANG,
                source_kind="gang",
            )
        )


def _bucket(computed, target, thing):
    """Where a contribution belongs: the row its kind declares
    (``card_row`` — subtypes, skills, powers, rules, collections, and
    the ComputedCard's buckets carry the same names), granted equipment,
    or a weapon's traits."""
    from n26.library.models import Asset, AssetTable, Pickable, Wargear, Weapon

    if target.kind == WEAPON_PROFILE:
        return computed.weapons[target.node.key], "traits"
    row = getattr(thing, "card_row", None)
    if row is not None:
        return computed, row
    if isinstance(thing, Asset):
        return computed, "granted_assets"
    if isinstance(thing, (Weapon, Wargear)):
        return computed, "granted_gear"
    if isinstance(thing, Pickable):
        # A granted pick draws no line — its slot is hidden — but it is a
        # fact the next round's conditions read, so it is kept.
        return computed, "picks"
    if isinstance(thing, AssetTable):
        # Likewise a granted table: no line, but holding it is what says
        # the gang may roll on it.
        return computed, "tables"
    return None, None


def _place(computed, target, contribution, carrier=None):
    """Place a grant and return its destination and appended entry.

    The entry is None for duplicate content or kinds without a display line.
    Retraction uses the destination to remove or reattribute the grant.
    """
    holder, kind = _bucket(computed, target, contribution.thing)
    if holder is None:
        return None, "", None
    if kind == "traits":
        holder.added_traits.append(contribution)
        return holder, "added_traits", contribution
    if kind == "granted_assets":
        return computed.card, "granted", _grant_asset(computed, contribution)
    if kind == "granted_gear":
        return computed.card, "granted", _grant_gear(computed, contribution, carrier)
    existing = getattr(holder, kind)
    if contribution.name in {c.name for c in existing}:
        # One skill from two givers is one skill. The edge is logged all
        # the same, so losing one giver does not lose the skill.
        return holder, kind, None
    existing.append(contribution)
    return holder, kind, contribution


def _take_away(computed, target, contribution, source_key, step):
    """Remove computed grants and suppress eligible stored assignments.

    Return the affected entries so ``_retract`` can propagate cancellations
    or restore them if the removal's source is cancelled.
    """
    thing = contribution.thing
    record = _TakenAway(source_key=source_key, thing=thing, step=step, kind=target.kind)
    holder, kind = _bucket(computed, target, thing)
    if holder is not None:
        if kind == "traits":
            holder.removed_traits.append(contribution)
            record.holder, record.field = holder, "removed_traits"
            record.added = contribution
        elif kind in ("granted_gear", "granted_assets"):
            record.holder, record.field = computed.card, "granted"
            record.dropped = _ungrant_gear(computed, contribution)
        else:
            standing = getattr(holder, kind)
            record.holder, record.field = holder, kind
            record.dropped = tuple(
                entry for entry in standing if entry.name == contribution.name
            )
            setattr(
                holder,
                kind,
                [entry for entry in standing if entry.name != contribution.name],
            )
    if target.kind != WEAPON_PROFILE:
        # On a weapon's line a removal is one trait on one gun, never a
        # statement about what the model holds.
        record.hidden, record.refused = _suppress(computed.card, thing)
    return record


def _suppress(card, thing):
    """Hide unpaid stored assignments without changing the database.

    Preserve paid assignments and any assignment with paid descendants, which
    would otherwise be stranded. Return suppressed and preserved nodes separately.
    """
    hidden, refused = [], []
    for node in _stored_lines(card, thing):
        if any(line.carries_money for line in node.walk()):
            refused.append(node)
        else:
            node.suppressed = True
            hidden.append(node)
    return tuple(hidden), tuple(refused)


def _stored_lines(card, thing):
    """The card's own written lines naming this thing — what a removal
    reaches. Granted lines are the grants' own output and are retracted
    through the log instead."""
    wanted = ModifierIndex.key(thing)
    return [
        node
        for node in card.all_nodes()
        if not node.computed and ModifierIndex.key(node.assignable) == wanted
    ]


def stands_whatever_happens(card, thing):
    """Whether a paid stored copy prevents this content from being removed.

    Mirror ``_suppress`` eligibility, including payment in descendants.
    One paid copy is enough even when other free copies can be suppressed.
    """
    lines = _stored_lines(card, thing)
    if not lines:
        return False
    return any(any(line.carries_money for line in node.walk()) for node in lines)


def _retract(computed, log):
    """Propagate removals through grants and other dependent effects.

    Content survives while any granting source remains. Reattribute surviving
    entries without changing their positions. Apply named removals in settlement
    order so mutual removals do not depend on iteration order. Restore effects
    of removals whose own source was cancelled, then settle campaign-default
    exclusions.

    Work entirely in memory, preserving stored assignments and repeatable
    computation. Return content absent from the final card so acquisitions
    can exclude it.
    """
    if not log.removals:
        return set()

    card = computed.card
    ordinary = [record for record in log.removals if not record.defaults_only]
    exclusions = [record for record in log.removals if record.defaults_only]
    # Settle source cancellations before exclusions. Clear their provisional
    # hides while preserving any hide made by a named removal.
    hidden_by_name = {node.key for record in ordinary for node in record.hidden}
    for record in exclusions:
        for node in record.hidden:
            node.suppressed = node.key in hidden_by_name
    #: Stored assignments by the thing they name. Granted lines are the grants'
    #: own output and are retracted through the log instead.
    stored = {}
    for node in card.all_nodes():
        if not node.computed:
            stored.setdefault(ModifierIndex.key(node.assignable), []).append(node)

    edges = {}
    for placed in log.placed:
        edges.setdefault(placed.thing_key, []).append(placed)

    #: The gang's guests. Nothing gives them *here* and no assignment of
    #: theirs stands here, so a removal that names one takes it away all
    #: the same — everything it was doing on this card stops.
    guests = {ModifierIndex.key(c.thing) for c in computed.echoed}

    #: Things no longer on the card at all.
    dead = set()

    def gone(thing_key):
        """Whether neither a surviving grant nor stored assignment supplies this content."""
        if any(not node.suppressed for node in stored.get(thing_key, ())):
            return False
        return all(placed.source_key in dead for placed in edges.get(thing_key, ()))

    def cascade():
        """Recursively retract dependants that lost their final granting source."""
        for _ in range(MAX_CHAIN_DEPTH):
            starved = {
                thing_key
                for thing_key in edges
                if thing_key not in dead and gone(thing_key)
            }
            if not starved:
                return
            dead.update(starved)

    for record in (*ordinary, *exclusions):
        step = record.step
        if record.source_key in dead:
            if not record.defaults_only:
                _put_back(record)
            step.outcome = "retracted"
            continue
        if record.defaults_only:
            for node in record.hidden:
                node.suppressed = True
        if record.kind == WEAPON_PROFILE:
            step.took_away = (*step.took_away, str(record.thing))
            continue
        if record.refused:
            step.refused = (*step.refused, str(record.thing))
            if record.hidden:
                # Held twice, once paid for: the free assignment goes, the
                # purchase stays — and so the thing is still on the card,
                # doing everything it does.
                step.took_away = (*step.took_away, str(record.thing))
            elif step.outcome == "reached":
                step.outcome = "refused"
            continue
        thing_key = ModifierIndex.key(record.thing)
        if record.defaults_only and not gone(thing_key):
            step.took_away = (*step.took_away, str(record.thing))
            continue
        if record.dropped or record.hidden or thing_key in edges or thing_key in guests:
            step.took_away = (*step.took_away, str(record.thing))
        dead.add(thing_key)
        cascade()

    if not dead:
        return dead

    # What a departed thing was doing stops with it.
    for applied in log.applied:
        if applied.source_key in dead:
            _drop(applied.holder, applied.field, applied.payload)

    # A grant whose giver has gone, or whose thing has, is not there any
    # more. Where a live giver of the same thing remains, the entry keeps
    # its place and names that one instead.
    live = {id(placed) for placed in log.placed if _stands(placed, dead)}
    givers = {placed.thing_key: placed for placed in log.placed if id(placed) in live}
    for placed in log.placed:
        if id(placed) in live or placed.payload is None:
            continue
        survivor = givers.get(placed.thing_key)
        _drop(
            placed.holder,
            placed.field,
            placed.payload,
            instead=(
                survivor.contribution
                if survivor is not None and survivor.payload is None
                else None
            ),
        )

    if log.recategorisations:
        standing = [
            category
            for source_key, category in log.recategorisations
            if source_key not in dead
        ]
        computed.sorted_under = standing[-1] if standing else None

    for step in computed.plan:
        if step.outcome == "reached" and ModifierIndex.key(step.source) in dead:
            step.outcome = "retracted"

    return dead


def _stands(placed, dead):
    """Whether a granting edge is still there: giver and thing both."""
    return placed.source_key not in dead and placed.thing_key not in dead


def _drop(holder, field, payload, instead=None):
    """Remove an entry by identity, optionally replacing it in the same position."""
    standing = getattr(holder, field)
    kept = [entry for entry in standing if entry is not payload]
    if instead is not None and len(kept) < len(standing):
        kept.insert(
            next(i for i, entry in enumerate(standing) if entry is payload), instead
        )
    setattr(holder, field, kept)


def _put_back(record):
    """Undo a removal whose own carrier turned out to have been cancelled."""
    for node in record.hidden:
        node.suppressed = False
    if record.holder is None:
        return
    if record.added is not None:
        _drop(record.holder, record.field, record.added)
    if record.dropped:
        setattr(
            record.holder,
            record.field,
            [*getattr(record.holder, record.field), *record.dropped],
        )


def _campaign_gives_type(card, campaign_type_id):
    from n26.library.models import CampaignType

    return any(
        isinstance(node.assignable, CampaignType)
        and node.assignable.pk == campaign_type_id
        and not node.suppressed
        for node in card.all_nodes()
    )


def _campaign_asset_defaults(card, asset_type_id):
    """Stored assets directly supplied by either campaign type carrier."""
    from n26.library.models import Asset, CampaignType

    nodes = {node.key: node for node in card.all_nodes()}
    for node in nodes.values():
        if (
            not isinstance(node.assignable, Asset)
            or node.assignable.asset_type_id != asset_type_id
        ):
            continue
        if node.computed:
            continue
        cause = nodes.get(node.caused_by_key)
        if isinstance(getattr(cause, "assignable", None), CampaignType):
            yield node


def _grant_asset(computed, contribution):
    """Keep each granting edge for retraction; the renderer draws one asset."""
    from n26.core.card import Node

    node = Node(
        assignable=contribution.thing,
        key=("granted-asset", computed.granted_serial, contribution.thing.pk),
        computed=True,
        granted_by=contribution.source,
        granted_by_kind=contribution.source_kind,
        caused_by_key=contribution.root_key,
    )
    computed.granted_serial += 1
    computed.card.granted.append(node)
    return node


def _grant_gear(computed, contribution, carrier):
    """Put one copy of granted equipment on the card.

    No assignment means no sale, transfer, ledger entry or rating.
    Built-ins and option sets are materialised only at acquisition.
    Weapons include their free profiles; paid ammo and accessories
    need a stored assignment to attach to.
    """
    from n26.core.card import Node
    from n26.library.models import Weapon

    card = computed.card
    thing = contribution.thing
    serial = computed.granted_serial
    computed.granted_serial += 1
    node = Node(
        assignable=thing,
        key=("granted", serial, thing.pk),
        rating=0,
        caused_by_key=carrier.key if carrier is not None else None,
        computed=True,
        granted_by=contribution.source,
        granted_by_kind=contribution.source_kind,
    )
    if isinstance(thing, Weapon):
        for profile in thing.profiles.all():
            if profile.price:
                continue
            line = Node(
                assignable=profile,
                key=("granted", serial, thing.pk, profile.pk),
                caused_by_key=node.key,
                is_weapon_profile=True,
                computed=True,
            )
            node.children.append(line)
            # Later rounds may add traits to these profiles.
            computed.weapons[line.key] = ComputedWeapon(node=line)
    card.granted.append(node)
    return node


def _ungrant_gear(computed, contribution):
    """Take back granted nodes — every copy, whoever gave it.

    Stored assignments are handled by ``_suppress``. This only removes
    computed nodes and returns them so a retracted removal can restore
    them.
    """
    card = computed.card
    taken = [node for node in card.granted if node.assignable == contribution.thing]
    gone = {id(node) for node in taken}
    card.granted[:] = [node for node in card.granted if id(node) not in gone]
    return tuple(taken)
