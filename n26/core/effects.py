"""Computing what modifiers do to a card.

The whole layer is one pure function::

    load (fixed queries) -> Card -> compute(card, index) -> ComputedCard

``compute`` issues **no queries**. Everything it needs — the assignments,
their assignables, and the modifiers reachable from them — is loaded first
by ``n26.card`` and handed in as a ``ModifierIndex``. That is what keeps
per-card evaluation affordable: a card without the mount simply is not
handed the mount's assignment, so nothing of the mount's is computed for
it, and no amount of kit on a model changes the query count.

A member's card is computed against the gang's holdings as well as its
own. The gang-hosted assignments ride it as broadcast lines; what the gang
holds **by grant** — a rule an alliance gave it, the hidden carrier a
house's rules hang off — is dealt on beside them as the gang's *guests*.
There is no difference between the two once effects are being applied, so
a guest's modifiers reach the model exactly as an assignment's would; what
a guest never does is draw a line, add a rating, or make its stored effects the
fighter's news. The gang's card settles first, so a bundle something took
away from the gang is a guest on nobody's card.

Order of evaluation, fixed:

1. **Additions run to a fixed point.** A granted thing can itself carry
   modifiers — a mount grants Mounted, Mounted grants two skills — so the
   loop repeats until nothing new appears, with a seen-set so a cycle in
   content terminates instead of spinning.
2. **Then removals**, so they beat additions whatever order sources load.
3. **Then stat changes fold** — sets first, then shifts, which sum.

Most of what a modifier grants is a fact — a subtype, a skill, a trait —
and lands on the ``ComputedCard``. A granted **weapon** is not a fact but
a thing with firing lines, and those lines have to be on the card for a
weapon-scoped modifier to reach them and for a renderer to draw them. So
``compute`` writes them onto ``card.granted``, clearing it first: the
list is this function's output, and computing a card twice must not leave
the bearer holding two of everything.

The consequence for content: a granted weapon appears at the *end* of the
round its grant ran in, so an unconditional weapon scope on the same
carrier — asked during that round — does not see it. Naming the weapon
makes the rule conditional and therefore later, which is what an author
writing "these claws gain…" says anyway.

**Taking something away** is the mirror of all that, and it reaches two
kinds of presence. A *granted* thing is on the card only while something
live gives it, so cancelling it means dropping every granting edge — and
then everything the thing itself was doing goes with it, down the chain,
because what it granted has lost its giver too. A thing two carriers give
survives losing one of them and changes hands to the survivor, which is
why every edge is logged and not just the entry it wrote. A *stored*
assignment is on the card because somebody wrote it down; a removal
**suppresses** it — hides it from every reader, leaving the assignment
exactly where it is — but
only where nothing was paid for it and nothing paid hangs beneath it. A
purchase is never taken away by a read, and nothing paid for is ever
stranded. Removals settle as their round does, so a later round sees a
world without what an earlier one cancelled; the chain and the
suppressions are then carried through in one pass at the end
(``_retract``), which is also where a removal whose own carrier turned out
to be gone is put back.
"""

from dataclasses import dataclass, field

from n26.library.models.modifier import GANG, MODEL, WEAPON_PROFILE

#: A granted thing five levels deep is a content bug, not a use case.
MAX_CHAIN_DEPTH = 5

#: How a line the gang holds names its holder on a member's card. A
#: member's card knows no name for the gang, and every surface says this.
THE_GANG = "the gang"


def kind_of(thing):
    """The plain name of what kind of thing this is: "skill", "wargear"…

    Empty for the kinds a card never draws a row for — a hidden carrier,
    a choice and what was chosen for it. Their names are authored to be
    read ("Strength rolled 6", "Gang Legacy", "Cawdor"), but their kinds
    are the library's own plumbing, and a player's tooltip must never say
    so. Every surface drawing a kind already draws nothing when there is
    none.
    """
    from n26.core.models import CampaignAsset
    from n26.library.models import Hidden, Pickable, Slot

    if isinstance(thing, (Hidden, Slot, Pickable)):
        return ""
    if isinstance(thing, CampaignAsset):
        # A campaign asset is named by what its campaign type calls the
        # asset type — "territory", "racket" — never by the table it sits in.
        return thing.type_label
    return str(thing._meta.verbose_name)


def is_orphan_pick(node):
    """A pickable nobody was offered: a pick with no choice behind it.

    Its slot is what puts it on a card and what gives it its meaning, so
    without one it shows nothing and does nothing — not a line, not a
    modifier, not a fact another rule can match on. An owner may still
    hand one over; it simply waits for a choice to answer.
    """
    from n26.library.models import Pickable

    return isinstance(node.assignable, Pickable) and node.chosen_for_key is None


@dataclass(frozen=True)
class Contribution:
    """Something a modifier added, and what added it."""

    thing: object
    source: str
    source_kind: str = ""
    #: Whether, granted to the gang, it also rides every member's card
    #: as the gang's guest — the granting scope's own say. Meaningless
    #: for a grant to a model, where there is nothing to echo.
    echoes: bool = True
    #: The written line the chain of grants that brought this thing
    #: stands on, however many grants deep it arrived. A grant writes
    #: nothing down, so a choice one gives has no assignment of its own
    #: to be addressed on; this is the one it hangs from instead, and
    #: taking that line away takes the whole chain with it.
    root_key: object = None

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


@dataclass
class CounterContribution:
    """What a modifier adds to a counter, and what added it.

    Nothing is written down: a reading is the stored value plus every
    contribution standing at the moment it is read, so the sum falls
    back the instant a carrier goes. A counter can be contributed to
    with no assignment behind it at all, and then the sum is the whole
    of its reading.
    """

    counter: object
    amount: int
    source: str
    source_kind: str = ""


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


@dataclass
class ChoiceSlot:
    """A choice on a card, resolved or not.

    Two things ask the player to choose: a modifier that offers a
    choice of a specific kind, and a ``Slot`` assigned to the holder.
    Either way the row is computed — shown while whatever offers the
    choice is present — and only what was chosen is stored.

    A slot-borne choice may hold several picks and reads them off
    ``Assignment.chosen_for``, which links to the choice-offering
    assignment.
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
    def chosen_name(self):
        return ", ".join(node.name for node in self.picks) if self.picks else None

    @property
    def identity(self):
        """What tells this choice from the others one anchor asks.

        The offer or the slot behind it — one row of content either way,
        which is what an address can name and find again.
        """
        return self.slot if self.slot is not None else self.offer


@dataclass(frozen=True)
class CategoryPlacement:
    """Where one category sits for this fighter, and who put it there.

    There is no access table — placements are folded from modifiers at
    read time, so they appear and disappear with whatever carries them
    (the profile's declared sets, the Wyrd subtype's powers reveal, a
    wargear that grants Wyrd transitively). The category is fundamental;
    the section is per-fighter; anything unplaced falls back to "Other"
    at browse time.
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
    """A pick the gang holds, drawn on this model's card.

    What the gang picks reaches every member and is listed on none of
    them — unless the pickable carries a modifier saying otherwise, and
    then every model that modifier reaches draws the line. A fact, never
    a control: the choice belongs to whoever was asked, and their card
    draws its own choice row rather than one of these.
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
    """Something a card's kit does beyond adding a line to this card.

    Stored effects write assignments when the thing arrives — a pet wargear
    brings a whole other model — so ``compute`` never runs them. It notes
    them instead, because "this brings a Cyber-mastiff" is worth reading
    both before you buy and after: on a preview it has not happened yet,
    on a real card it did, at hire.
    """

    description: str
    source: str
    source_kind: str
    happened: bool


@dataclass
class PlannedStep:
    """One modifier on one carrier: when it runs, what it says, what it did.

    ``compute`` is pure reading, so the plan and the trace are one
    artifact: build a card's ComputedCard and read ``.plan`` — every step
    in execution order, its round, its scope and effect as sentences, and
    its outcome. This is the debugging surface: what the modifiers are
    doing, in order, as data.
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
    #: True when the carrier is the gang's, dealt onto this card the way
    #: the gang-hosted assignments are: the behaviour reaches this model,
    #: but the thing itself is held by the gang, so nothing here draws it
    #: and its stored effects are the gang's news, said once on the gang's card.
    echoed: bool = False
    #: The card node carrying this modifier — None for discovered
    #: carriers. What "the weapon I am attached to" anchors on.
    node: object = None
    #: The written line this carrier stands on: its own where the card
    #: holds it, and otherwise the one at the foot of the grants that
    #: brought it here. What a choice it gives is addressed on.
    root_key: object = None

    @property
    def scope(self):
        """The scope as a sentence — derived on read, so building the
        plan costs no string formatting unless somebody looks."""
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
    """Stands where a modifier would in an owner-removal's plan step.

    The step never runs through a scope — its targets are fixed by
    construction — so only the two sentences are ever read, and the plan
    stays one shape whoever authored the line.
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
    """The source an owner's own step names.

    Keyed like an assignable so every retraction pass can ask, and keyed
    off all of them: the owner is never granted, so never cancelled.
    """

    class _meta:
        label_lower = "owner"

    pk = None

    def __str__(self):
        return "your edits"


THE_OWNER = _TheOwner()


def _own_removals(card):
    """The owner's removals, ready to settle with round 0.

    Each is an assignment with ``removes`` set, carried on the card as
    machinery (``Card.removals``) rather than as a line. Settling with
    round 0 gives them exactly an unconditional content removal's
    reach: conditional scopes then ask their questions of a world where
    the thing is already gone, and a later round's grant of it stays
    cancelled all the same (``_retract`` keeps the dead dead).
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
    """One granting edge, as the retraction pass remembers it.

    Every edge is logged, including one whose thing another carrier had
    already put on the card (``payload`` is then None): a thing two
    things give must survive losing one of them, and that cannot be told
    from the single entry standing in the row.
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
    """One thing a modifier did that is not a grant, and whose doing it was.

    Retraction drops the entry by identity from the list it was appended
    to, so nothing else in that list is disturbed.
    """

    source_key: object
    holder: object
    field: str
    payload: object


@dataclass
class _TakenAway:
    """One removal that reached its target, and everything it did there.

    A removal settles with its round, before anything knows whether the
    thing carrying it survives — so what it did is written down and
    carried through at the end: onwards, if the removal stands, to
    whatever the cancelled thing was itself doing; backwards, if the
    carrier turns out to have been taken away too.
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


@dataclass
class _Offers:
    """The choices a run collected, before their rows are filled in —
    the offers a modifier made, and the slots one gave.

    A box rather than a bare list so a retracted one is dropped by the
    same code that drops a retracted placement.
    """

    items: list = field(default_factory=list)


@dataclass
class _Log:
    """What one run of ``compute`` did, in the order it did it.

    The trace ``computed.plan`` gives a person, in the form retraction
    needs: every effect keyed by the thing that carried it, so cancelling
    that thing can find its work again.
    """

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
    #: Where skill sets and power families sit for this fighter — see
    #: ``CategoryPlacement``.
    placements: list[CategoryPlacement] = field(default_factory=list)
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
    #: What the *gang* holds by grant, riding this card the way the gang's
    #: own assignments do: its behaviour reaches this model, it draws no line
    #: here, and it is worth nothing. Empty on a gang's own card, where
    #: the same things are ``acquired``.
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
    """Modifiers by the thing that carries them, loaded up front.

    Built by ``n26.card``; ``compute`` only ever reads it, which is what
    makes ``compute`` query-free.
    """

    def __init__(self, by_key=None):
        self._by_key = by_key or {}

    @staticmethod
    def key(thing):
        return (thing._meta.label_lower, thing.pk)

    def add(self, thing, modifiers):
        """Store each modifier with its round, computed once here.

        Compiling the scope's selector and scoring it per ``compute``
        call was the rounds engine's whole overhead; the index is built
        once per render and shared across every card, so this is where
        the work belongs.
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
    """Work out a card's computed subtypes, skills, traits and stat changes.

    Evaluation runs in **rounds by specificity**: a modifier's round
    is the specificity of its scope's
    selector — 0 is unconditional, each condition adds one. Every scope
    in a round asks against the facts **settled before the round began**,
    so order within a round cannot matter; then the round's additions
    apply, then its removals. A more specific round therefore sees what
    less specific rounds granted — the Cutter's unconditional "grants
    Mounted" lands in round 0, and a gang rule for Mounted models
    (round 1) reaches the rider.

    Deterministic by construction: round boundaries come from the
    content's shape, never from iteration order. A carrier granted in
    round r runs its own modifiers no earlier than r, against the same
    snapshot its round sees. The whole run is recorded on
    ``computed.plan``.

    Removals settle with their round, and what they cancel is then
    followed through the chain in one pass at the end — see ``_retract``
    and the module docstring.
    """
    from n26.library.models.modifier import (
        AddsAssignable,
        AllowsAtMost,
        ChangesCategory,
        ChangesStat,
        ContributesToCounter,
        DrawsPick,
        OffersChoice,
        PlacesCategory,
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
    for node in card.all_nodes():
        if node.caused_by_key is not None:
            by_cause.setdefault(node.caused_by_key, []).append(node)
        if node.chosen_for_key is not None:
            by_choice.setdefault(node.chosen_for_key, []).append(node)

    #: Plan-display order within a round; application order is fixed
    #: separately (adds settle before removes).
    effect_order = {
        AddsAssignable: 0,
        RemovesAssignable: 1,
        ChangesStat: 2,
        PlacesCategory: 3,
        OffersChoice: 4,
        RequiresCompanions: 5,
        AllowsAtMost: 6,
        ContributesToCounter: 7,
        DrawsPick: 8,
    }

    def steps_for(
        source, discovered, found_in_round, node=None, echoed=False, root_key=None
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
            )

    # One run of a carrier's modifiers per NODE, not per distinct thing:
    # owning two Hardpoint conversions costs two Attacks. ``seen`` only
    # dedups the granted frontier, exactly as before.
    pending = []
    seen = set()
    for node in card.all_nodes():
        seen.add(ModifierIndex.key(node.assignable))
        if is_orphan_pick(node):
            # A pickable with no choice behind it does nothing at all —
            # see ``is_orphan_pick``.
            continue
        pending.extend(steps_for(node.assignable, False, 0, node=node))

    # The campaign's assets the gang holds are the second kind of carrier.
    # A holding is written nowhere on the card — the gang holds the asset
    # and never owns it — so it stands on no line and is worth nothing,
    # and what its asset's modifiers do is credited to the campaign asset
    # itself, named as its campaign type names the asset type. On a
    # member's card the holdings ride as the gang's guests, the way its assignments ride as
    # broadcast: a scope aimed at every model reaches the fighter, one
    # aimed at the bearer reaches nobody, and a stored effect is never
    # said here.
    guest = getattr(card, "host_kind", MODEL) != GANG
    for campaign_asset in getattr(card, "holdings", ()):
        seen.add(ModifierIndex.key(campaign_asset))
        pending.extend(steps_for(campaign_asset, False, 0, echoed=guest))

    # What the gang holds by grant is dealt on here too. The gang-hosted
    # assignments already ride the card; a thing the gang was *given* has
    # no assignment to ride, and there is no difference between the two
    # from the point of view of applying effects — so it arrives as the
    # gang's guest, drawing nothing and worth nothing, and does everything
    # it does. Something the card already carries is passed over: the
    # assignment it stands on is the more direct telling, and one thing's
    # modifiers run once however many ways it reaches the card.
    # A grant whose scope keeps it the gang's alone never echoes: it
    # prints on the gang's card and touches no fighter.
    echoed = [
        contribution
        for contribution in _from_the_gang(card, index)
        if contribution.echoes and ModifierIndex.key(contribution.thing) not in seen
    ]
    for contribution in echoed:
        seen.add(ModifierIndex.key(contribution.thing))
        # The gang's guest keeps the line it stands on: the gang wrote
        # that one down, and it rides this card as a broadcast line, so a
        # choice the guest gives has an address here after all.
        pending.extend(
            steps_for(
                contribution.thing,
                True,
                0,
                echoed=True,
                root_key=contribution.root_key,
            )
        )

    edits = _own_removals(card)
    round_no = 0
    while (pending or edits) and round_no <= MAX_CHAIN_DEPTH:
        facts = _Facts(card, computed)  # the snapshot every scope in this round sees
        adds, removes = [], []
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
                    # Stored effects write assignments at arrival — running
                    # one here would breed pets on every render. Noted,
                    # never run — and noted **where the scope points**: a
                    # pet collar's targets_model notes on its bearer's
                    # card, a Justicar alliance's targets_gang notes once
                    # on the gang. What the gang holds is never a member
                    # card's news, whether it rides as an assignment or as
                    # a guest.
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
                        # Addressed on the line the giver stands on. That
                        # is the giver's own where the card holds it, and
                        # otherwise the written line its chain of grants
                        # hangs from — so what a grant gives can be asked
                        # and answered like anything else, and un-writing
                        # that line takes the answers with it.
                        given = (
                            effect.thing,
                            lines.get(step.root_key),
                            label,
                            label_kind,
                        )
                        given_slots.items.append(given)
                        log.applied.append(
                            _Applied(source_key, given_slots, "items", given)
                        )
                for target in targets:
                    if isinstance(effect, AddsAssignable):
                        thing = effect.thing
                        adds.append(
                            (
                                target,
                                Contribution(
                                    thing=thing,
                                    source=label,
                                    source_kind=label_kind,
                                    echoes=getattr(scope, "echoes", True),
                                    root_key=step.root_key,
                                ),
                                step.node,
                                source_key,
                            )
                        )
                        step.granted = (*step.granted, str(thing))
                        thing_key = ModifierIndex.key(thing)
                        if thing_key not in seen:
                            seen.add(thing_key)
                            pending.extend(
                                steps_for(thing, True, round_no, root_key=step.root_key)
                            )
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
                        contributed = CounterContribution(
                            counter=effect.counter,
                            amount=effect.amount,
                            source=label,
                            source_kind=label_kind,
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
                    elif isinstance(effect, OffersChoice):
                        # Addressed on the line the offerer stands on, as a
                        # given slot is: an offer carried by something a
                        # modifier granted — the hidden a profile hands its
                        # own narrowed choice on — is answerable, where a
                        # choice with no address could only ever be looked at.
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
        round_no += 1

    computed.echoed = echoed
    dead = _retract(computed, log)
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
    )
    _fill_drawn_picks(computed, drawn)
    return computed


def _from_the_gang(card, index):
    """What the card's gang holds by grant — this card's guests.

    Worked out from the gang's own card, and only once: every member asks
    the same question of the same assignments, so the answer is kept there
    (``GangCard.acquired``). It is the **settled** answer, after the
    gang's own removals have run, so a bundle a corruption cancelled
    reaches nobody.

    Query-free, like everything here: the gang's own assignments came back
    with this card's, and its card was assembled from them. A gang's own card
    has no gang above it and so no guests.
    """
    gang_card = getattr(card, "gang_card", None)
    if gang_card is None:
        return ()
    if gang_card.acquired is None:
        gang_card.acquired = tuple(compute(gang_card, index).acquired)
    return gang_card.acquired


def _acquisitions(log, dead):
    """Every distinct thing a grant put on this card and nothing took back.

    Read off the granting edges rather than the computed lines, because a
    grant need not draw one: a hidden carrier shows nothing and does
    everything, which is how a whole bundle of gang rules hangs off a
    single thing. Keyed by the thing, so what two carriers give is held
    once and named by the first giver still standing.
    """
    held = {}
    for placed in log.placed:
        if not _stands(placed, dead):
            continue
        standing = held.get(placed.thing_key)
        # First giver still standing names it — except that a giver whose
        # grant echoes beats one keeping it the gang's alone, whatever
        # order the batch happened to sort them in: reaching the members
        # must not turn on a modifier's name.
        if standing is None or (placed.contribution.echoes and not standing.echoes):
            held[placed.thing_key] = placed.contribution
    return list(held.values())


def _placed_category(effect, node, by_cause):
    """The category a placement puts somewhere: its own, or — chosen
    mode — the category of whatever was chosen for its carrier's choice.

    What was chosen is an assignment caused by the carrier's, exactly as
    a slot resolves; its assignable's ``category`` names the set — a
    pickable's linked category is the chosen thing's whole payload.
    Nothing chosen, no category.
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

    @property
    def name(self):
        return str(self.thing)


@dataclass
class ComputedGang:
    """What the gang's own card says once its modifiers have run.

    The gang-side sibling of ``ComputedCard``, deliberately slimmer: a
    gang has no statline and no weapons to speak for, so the test
    interface does not carry a fighter's empty buckets
    (design/gang-sheet.md). Same engine underneath — ``compute_gang``
    runs ``compute`` over the ``GangCard`` and keeps what a gang can
    mean: its choice slots (a Venator's ranked trees), computed grants,
    counter readings, and the plan.
    """

    card: object
    plan: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    collections: list = field(default_factory=list)
    counters: list = field(default_factory=list)
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


def counter_readings(card, computed=None):
    """Every counter on a card, and where each one stands.

    A reading is the stored value plus every contribution standing on
    the card. A counter contributed to with no assignment behind it
    still has a reading — it comes back the way a granted rule does,
    with the sum as its whole value and nothing to tally.
    """
    from n26.library.models import Counter

    contributed = counter_totals(computed)
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
        added = 0 if thing_key in taken else contributed.get(thing_key, 0)
        taken.add(thing_key)
        readings.append(
            CounterReading(
                thing=node.assignable, value=(held.value if held else 0) + added
            )
        )
    for contribution in computed.counter_contributions if computed else ():
        thing_key = ModifierIndex.key(contribution.counter)
        if thing_key in taken:
            continue
        taken.add(thing_key)
        readings.append(
            CounterReading(thing=contribution.counter, value=contributed[thing_key])
        )
    return readings


def counter_totals(computed):
    """What modifiers add to each counter, keyed by the counter's key."""
    totals = {}
    for contribution in computed.counter_contributions if computed else ():
        thing_key = ModifierIndex.key(contribution.counter)
        totals[thing_key] = totals.get(thing_key, 0) + contribution.amount
    return totals


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
        counters=counter_readings(gang_card, computed),
        placements=computed.placements,
        effects=computed.stored_effects,
        notes=[
            *choice_notes(computed),
            *_companion_notes(gang_card, computed),
            *_limit_notes(gang_card, computed),
        ],
    )


def _held(nodes):
    """How many of each countable thing these lines amount to.

    What composition rules count: a member's rank and entry, and the gear
    the roster holds. Keyed by identity, so nothing compares names.

    Two lines are passed over. The gang-hosted assignments ride every
    member's card, and counting a broadcast one would make the gang's kit
    read as one copy per member. A suppressed assignment has been taken
    away — it stays
    in the database and is no longer part of what the card holds, so a
    rank a rule cancelled does not prop up a ratio or fill a quota.
    """
    from n26.library.models import Profile, Subtype, Wargear

    counted = {}
    for node in nodes:
        if node.broadcast or node.suppressed:
            continue
        thing = node.assignable
        if not isinstance(thing, (Profile, Subtype, Wargear)):
            continue
        # A Legacy profile rides a card alongside the entry the model was
        # hired as; only the one the card is drawn from says what it is.
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
    """Roster shortfalls against composition asks — said, never fixed.

    The book removes Champions when the scum run out; we say the roster
    is short and leave it to the owner. Counting is of members'
    *printed* hierarchy subtypes: a rank is a hire-time built-in fact.
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
    """Where the roster is over a ceiling a rule states — the census half
    of ``AllowsAtMost``, said on the gang's sheet.

    Only a breach draws a note: a gang inside its limits should not be
    told what it is allowed, and a gang holding none of the thing is the
    quietest case of all. Nothing is refused either way; the book turns
    fighters away and we say the roster is over.
    """
    if not computed.limits:
        return []
    return _over_the_limit(computed.limits, _roster_holdings(gang_card), "the gang")


def limit_notes(card, computed):
    """Where one model is over a ceiling a rule states — the "each" half
    of ``AllowsAtMost``: "Leaders and Champions may be equipped with up
    to one Psychic Familiar each" is a limit on every model it reaches,
    counted over that model's own assignments.

    Breach-only, like the gang's census. Query-free, like everything
    downstream of ``compute``.
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
    """What a card has to say about its choices — said, never enforced.

    Both halves belong on whichever card drew the choice row, so a
    fighter asked for a legacy hears about it on their own card and the
    gang hears about the gang's.
    """
    return [*_repeat_notes(computed), *_shortfall_notes(computed)]


def _repeat_notes(computed):
    """One thing picked for two choices, where the slot type says no
    repeats.

    A modifier's offer says nothing about repeats, so any two of them
    settling on one thing is worth mentioning. A slot's slot type
    decides: where it allows repeats, picking the same pickable twice is
    the content working as written.
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
    """Where a choice holds fewer picks than it asks for.

    A note, never a refusal: leaving a choice open costs nothing and
    making it late costs nothing either. Only a slot states a number —
    a modifier's offer asks for one and says nothing when it is open,
    the row itself being the reminder.
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
    """What a round's scopes ask against: printed facts plus everything
    settled by earlier rounds. Built once per round, so every question in
    the round sees the same world."""

    def __init__(self, card, computed):
        from n26.core import select

        self._select = select
        self._computed = computed
        self._weapons = {}
        # Counter contributions are part of what a threshold reads, and
        # they settle round by round like everything else here: a
        # contribution made in one round is asked about from the next.
        self._model = (
            card.model_matchable()
            .also(*(contribution.thing for contribution in computed.subtypes))
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
    """Resolve each offered choice against what the anchor has caused.

    What is chosen is stored as an assignment caused by the carrier's, and
    it names the question it answers — which is what keeps two choices of
    one kind on one line apart, a primary role and a secondary one being
    settled by the same sort of thing.

    An answer naming no question is read the only way left: the first
    question whose kind it fits takes it. One answer settles one question
    however it was written, so a line asking twice with a single such
    answer has one question settled and one still open to be answered,
    rather than two reading as answered from one click.

    Questions holding their own answers are settled before that, because
    an answer given to one question must not be taken by another that
    merely could have had it. And an answer naming a question this card no
    longer asks is read like an unnamed one rather than lost: composing a
    modifier writes its question afresh, and nobody's card should empty
    because an author reworded it.
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


def _fill_slot_choices(computed, given, by_choice):
    """A choice row for every slot the card holds, and what answers it.

    A slot asks on the card it is *hosted* on, so a gang's slot is asked
    once on the gang's own card rather than again on every member's — the
    same rule that keeps the gang's kit off their cards. A hidden slot
    asks nothing at all: what is picked for it still applies, which is
    how several things arrive together under one name.

    What answers it is read off ``chosen_for``: the picks naming this
    choice's own assignment, narrowed to the ones naming this slot, in
    the order they were written. The pair is what keeps two choices
    apart wherever one assignment asks both — two slots a single thing
    gave share an anchor, and only the slot tells their picks apart.

    ``given`` holds the slots a modifier handed over, which have no
    assignment of their own — the choice they open is anchored on the
    written line the giver stands on, so un-writing that retracts this
    one too. A slot given by something standing on no written line at
    all has nowhere to be asked, and is not.
    """
    from n26.library.models import Slot

    asked = []
    for node in computed.card.all_nodes():
        if not isinstance(node.assignable, Slot):
            continue
        if node.broadcast or node.suppressed:
            continue
        asked.append(
            (node.assignable, node, str(node.assignable), kind_of(node.assignable))
        )
    asked.extend(
        (slot, anchor, source, source_kind)
        for slot, anchor, source, source_kind in given
        if anchor is not None
    )
    # Ordered by what the author said, once the given ones are in: where
    # a choice sits on the card is the slot's own business, and one
    # handed over by a modifier does not belong at the bottom for that
    # reason alone. Stable, so two slots of one position keep the order
    # they arrived in.
    asked.sort(key=lambda part: (part[0].position, part[0].name))

    for slot, anchor, source, source_kind in asked:
        if slot.hidden:
            continue
        picks = [
            node
            for node in by_choice.get(anchor.key, ())
            if node.chosen_for_slot_id == slot.pk
        ]
        computed.choices.append(
            ChoiceSlot(
                kind_label=slot.choice_label,
                source=source,
                source_kind=source_kind,
                anchor=anchor,
                picks=picks,
                slot=slot,
                min_picks=slot.min_picks,
                max_picks=slot.max_picks,
            )
        )


def _fill_drawn_picks(computed, drawn):
    """The gang's picks this card draws, once its own questions are known.

    A pick is drawn here only where this card does not ask the question
    it settles. The card that was asked draws a choice row holding the
    same pick and leading to the picker, so a second line would say it
    twice and offer nothing.

    Read after the card has settled, so a carrier something took away
    draws nothing (its step reads ``retracted`` by then), and two
    modifiers saying to draw one pick draw one line.
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
    the ComputedCard's buckets carry the same names), a granted weapon,
    or a weapon's traits."""
    from n26.library.models import Weapon

    if target.kind == WEAPON_PROFILE:
        return computed.weapons[target.node.key], "traits"
    row = getattr(thing, "card_row", None)
    if row is not None:
        return computed, row
    if isinstance(thing, Weapon):
        return computed, "granted_weapons"
    return None, None


def _place(computed, target, contribution, carrier=None):
    """Put a grant where its kind says it goes.

    Answers with the list it landed in — the holder and the attribute
    name — and the entry appended, which is None where a same-named entry
    already stood or where the kind draws nothing at all. Retraction
    needs all three: the entry to take back out, and the destination to
    hand the thing to another giver in.
    """
    holder, kind = _bucket(computed, target, contribution.thing)
    if holder is None:
        return None, "", None
    if kind == "traits":
        holder.added_traits.append(contribution)
        return holder, "added_traits", contribution
    if kind == "granted_weapons":
        return computed.card, "granted", _grant_weapon(computed, contribution, carrier)
    existing = getattr(holder, kind)
    if contribution.name in {c.name for c in existing}:
        # One skill from two givers is one skill. The edge is logged all
        # the same, so losing one giver does not lose the skill.
        return holder, kind, None
    existing.append(contribution)
    return holder, kind, contribution


def _take_away(computed, target, contribution, source_key, step):
    """Cancel one thing on one target, and say what that came to.

    Three things can be standing in the way of a thing being gone, and
    this reaches all of them: a computed entry in a card row, a granted
    weapon and its lines, and a **stored assignment** — the fighter's
    built-in kit, a rule that arrived with the gang type — which is hidden
    rather than written to. What it did is returned as a record: the chain
    from here is followed once, at the end, by ``_retract``.
    """
    thing = contribution.thing
    record = _TakenAway(source_key=source_key, thing=thing, step=step, kind=target.kind)
    holder, kind = _bucket(computed, target, thing)
    if holder is not None:
        if kind == "traits":
            holder.removed_traits.append(contribution)
            record.holder, record.field = holder, "removed_traits"
            record.added = contribution
        elif kind == "granted_weapons":
            record.holder, record.field = computed.card, "granted"
            record.dropped = _ungrant_weapon(computed, contribution)
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
    """Hide the stored assignments of a thing a removal cancelled.

    Innate kit is an assignment nobody paid for — a fighter's built-in
    gun, a rule the gang type brought — and a removal reaches it: the
    assignment stays in the database and stops being drawn, so taking the
    remover away brings it back on the next read.

    Never a purchase, and never an assignment with a purchase hanging
    beneath it:
    an accessory somebody bought for a built-in gun would be stranded, so
    the gun stays. Answers with what it hid and what it left alone.
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
    """Whether taking this away would leave it on the card regardless.

    The mirror of what :func:`_suppress` refuses: a written line nobody
    paid for is hidden, and one with money behind it is left exactly
    where it is. So a thing every line of which carries money cannot be
    taken away at all, and a surface offering to do so has to ask this
    first — otherwise it writes a removal that changes nothing and then
    reports a loss the card denies.

    Held twice, once paid for, counts as standing: the free line goes and
    the thing is still there, doing everything it does.
    """
    lines = _stored_lines(card, thing)
    if not lines:
        return False
    return any(any(line.carries_money for line in node.walk()) for node in lines)


def _retract(computed, log):
    """Follow every removal through to what it really cost the card.

    A removal cancels a thing; this pass works out the rest. What the
    thing was doing stops — every grant it made, stat it shifted,
    category it placed, question it asked — and a thing it granted is
    itself gone unless something else still gives it, which carries on
    down the chain. A thing two carriers gave survives losing one, and
    changes hands: the entry keeps its place and names the survivor.

    Removals are taken in the order they settled, so an earlier round's
    removal is never undone by a later one, and two things cancelling
    each other both go rather than the answer depending on which was
    read first. A removal whose own carrier turns out to have been
    cancelled never happened, and what it took is put back.

    Nothing here queries, and nothing here is written down: the card
    keeps every assignment it had, and a card computed again from the same
    assignments comes out the same.

    Answers with the things that turned out not to be on the card at all,
    which is what a reader of what the card acquired must leave out.
    """
    if not log.removals:
        return set()

    card = computed.card
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
        """Nothing gives this any more, and no assignment of it stands."""
        if any(not node.suppressed for node in stored.get(thing_key, ())):
            return False
        return all(placed.source_key in dead for placed in edges.get(thing_key, ()))

    def cascade():
        """Whatever the last cancellation starved, and so on down."""
        for _ in range(MAX_CHAIN_DEPTH):
            starved = {
                thing_key
                for thing_key in edges
                if thing_key not in dead and gone(thing_key)
            }
            if not starved:
                return
            dead.update(starved)

    for record in log.removals:
        step = record.step
        if record.source_key in dead:
            _put_back(record)
            step.outcome = "retracted"
            continue
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
    """Take one entry out of a computed list by identity, optionally
    putting another in its place — so the entry keeps its position when a
    thing simply changes hands."""
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


def _grant_weapon(computed, contribution, carrier):
    """Put a granted weapon on the card, with its free firing lines.

    Free kit, and the card says so by what the lines are made of: no
    assignment, so nothing to sell and nothing on the ledger, and a
    rating of zero, so the gang is worth the same with it as without.

    Only the lines that come with the gun. A paid firing line is ammo
    somebody bought, and nobody bought this — so a granted weapon offers
    none, and takes no accessories either: both hang off a purchase.

    Every grant is its own weapon, where every grant of one skill is the
    same skill: two things each handing the bearer a stub gun leave them
    holding two stub guns. Answers with the line it dealt, which is what
    a retraction takes back.
    """
    from n26.core.card import Node

    card = computed.card
    weapon = contribution.thing
    serial = computed.granted_serial
    computed.granted_serial += 1
    node = Node(
        assignable=weapon,
        key=("granted", serial, weapon.pk),
        rating=0,
        caused_by_key=carrier.key if carrier is not None else None,
        computed=True,
    )
    for profile in weapon.profiles.all():
        if profile.price:
            continue
        line = Node(
            assignable=profile,
            key=("granted", serial, weapon.pk, profile.pk),
            caused_by_key=node.key,
            is_weapon_profile=True,
            computed=True,
        )
        node.children.append(line)
        # Registered here and not at the top of ``compute``: a later, more
        # specific round may name this weapon and add a trait to it, and
        # the trait needs somewhere to land.
        computed.weapons[line.key] = ComputedWeapon(node=line)
    card.granted.append(node)
    return node


def _ungrant_weapon(computed, contribution):
    """Take back a granted weapon — every copy of it, whoever gave it.

    A weapon the gang **bought** is a stored assignment, and one nobody
    paid for is hidden rather than unbought (``_suppress``); either way this
    touches only the lines a grant put there. Answers with the lines it
    took, so a retracted removal can put them back.
    """
    card = computed.card
    taken = [node for node in card.granted if node.assignable == contribution.thing]
    gone = {id(node) for node in taken}
    card.granted[:] = [node for node in card.granted if id(node) not in gone]
    return tuple(taken)
