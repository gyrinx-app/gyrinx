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
own. The gang's rows ride it as broadcast lines; what the gang holds **by
grant** — a rule an alliance gave it, the hidden carrier a house's rules
hang off — is dealt on beside them as the gang's *guests*. There is no
difference between the two once effects are being applied, so a guest's
modifiers reach the model exactly as a row's would; what a guest never
does is draw a line, add a rating, or make its stored effects the
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
why every edge is logged and not just the entry it wrote. A *stored* row
is on the card because somebody wrote it down; a removal **suppresses**
it — hides it from every reader, leaving the row exactly where it is — but
only where nothing was paid for it and nothing paid hangs beneath it. A
purchase is never taken away by a read, and nothing paid for is ever
stranded. Removals settle as their round does, so a later round sees a
world without what an earlier one cancelled; the chain and the
suppressions are then carried through in one pass at the end
(``_retract``), which is also where a removal whose own carrier turned out
to be gone is put back.
"""

from dataclasses import dataclass, field

from n26.library.models.modifier import MODEL, WEAPON_PROFILE

#: A granted thing five levels deep is a content bug, not a use case.
MAX_CHAIN_DEPTH = 5


def kind_of(thing):
    """The plain name of what kind of thing this is: "skill", "wargear"…

    Empty for a hidden carrier: its name is authored to be read ("Strength
    rolled 6"), but its kind is the library's own plumbing, and a player's
    tooltip must never say so. Every surface drawing a kind already draws
    nothing when there is none.
    """
    from n26.library.models import Hidden

    if isinstance(thing, Hidden):
        return ""
    return str(thing._meta.verbose_name)


@dataclass(frozen=True)
class Contribution:
    """Something a modifier added, and what added it."""

    thing: object
    source: str
    source_kind: str = ""

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
    """A choice a modifier offers, resolved or not.

    The slot is computed — present while its carrier is — and only what
    was chosen is stored, as an assignment caused by the carrier's.
    Unresolved is the absence of that row: nothing pending is written.
    """

    kind_label: str
    source: str
    source_kind: str
    anchor: object  # the card node carrying the offer
    resolved_with: object = None  # the card node chosen for it, if any
    #: The offer itself, so a picker can ask what this fighter may choose
    #: (``n26.core.browse.offered_by``). Its section narrowing needs the card,
    #: which the slot does not carry — hence asking rather than storing.
    offer: object = None

    @property
    def is_resolved(self):
        return self.resolved_with is not None

    @property
    def chosen_name(self):
        return self.resolved_with.name if self.resolved_with else None


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
    #: The CollectionSection row — the collection's own schema, carrying
    #: the tier's name, its position, and which collection this placement
    #: is scoped to.
    section: object
    source: str
    source_kind: str


@dataclass(frozen=True)
class StoredEffect:
    """Something a card's kit does beyond adding a line to this card.

    Stored effects write rows when the thing is assigned — a pet wargear
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
    #: retracted, because the rows it wrote are still there),
    #: ``retracted`` — it ran, and then whatever carried it was itself
    #: taken away, so its work was undone — or ``refused``, a removal
    #: that found only rows somebody had paid for.
    outcome: str = "pending"
    granted: tuple = ()
    #: What a removal actually cancelled: a grant, a stored row, or both.
    took_away: tuple = ()
    #: What a removal left alone because money stands behind it.
    refused: tuple = ()
    #: True when the carrier arrived via a grant rather than the card.
    discovered: bool = False
    #: True when the carrier is the gang's, dealt onto this card the way
    #: the gang's rows are: the behaviour reaches this model, but the
    #: thing itself is held by the gang, so nothing here draws it and its
    #: stored effects are the gang's news, said once on the gang's card.
    echoed: bool = False
    #: The card node carrying this modifier — None for discovered
    #: carriers. What "the weapon I am attached to" anchors on.
    node: object = None

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
    #: Stored rows this hid, and stored rows it left alone because money
    #: stands behind them.
    hidden: tuple = ()
    refused: tuple = ()


@dataclass
class _Offers:
    """The choice offers a run collected, before the slots are filled.

    A box rather than a bare list so a retracted offer is dropped by the
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
    #: The category heading this model sorts under on the gang sheet,
    #: when a rule re-files them — None sorts by the profile's own.
    sorted_under: object = None
    weapons: dict = field(default_factory=dict)
    choices: list[ChoiceSlot] = field(default_factory=list)
    stored_effects: list[StoredEffect] = field(default_factory=list)
    #: Gang-scoped composition asks (``RequiresCompanions``), collected
    #: here and resolved against the roster by ``compute_gang`` — only a
    #: gang card ever gathers any.
    requirements: list = field(default_factory=list)
    #: Composition ceilings (``AllowsAtMost``), collected here and folded
    #: against what is held by ``limit_notes``. A gang card gathers the
    #: ones aimed at the gang and counts the roster; a model's card
    #: gathers the ones aimed at it and counts its own rows.
    limits: list = field(default_factory=list)
    #: How many granted lines have been dealt. A line's key is built from
    #: it, so a key stays unique even where a grant was taken back and
    #: another dealt after it.
    granted_serial: int = 0
    #: What a modifier put on this card and nothing took back — what the
    #: card holds by grant rather than by row, whether or not the grant
    #: drew anything. A gang's are dealt onto every member's card, where
    #: they arrive as ``echoed``.
    acquired: list[Contribution] = field(default_factory=list)
    #: What the *gang* holds by grant, riding this card the way the gang's
    #: own rows do: its behaviour reaches this model, it draws no line
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

    is_assigned = {
        ModifierIndex.key(node.assignable): node.assignment is not None
        for node in card.all_nodes()
    }
    anchors = {ModifierIndex.key(node.assignable): node for node in card.all_nodes()}
    offers = _Offers()
    log = _Log()

    # Chosen rows by what caused them. What a choice settles on is a
    # stored row — a printed fact — so this is built once, before the
    # rounds: a chosen-mode placement in any round reads the same
    # settled row a slot does.
    by_cause = {}
    for node in card.all_nodes():
        if node.caused_by_key is not None:
            by_cause.setdefault(node.caused_by_key, []).append(node)

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
    }

    def steps_for(source, discovered, found_in_round, node=None, echoed=False):
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
            )

    # One run of a carrier's modifiers per NODE, not per distinct thing:
    # owning two Hardpoint conversions costs two Attacks. ``seen`` only
    # dedups the granted frontier, exactly as before.
    pending = []
    seen = set()
    for node in card.all_nodes():
        seen.add(ModifierIndex.key(node.assignable))
        pending.extend(steps_for(node.assignable, False, 0, node=node))

    # What the gang holds by grant is dealt on here too. The gang's own
    # rows already ride the card; a thing the gang was *given* has no row
    # to ride, and there is no difference between the two from the point
    # of view of applying effects — so it arrives as the gang's guest,
    # drawing nothing and worth nothing, and does everything it does.
    # Something the card already carries is passed over: the row it
    # stands on is the more direct telling, and one thing's modifiers run
    # once however many ways it reaches the card.
    echoed = [
        contribution
        for contribution in _from_the_gang(card, index)
        if ModifierIndex.key(contribution.thing) not in seen
    ]
    for contribution in echoed:
        seen.add(ModifierIndex.key(contribution.thing))
        pending.extend(steps_for(contribution.thing, True, 0, echoed=True))

    round_no = 0
    while pending and round_no <= MAX_CHAIN_DEPTH:
        facts = _Facts(card, computed)  # the snapshot every scope in this round sees
        adds, removes = [], []

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
                    # Stored effects write rows at assign time — running one
                    # here would breed pets on every render. Noted, never
                    # run — and noted **where the scope points**: a pet
                    # collar's targets_model notes on its bearer's card, a
                    # Justicar alliance's targets_gang notes once on the
                    # gang. What the gang holds is never a member card's
                    # news, whether it rides as a row or as a guest.
                    gang_held = step.echoed or (
                        step.node is not None and step.node.broadcast
                    )
                    if gang_held or not scope.targets(card, facts, carrier=step.node):
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
                    # about rows that were written when the thing was
                    # assigned, and a removal is a read. The pet it brought
                    # is still on the roster, so the card goes on saying
                    # where it came from.
                    computed.stored_effects.append(note)
                    step.outcome = "noted"
                    computed.plan.append(step)
                    continue

                targets = [
                    target
                    for target in scope.targets(card, facts, carrier=step.node)
                    if effect.accepts(target.kind)
                ]
                if not targets:
                    step.outcome = "skipped"
                    computed.plan.append(step)
                    continue
                step.outcome = "reached"
                label, label_kind = str(step.source), kind_of(step.source)
                for target in targets:
                    if isinstance(effect, AddsAssignable):
                        thing = effect.thing
                        adds.append(
                            (
                                target,
                                Contribution(
                                    thing=thing, source=label, source_kind=label_kind
                                ),
                                step.node,
                                source_key,
                            )
                        )
                        step.granted = (*step.granted, str(thing))
                        thing_key = ModifierIndex.key(thing)
                        if thing_key not in seen:
                            seen.add(thing_key)
                            pending.extend(steps_for(thing, True, round_no))
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
                    elif isinstance(effect, OffersChoice):
                        offer = (
                            effect,
                            label,
                            label_kind,
                            anchors.get(source_key),
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
    return computed


def _from_the_gang(card, index):
    """What the card's gang holds by grant — this card's guests.

    Worked out from the gang's own card, and only once: every member asks
    the same question of the same rows, so the answer is kept there
    (``GangCard.acquired``). It is the **settled** answer, after the
    gang's own removals have run, so a bundle a corruption cancelled
    reaches nobody.

    Query-free, like everything here: the gang's rows came back with this
    card's own, and its card was assembled from them. A gang's own card
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

    Read off the granting edges rather than the computed rows, because a
    grant need not draw one: a hidden carrier shows nothing and does
    everything, which is how a whole bundle of gang rules hangs off a
    single thing. Keyed by the thing, so what two carriers give is held
    once and named by the first giver still standing.
    """
    held = {}
    for placed in log.placed:
        if _stands(placed, dead):
            held.setdefault(placed.thing_key, placed.contribution)
    return list(held.values())


def _placed_category(effect, node, by_cause):
    """The category a placement puts somewhere: its own, or — chosen
    mode — the home of whatever was chosen for its carrier's choice.

    What was chosen is an assignment caused by the carrier's, exactly as
    a slot resolves; its assignable's ``category`` home names the set
    (a ``SkillTree`` token's whole payload). Nothing chosen, no category.
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


def counter_readings(card):
    """Every counter on a card, with where it stands. Rows only."""
    from n26.library.models import Counter

    readings = []
    for node in card.all_nodes():
        if isinstance(node.assignable, Counter):
            held = (
                getattr(node.assignment, "counter_value", None)
                if node.assignment is not None
                else None
            )
            readings.append(
                CounterReading(thing=node.assignable, value=held.value if held else 0)
            )
    return readings


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
        counters=counter_readings(gang_card),
        placements=computed.placements,
        effects=computed.stored_effects,
        notes=[
            *_gang_notes(computed),
            *_companion_notes(gang_card, computed),
            *_limit_notes(gang_card, computed),
        ],
    )


def _held(nodes):
    """How many of each countable thing these lines amount to.

    What composition rules count: a member's rank and entry, and the gear
    the roster holds. Keyed by identity, so nothing compares names.

    Two lines are passed over. The gang's own rows ride every member's
    card, and counting a broadcast one would make the gang's kit read as
    one copy per member. A suppressed row has been taken away — it stays
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
    counted over that model's own rows.

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


def _gang_notes(computed):
    """Incoherence worth mentioning, never blocking — inform, not police."""
    from n26.core.notes import WARNING, Note

    notes = []
    first_chosen_for = {}
    for slot in computed.choices:
        if slot.resolved_with is None:
            continue
        thing = slot.resolved_with.assignable
        held = first_chosen_for.get(ModifierIndex.key(thing))
        if held is not None:
            notes.append(
                Note(
                    text=(
                        f"{thing} is chosen for both {held.source} and {slot.source}"
                    ),
                    about=thing,
                    level=WARNING,
                )
            )
        else:
            first_chosen_for[ModifierIndex.key(thing)] = slot
    return notes


class _Facts:
    """What a round's scopes ask against: printed facts plus everything
    settled by earlier rounds. Built once per round, so every question in
    the round sees the same world."""

    def __init__(self, card, computed):
        from n26.core import select

        self._select = select
        self._computed = computed
        self._weapons = {}
        self._model = card.model_matchable().also(
            *(contribution.thing for contribution in computed.subtypes)
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

    What is chosen is stored as an assignment caused by the carrier's; a
    slot reads as resolved when such a row matches the offer's selector.
    """
    from n26.core import select

    for effect, source, source_kind, anchor in offers:
        resolved = None
        if anchor is not None:
            selector = effect.selector()
            for node in by_cause.get(anchor.key, []):
                if selector.matches(select.matchable(node.assignable)):
                    resolved = node
                    break
        computed.choices.append(
            ChoiceSlot(
                kind_label=effect.kind_label,
                source=source,
                source_kind=source_kind,
                anchor=anchor,
                resolved_with=resolved,
                offer=effect,
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
    this reaches all of them: a computed entry in a row, a granted weapon
    and its lines, and a **stored row** — the fighter's built-in kit, a
    rule that arrived with the gang type — which is hidden rather than
    written to. What it did is returned as a record: the chain from here
    is followed once, at the end, by ``_retract``.
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
    """Hide the stored rows of a thing a removal cancelled.

    Innate kit is a row nobody paid for — a fighter's built-in gun, a
    rule the gang type brought — and a removal reaches it: the row stays
    in the database and stops being drawn, so taking the remover away
    brings it back on the next read.

    Never a purchase, and never a row with a purchase hanging beneath it:
    an accessory somebody bought for a built-in gun would be stranded, so
    the gun stays. Answers with what it hid and what it left alone.
    """
    hidden, refused = [], []
    wanted = ModifierIndex.key(thing)
    for node in card.all_nodes():
        if node.computed or ModifierIndex.key(node.assignable) != wanted:
            continue
        if any(line.carries_money for line in node.walk()):
            refused.append(node)
        else:
            node.suppressed = True
            hidden.append(node)
    return tuple(hidden), tuple(refused)


def _retract(computed, log):
    """Follow every removal through to what it really cost the card.

    A removal cancels a thing; this pass works out the rest. What the
    thing was doing stops — every grant it made, stat it shifted,
    category it placed, question it asked — and a thing it granted is
    itself gone unless something else still gives it, which carries on
    down the chain. A thing two carriers gave survives losing one, and
    changes hands: the row keeps its place and names the survivor.

    Removals are taken in the order they settled, so an earlier round's
    removal is never undone by a later one, and two things cancelling
    each other both go rather than the answer depending on which was
    read first. A removal whose own carrier turns out to have been
    cancelled never happened, and what it took is put back.

    Nothing here queries, and nothing here is written down: the card
    keeps every row it had, and a card computed again from the same rows
    comes out the same.

    Answers with the things that turned out not to be on the card at all,
    which is what a reader of what the card acquired must leave out.
    """
    if not log.removals:
        return set()

    card = computed.card
    #: Stored rows by the thing they name. Granted lines are the grants'
    #: own output and are retracted through the log instead.
    stored = {}
    for node in card.all_nodes():
        if not node.computed:
            stored.setdefault(ModifierIndex.key(node.assignable), []).append(node)

    edges = {}
    for placed in log.placed:
        edges.setdefault(placed.thing_key, []).append(placed)

    #: The gang's guests. Nothing gives them *here* and no row of theirs
    #: stands here, so a removal that names one takes it away all the same
    #: — everything it was doing on this card stops.
    guests = {ModifierIndex.key(c.thing) for c in computed.echoed}

    #: Things no longer on the card at all.
    dead = set()

    def gone(thing_key):
        """Nothing gives this any more, and no row of it still stands."""
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
                # Held twice, once paid for: the free row goes, the
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
    # more. Where a live giver of the same thing remains, the row keeps
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
    putting another in its place — so the row keeps its position when a
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

    A weapon the gang **bought** is a stored row, and one nobody paid for
    is hidden rather than unbought (``_suppress``); either way this
    touches only the lines a grant put there. Answers with the lines it
    took, so a retracted removal can put them back.
    """
    card = computed.card
    taken = [node for node in card.granted if node.assignable == contribution.thing]
    gone = {id(node) for node in taken}
    card.granted[:] = [node for node in card.granted if id(node) not in gone]
    return tuple(taken)
