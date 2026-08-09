"""Computing what modifiers do to a card.

The whole layer is one pure function::

    load (fixed queries) -> Card -> compute(card, index) -> ComputedCard

``compute`` issues **no queries**. Everything it needs — the assignments,
their assignables, and the modifiers reachable from them — is loaded first
by ``n26.card`` and handed in as a ``ModifierIndex``. That is what keeps
per-card evaluation affordable: a card without the mount simply is not
handed the mount's assignment, so nothing of the mount's is computed for
it, and no amount of kit on a model changes the query count.

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
"""

from dataclasses import dataclass, field

from n26.library.models.modifier import MODEL, WEAPON_PROFILE

#: A granted thing five levels deep is a content bug, not a use case.
MAX_CHAIN_DEPTH = 5


def kind_of(thing):
    """The plain name of what kind of thing this is: "skill", "wargear"…"""
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

    The slot is computed — present while its carrier is — and only the
    answer is stored, as an assignment caused by the carrier's. Unresolved
    is the absence of that answer: nothing pending is written.
    """

    kind_label: str
    source: str
    source_kind: str
    anchor: object  # the card node carrying the offer
    resolved_with: object = None  # the card node that answers it, if any
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
    outcome: str = "pending"  # reached / skipped / noted
    granted: tuple = ()
    #: True when the carrier arrived via a grant rather than the card.
    discovered: bool = False
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
        did = f" -> granted {', '.join(self.granted)}" if self.granted else ""
        return (
            f"round {self.ran_in}: [{self.scope}] {self.effect} "
            f"(from {self.source}) — {self.outcome}{did}"
        )


@dataclass
class ComputedCard:
    """What a card looks like once its modifiers have been worked out."""

    card: object
    #: The plan-and-trace: every step in execution order. See PlannedStep.
    plan: list[PlannedStep] = field(default_factory=list)
    subtypes: list[Contribution] = field(default_factory=list)
    skills: list[Contribution] = field(default_factory=list)
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
    weapons: dict = field(default_factory=dict)
    choices: list[ChoiceSlot] = field(default_factory=list)
    stored_effects: list[StoredEffect] = field(default_factory=list)
    #: Gang-scoped composition asks (``RequiresCompanions``), collected
    #: here and resolved against the roster by ``compute_gang`` — only a
    #: gang card ever gathers any.
    requirements: list = field(default_factory=list)

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
    """
    from n26.library.models.modifier import (
        AddsAssignable,
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
    offers = []

    # Answers by what caused them. Choice answers are stored rows — printed
    # facts — so this is built once, before the rounds: a chosen-mode
    # placement in any round reads the same settled answer a slot does.
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
    }

    def steps_for(source, discovered, found_in_round, node=None):
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
            )

    # One run of a carrier's modifiers per NODE, not per distinct thing:
    # owning two Hardpoint conversions costs two Attacks. ``seen`` only
    # dedups the granted frontier, exactly as before.
    pending = []
    seen = set()
    for node in card.all_nodes():
        seen.add(ModifierIndex.key(node.assignable))
        pending.extend(steps_for(node.assignable, False, 0, node=node))

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
                if getattr(effect, "is_stored", False):
                    # Stored effects write rows at assign time — running one
                    # here would breed pets on every render. Noted, never
                    # run — and noted **where the scope points**: a pet
                    # collar's targets_model notes on its bearer's card, a
                    # Justicar alliance's targets_gang notes once on the
                    # gang. A gang-held carrier's echo on a member card is
                    # never its news (the broadcast guard).
                    echoed = step.node is not None and step.node.broadcast
                    if echoed or not scope.targets(card, facts, carrier=step.node):
                        step.outcome = "skipped"
                        computed.plan.append(step)
                        continue
                    computed.stored_effects.append(
                        StoredEffect(
                            description=str(effect),
                            source=str(step.source),
                            source_kind=kind_of(step.source),
                            happened=is_assigned.get(
                                ModifierIndex.key(step.source), False
                            ),
                        )
                    )
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
                            )
                        )
                    elif isinstance(effect, ChangesStat):
                        change = StatChange(
                            stat=effect.stat,
                            mode=effect.mode,
                            amount=effect.amount,
                            source=label,
                            source_kind=label_kind,
                        )
                        if target.kind == MODEL:
                            computed.stat_changes.append(change)
                        else:
                            computed.weapons[target.node.key].stat_changes.append(
                                change
                            )
                    elif isinstance(effect, OffersChoice):
                        offers.append(
                            (
                                effect,
                                label,
                                label_kind,
                                anchors.get(ModifierIndex.key(step.source)),
                            )
                        )
                    elif isinstance(effect, RequiresCompanions):
                        computed.requirements.append((effect, label, label_kind))
                    elif isinstance(effect, PlacesCategory):
                        category = _placed_category(effect, step.node, by_cause)
                        if category is None:
                            # A chosen-mode placement with nothing chosen
                            # yet: nothing to place, and the plan says so.
                            step.outcome = "skipped"
                            continue
                        computed.placements.append(
                            CategoryPlacement(
                                category=category,
                                section=effect.section,
                                source=label,
                                source_kind=label_kind,
                            )
                        )
                computed.plan.append(step)

        # Settle the round: additions first, then removals (agreed order).
        for target, contribution, carrier in adds:
            _place(computed, target, contribution, carrier)
        for target, contribution in removes:
            _unplace(computed, target, contribution)
        round_no += 1

    _fill_choice_slots(computed, offers, by_cause)
    return computed


def _placed_category(effect, node, by_cause):
    """The category a placement puts somewhere: its own, or — chosen
    mode — the home of whatever answered its carrier's choice.

    The answer is an assignment caused by the carrier's, exactly as a
    slot resolves; its assignable's ``category`` home names the set
    (a ``SkillTree`` token's whole payload). No answer, no category.
    """
    if not effect.the_chosen:
        return effect.category
    if node is None:
        return None  # a discovered carrier is caused by nothing on the card
    for answer in by_cause.get(node.key, ()):
        home = getattr(answer.assignable, "category", None)
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
    return ComputedGang(
        card=gang_card,
        plan=computed.plan,
        choices=computed.choices,
        rules=computed.rules,
        collections=computed.collections,
        counters=counter_readings(gang_card),
        placements=computed.placements,
        effects=computed.stored_effects,
        notes=[*_gang_notes(computed), *_companion_notes(gang_card, computed)],
    )


def _companion_notes(gang_card, computed):
    """Roster shortfalls against composition asks — said, never fixed.

    The book removes Champions when the scum run out; we say the roster
    is short and leave it to the owner. Counting is of members'
    *printed* hierarchy subtypes: a rank is a hire-time built-in fact.
    """
    from n26.core.notes import WARNING, Note
    from n26.library.models import Subtype

    if not computed.requirements:
        return []
    tallies = {}
    for member in gang_card.members.values():
        for node in member.all_nodes():
            if node.broadcast or not isinstance(node.assignable, Subtype):
                continue
            key = ModifierIndex.key(node.assignable)
            tallies[key] = tallies.get(key, 0) + 1

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


def _gang_notes(computed):
    """Incoherence worth mentioning, never blocking — inform, not police."""
    from n26.core.notes import WARNING, Note

    notes = []
    first_answered_by = {}
    for slot in computed.choices:
        if slot.resolved_with is None:
            continue
        thing = slot.resolved_with.assignable
        held = first_answered_by.get(ModifierIndex.key(thing))
        if held is not None:
            notes.append(
                Note(
                    text=f"{thing} answers both {held.source} and {slot.source}",
                    about=thing,
                    level=WARNING,
                )
            )
        else:
            first_answered_by[ModifierIndex.key(thing)] = slot
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

    The answer to a choice is stored as an assignment caused by the
    carrier's; a slot reads as resolved when such a row matches the
    offer's selector.
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
    """Where a contribution belongs: subtypes, skills, rules, collections,
    a granted weapon, or a weapon's traits."""
    from n26.library.models import Collection, Rule, Skill, Subtype, Weapon

    if target.kind == WEAPON_PROFILE:
        return computed.weapons[target.node.key], "traits"
    if isinstance(thing, Subtype):
        return computed, "subtypes"
    if isinstance(thing, Skill):
        return computed, "skills"
    if isinstance(thing, Rule):
        return computed, "rules"
    if isinstance(thing, Collection):
        return computed, "collections"
    if isinstance(thing, Weapon):
        return computed, "granted_weapons"
    return None, None


def _place(computed, target, contribution, carrier=None):
    holder, kind = _bucket(computed, target, contribution.thing)
    if holder is None:
        return
    if kind == "traits":
        holder.added_traits.append(contribution)
    elif kind == "granted_weapons":
        _grant_weapon(computed, contribution, carrier)
    else:
        existing = getattr(holder, kind)
        if contribution.name not in {c.name for c in existing}:
            existing.append(contribution)


def _unplace(computed, target, contribution):
    holder, kind = _bucket(computed, target, contribution.thing)
    if holder is None:
        return
    if kind == "traits":
        holder.removed_traits.append(contribution)
    elif kind == "granted_weapons":
        _ungrant_weapon(computed, contribution)
    else:
        setattr(
            holder,
            kind,
            [c for c in getattr(holder, kind) if c.name != contribution.name],
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
    holding two stub guns.
    """
    from n26.core.card import Node

    card = computed.card
    weapon = contribution.thing
    serial = len(card.granted)
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


def _ungrant_weapon(computed, contribution):
    """Take back a granted weapon — every copy of it, whoever gave it.

    It reaches grants only. A weapon the gang bought is a stored row and
    stays exactly where it is: unbuying is an operation, not a read.
    """
    card = computed.card
    card.granted[:] = [
        node for node in card.granted if node.assignable != contribution.thing
    ]
