"""Render structures — what a card and a gang look like, as plain data.

Nothing here knows about HTML, templates or terminals. These are dataclasses
a renderer consumes: the text renderer in ``n26.core.render_text`` is one, a web
template would be another. Building them is pure reading, so they are easy
to assert against in tests without rendering anything.

Query budget is the point. Building a whole gang's worth of cards is a fixed
number of queries regardless of how many models or how much kit — see
``render_gang`` and the assertions in ``tests/sandbox/test_render.py``.
"""

from dataclasses import dataclass, field

from n26.core.card import build_card
from n26.core.effects import kind_of
from n26.library.models import (
    Collection,
    Counter,
    Hidden,
    Power,
    Rule,
    Skill,
    Subtype,
    Weapon,
    WeaponProfile,
)
from n26.library.standard_content import XP_COUNTER

#: The book's weapon slots on one card. Each weapon takes its own
#: ``slots`` against this budget — asterisked weapons two, grenades none.
#: Shown wherever a selection is being weighed; never enforced, because
#: we inform rather than police.
WEAPON_SLOTS_PER_CARD = 3


@dataclass(frozen=True)
class Provenance:
    """Where a thing on a card came from.

    Every assignable a card shows carries one — that is the rule. It is
    data for a renderer to use (a tooltip, a picker link, a "default"
    badge), never something a renderer is obliged to print.
    """

    #: The name of what brought it: "Mounted", "Specialist", "Khimerix".
    #: None means it was taken directly — the common case reads empty.
    source: str | None = None
    #: What kind of thing the source is: "subtype", "wargear", "profile".
    source_kind: str | None = None
    #: The ledger's reason ("bought", "default", …). Stored things only —
    #: a computed thing was never paid for, so it has none.
    reason: str | None = None
    #: True when it is re-derived on read and written nowhere.
    computed: bool = False


@dataclass(frozen=True)
class AssignableLine:
    """One assignable drawn on a card: its name, and where it came from."""

    name: str
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class StatCell:
    """One characteristic on a card."""

    short_name: str
    full_name: str
    value: str
    highlighted: bool = False
    first_of_group: bool = False
    modified_by: list[Provenance] = field(default_factory=list)

    @property
    def modified(self):
        return bool(self.modified_by)


@dataclass
class Statline:
    cells: list[StatCell] = field(default_factory=list)

    def groups(self):
        """Cells split into visual groups, per ``is_first_of_group``."""
        groups = []
        for cell in self.cells:
            if cell.first_of_group or not groups:
                groups.append([])
            groups[-1].append(cell)
        return groups

    def get(self, short_name):
        return next((c for c in self.cells if c.short_name == short_name), None)


@dataclass
class WeaponProfileLine:
    """One of a weapon's profiles: what it added, and how it shoots.

    ``rating`` is what this line contributed to the model's rating — as
    every number on a card is — and not what the thing is worth. Three
    different situations all read 0: the mandatory first profile, which
    genuinely comes free with the weapon; an ammo type bundled into a
    hire, whose 50 credits are inside the package price on the fighter's
    line; and an owner's hand-set gift. A renderer therefore must not call a
    zero "free" — it cannot tell those apart, and the second one is a
    priced item the player paid for.

    Named for ``n26.library.WeaponProfile`` in full, because "profile" alone
    means the fighter entry everywhere else: a plain ``ProfileLine`` would
    read as a line for a ``n26.library.Profile``, which is what a Legacy
    profile will want when it gets one.
    """

    #: Blank for the weapon's own line, which is most of them: the book
    #: prints an Autogun's first line as "Autogun" and names only what hangs
    #: beneath it. A renderer puts the weapon's name on a blank line and the
    #: profile's on a named one — so blank is not missing data to be filled
    #: in with a dash, it is what says which line this is.
    name: str
    rating: int
    statline: Statline = field(default_factory=lambda: Statline())
    traits: list[AssignableLine] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class WeaponLine:
    name: str
    base_rating: int
    #: The assignment's pk, as a string, when this line draws a stored
    #: weapon — what a selection UI keys its checkboxes on. Empty on a
    #: hire preview, whose weapons exist on no ledger and cannot be
    #: selected for anything.
    id: str = ""
    #: Weapon slots this takes on a card — the library's own number:
    #: 1 for most, 2 for asterisked weapons, 0 for grenades.
    slots: int = 1
    profiles: list[WeaponProfileLine] = field(default_factory=list)
    #: Accessories hung off this weapon — a sight, suspensors.
    accessories: list[AssignableLine] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def extras_rating(self):
        """What the paid profiles add on top of the weapon itself."""
        return sum(profile.rating for profile in self.profiles)

    @property
    def total_rating(self):
        return self.base_rating + self.extras_rating

    @property
    def own_line(self):
        """The profile that *is* the weapon — the unnamed one, or None.

        Its stats belong on the weapon's own row, because the book prints
        an Autogun's first line as "Autogun". A weapon may have at most one
        (a database constraint refuses the second: two would print as the
        weapon twice with no way to tell them apart), so ``next`` is a
        lookup and not a choice between candidates.

        Searched rather than taken from position 0: the unnamed line is
        conventionally first but nothing guarantees it, and a renderer that
        assumes so prints the weapon's name on an ammo type's stats.
        """
        return next((p for p in self.profiles if not p.name), None)

    @property
    def named_profiles(self):
        """The profiles that get a row beneath the weapon — the named ones.

        With ``own_line`` this is the whole layout rule, kept here so the
        card on screen, the card on paper and the card as text derive it
        rather than each deciding it. They had drifted once already.
        """
        return [p for p in self.profiles if p.name]


@dataclass
class ChoiceLine:
    """A choice, drawn as its own row like any other assignable.

    Resolved, it reads as the chosen thing's row; unresolved is information,
    not an error — we inform, we do not police. Its provenance (what offered
    the choice) tells two slots of the same kind apart, and is where the
    picker link a real UI will hang — but a renderer does not show it.
    """

    kind_label: str
    chosen: str | None
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def is_resolved(self):
        return self.chosen is not None


@dataclass(frozen=True)
class EffectLine:
    """Something this model's kit does beyond its own card.

    A pet wargear brings another model to the gang. That is worth reading
    before you buy it as much as after, so the line says what it does and
    whether it has happened yet — ``False`` on a hire preview.
    """

    description: str
    happened: bool
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class ModelCard:
    #: This one model, as its owner named it — "Vesna Krail". Renamed
    #: the moment they paint it, so it stops resembling anything shared.
    name: str
    rating: int
    statline: Statline
    #: The miniature's pk, as a string, when this card draws a *stored*
    #: model — what a renderer builds links from (Equip, Delete). Empty on
    #: a hire preview or a gallery sample, which depict nobody: a card is
    #: the same structure either way, and "" is how it says "nowhere to
    #: link to".
    id: str = ""
    #: The library entry it was hired from — "Escher Gang Queen". Shared
    #: content: many models across many gangs point at this one row.
    #: Blank when there is no profile to name, which a header draws as
    #: nothing rather than as a dash.
    #:
    #: Distinct from ``profile_type``, which is only ever Fighter or
    #: Vehicle, and from ``type_line``, which composes that with the
    #: subtypes. None of the three can be worked out from another.
    profile_name: str = ""
    profile_type: str | None = None
    subtypes: list[AssignableLine] = field(default_factory=list)
    weapons: list[WeaponLine] = field(default_factory=list)
    skills: list[AssignableLine] = field(default_factory=list)
    #: Named special rules — "Automated Repair Systems". The book prints
    #: them apart from skills, so the card keeps them apart too.
    rules: list[AssignableLine] = field(default_factory=list)
    #: Wyrd powers the model knows. Not skills — but placed and picked
    #: through the same sections; drawn as their own row.
    powers: list[AssignableLine] = field(default_factory=list)
    equipment: list[AssignableLine] = field(default_factory=list)
    #: Collections this model can browse — equipment lists, trading posts.
    #: Access to buy from, not things owned; drawn apart from equipment.
    collections: list[AssignableLine] = field(default_factory=list)
    choices: list[ChoiceLine] = field(default_factory=list)
    effects: list[EffectLine] = field(default_factory=list)
    owned_by: str | None = None
    xp: int = 0
    xp_target: int | None = None

    @property
    def type_line(self):
        """``Fighter (Ganger, Mounted, Specialist)``.

        Sorted, because subtypes arrive in whatever order their assignments
        and modifiers happen to load, and a card should not reshuffle itself.
        """
        if self.profile_type is None:
            return "—"
        if not self.subtypes:
            return self.profile_type
        joined = ", ".join(sorted(line.name for line in self.subtypes))
        return f"{self.profile_type} ({joined})"

    @property
    def xp_display(self):
        """``13/19``, or ``13/–`` until ranks tell us the target."""
        return f"{self.xp}/{self.xp_target if self.xp_target is not None else '–'}"


@dataclass
class StashLine:
    """One thing in the gang's stash, and what it is pinned at."""

    name: str
    rating: int
    #: What kind of thing this is — "wargear", "weapon" — so a renderer
    #: can group the stash by the question people actually ask of it.
    #: Lower case, from the model's verbose_name, written to appear
    #: mid-sentence: a renderer using it as a heading capitalises it.
    kind: str = ""
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class GangSheet:
    """The whole gang, derived — never assembled by hand.

    Everything here comes from ``GangCard`` and ``ComputedGang``
    (design/gang-sheet.md): the gang's own rows, its choice slots, its
    counters, the stash's contents, and every member's card. Tests that care
    what the gang *is* assert on those structures; this is what a
    renderer draws.
    """

    name: str
    gang_type: str
    rating: int
    credits: int
    wealth: int
    #: The colour the owner picked, drawn as a mark wherever the gang is
    #: named. A palette name the theme resolves, or empty for no colour.
    colour: str = ""
    #: The gang's own rows — its founding, the house list, its rules.
    rows: list[AssignableLine] = field(default_factory=list)
    #: Gang-level choices — a Venator's ranked skill trees.
    choices: list[ChoiceLine] = field(default_factory=list)
    #: Counters the gang keeps, with their standing values.
    counters: list = field(default_factory=list)
    stash: list[StashLine] = field(default_factory=list)
    stash_rating: int = 0
    #: Remarks worth drawing — the same tree answering two slots. Loud
    #: or quiet per the note's level; never a gate.
    notes: list = field(default_factory=list)
    models: list[ModelCard] = field(default_factory=list)


def apply_changes(stat, raw, changes):
    """Fold stat changes onto a printed value, using the stat's own rules.

    Sets land first, then shifts, which sum. Values that are not plain
    numbers — ``S`` for the wielder's Strength, ``E`` for engaged-only
    range — are immune: there is nothing sensible to add to them.
    """
    if not changes:
        return raw, []

    sources = [
        Provenance(source=change.source, source_kind=change.source_kind, computed=True)
        for change in changes
    ]
    for change in changes:
        if change.mode == "set":
            raw = str(change.amount)

    shift = 0
    for change in changes:
        if change.mode == "improve":
            shift -= change.amount if stat.is_inverted else -change.amount
        elif change.mode == "worsen":
            shift += change.amount if stat.is_inverted else -change.amount

    if shift:
        number = stat._as_int(str(raw).rstrip('"+').lstrip("+"))
        if number is None:
            return raw, sources  # not a number — leave it, but say it was touched
        raw = str(number + shift)
    return raw, sources


def build_statline(owner, changes_for=None):
    """The characteristics of a fighter profile or a weapon profile.

    Values are formatted by each stat's own rules — 4 becomes 4" for a
    distance, 3 becomes 3+ for a roll target — and anything that isn't a
    plain number passes through, which is what lets a weapon's range read
    ``E`` or ``T`` and its Strength read ``S+3``.
    """
    statline = getattr(owner, "statline", None) if owner is not None else None
    if statline is None:
        return Statline()

    cells = []
    for stat_value in statline.ordered_stats():
        type_stat = stat_value.statline_type_stat
        stat = type_stat.stat
        changes = changes_for(stat.field_name) if changes_for else []
        raw, sources = apply_changes(stat, stat_value.value, changes)
        cells.append(
            StatCell(
                short_name=type_stat.short_name,
                full_name=type_stat.full_name,
                value=stat.format_value(raw),
                highlighted=type_stat.is_highlighted,
                first_of_group=type_stat.is_first_of_group,
                modified_by=sources,
            )
        )
    return Statline(cells=cells)


def _computed_provenance(contribution):
    return Provenance(
        source=contribution.source,
        source_kind=contribution.source_kind,
        computed=True,
    )


def build_model_card(miniature, card=None, computed=None, assignment_set=None):
    """Everything needed to draw one model's card.

    Pass ``computed`` (from ``n26.effects.compute``) to fold in what
    modifiers say — granted subtypes and skills, added weapon traits,
    shifted characteristics, forbidden combinations. Without it the card
    shows only what is literally assigned. Pass ``assignment_set`` to show
    one named selection instead of everything the model owns.
    """
    if card is None:
        card = build_card(miniature, with_statlines=True, assignment_set=assignment_set)

    return card_to_model_card(
        card,
        computed=computed,
        name=miniature.name,
        id=str(miniature.pk),
        owned_by=(miniature.owned_by.name if miniature.owned_by else None),
        xp=miniature.xp,
        xp_target=miniature.xp_target,
    )


def card_to_model_card(
    card, computed=None, *, name, id="", owned_by=None, xp=0, xp_target=None
):
    """Turn a card into the structure a renderer draws.

    Everything about *who* the card is for arrives as arguments, so this
    works the same whether the card came from a player's assignments or
    from a profile's default equipment in a hire preview.

    ``xp`` is what to show when the card holds no XP counter; a card that
    holds one shows its value instead, so the cell moves with every tally.
    """
    primary = None
    subtypes, skills, equipment, weapons, collections = [], [], [], [], []
    powers, rules = [], []
    counted_xp = None

    # A node that answers a choice is drawn as that choice's row, not as a
    # loose piece of equipment as well.
    answers = (
        {
            slot.resolved_with.key
            for slot in computed.choices
            if slot.resolved_with is not None
        }
        if computed
        else set()
    )

    # A line's cause is almost always another line on the same card — the
    # membership, the anchor subtype, the weapon a profile hangs off — so
    # its name is resolved from what is already in memory, never by a
    # query. A cause off the card degrades to the reason alone.
    nodes_by_key = {node.key: node for node in card.all_nodes()}

    def provenance_of(node):
        cause = nodes_by_key.get(node.caused_by_key)
        return Provenance(
            source=cause.name if cause else None,
            source_kind=kind_of(cause.assignable) if cause else None,
            reason=node.reason,
        )

    def trait_lines(child, weapon_state):
        if weapon_state is None:
            return [AssignableLine(name=name) for name in child.assignable.trait_names]
        added = {c.name: c for c in weapon_state.added_traits}
        return [
            AssignableLine(
                name=name,
                provenance=(
                    _computed_provenance(added[name]) if name in added else Provenance()
                ),
            )
            for name in weapon_state.trait_names
        ]

    def weapon_line(node, children):
        profiles = []
        # A weapon's children are its profiles and, now, its accessories.
        profile_nodes = [child for child in children if child.is_weapon_profile]
        for child in profile_nodes:
            weapon_state = computed.weapon(child) if computed else None
            profiles.append(
                WeaponProfileLine(
                    # The profile's *own* name, blank for the line that
                    # is the weapon. Not ``str(assignable)``: that adds
                    # the weapon in brackets, which is right where a
                    # profile stands alone and wrong on its own weapon's
                    # card. What to do with a blank is the renderer's.
                    name=child.assignable.name,
                    rating=child.rating,
                    statline=build_statline(
                        child.assignable,
                        changes_for=_weapon_changes(weapon_state),
                    ),
                    traits=trait_lines(child, weapon_state),
                    provenance=provenance_of(child),
                )
            )
        return WeaponLine(
            name=node.name,
            # A stored weapon carries its assignment; a preview's exists on
            # no ledger and keys nothing, which "" is how a line says.
            id=str(node.assignment.pk) if node.assignment is not None else "",
            slots=node.assignable.slots,
            base_rating=node.rating,
            profiles=profiles,
            accessories=[
                AssignableLine(name=child.name, provenance=provenance_of(child))
                for child in node.children
                if not child.is_weapon_profile
            ],
            provenance=provenance_of(node),
        )

    for node in card.roots:
        if node.key in answers:
            # An answer is drawn as its choice's row, not as a loose
            # piece — except that an answered *subtype* is still a
            # subtype: the type line states facts, and rules match on
            # it (a chosen Psyrender is a Psyrender).
            if isinstance(node.assignable, Subtype):
                subtypes.append(
                    AssignableLine(name=node.name, provenance=provenance_of(node))
                )
            continue
        if node.broadcast:
            # The gang's, not this model's. Its modifiers have already
            # reached this card and name it as their source; the row
            # itself belongs on the gang's sheet, not the fighter's.
            continue
        thing = node.assignable
        if isinstance(thing, Hidden):
            # No row of its own — that is its whole kind. Its effects have
            # already landed (a shifted stat cell names it), so skipping
            # the row hides nothing the player needs.
            continue
        if isinstance(thing, Subtype):
            subtypes.append(
                AssignableLine(name=thing.name, provenance=provenance_of(node))
            )
        elif isinstance(thing, Skill):
            skills.append(
                AssignableLine(name=thing.name, provenance=provenance_of(node))
            )
        elif isinstance(thing, Rule):
            rules.append(
                AssignableLine(name=str(thing), provenance=provenance_of(node))
            )
        elif isinstance(thing, Power):
            powers.append(
                AssignableLine(name=str(thing), provenance=provenance_of(node))
            )
        elif isinstance(thing, Weapon):
            weapons.append(weapon_line(node, node.children))
        elif isinstance(thing, WeaponProfile):
            # A profile assigned straight to the model rather than to a weapon.
            weapons.append(weapon_line(node, [node]))
        elif isinstance(thing, Collection):
            collections.append(
                AssignableLine(name=node.name, provenance=provenance_of(node))
            )
        elif isinstance(thing, Counter):
            # A counter is a running number, not a possession, so it is
            # never drawn as a piece of kit. XP has a cell of its own on
            # the card and fills it from the counter's value — the value a
            # hire opens at its printed Starting XP and every tally moves.
            if thing.name.casefold() == XP_COUNTER.casefold():
                counted_xp = _counter_value(node)
        elif node.is_profile:
            # A Legacy profile rides the card but is not drawn from: it is
            # not equipment either, so it falls off here until Legacy gets
            # its own line.
            if node.is_primary_profile:
                primary = thing
        else:
            equipment.append(
                AssignableLine(name=node.name, provenance=provenance_of(node))
            )

    if computed:
        for contribution in computed.subtypes:
            if contribution.name not in {line.name for line in subtypes}:
                subtypes.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )
        for contribution in computed.skills:
            if contribution.name not in {line.name for line in skills}:
                skills.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )
        for contribution in computed.rules:
            if contribution.name not in {line.name for line in rules}:
                rules.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )
        for contribution in computed.collections:
            if contribution.name not in {line.name for line in collections}:
                collections.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )

    return ModelCard(
        name=name,
        id=id,
        rating=card.full_rating,
        # ``str`` rather than ``.name``: every other line on a card
        # reads a thing this way, so an annotation shows here as it
        # would anywhere else. Never the qualifier — that is authoring's.
        profile_name=(str(primary) if primary else ""),
        profile_type=(primary.profile_type.name if primary else None),
        subtypes=sorted(subtypes, key=lambda line: line.name),
        statline=(
            build_statline(primary, changes_for=computed.changes_for)
            if primary and computed
            else build_statline(primary)
            if primary
            else Statline()
        ),
        weapons=sorted(weapons, key=lambda w: w.name),
        skills=sorted(skills, key=lambda line: line.name),
        rules=sorted(rules, key=lambda line: line.name),
        powers=sorted(powers, key=lambda line: line.name),
        equipment=sorted(equipment, key=lambda line: line.name),
        collections=sorted(collections, key=lambda line: line.name),
        choices=(
            [
                ChoiceLine(
                    kind_label=slot.kind_label,
                    chosen=slot.chosen_name,
                    provenance=Provenance(
                        source=slot.source,
                        source_kind=slot.source_kind,
                        computed=True,
                    ),
                )
                for slot in computed.choices
            ]
            if computed
            else []
        ),
        effects=(
            [
                EffectLine(
                    description=effect.description,
                    happened=effect.happened,
                    provenance=Provenance(
                        source=effect.source, source_kind=effect.source_kind
                    ),
                )
                for effect in computed.stored_effects
            ]
            if computed
            else []
        ),
        owned_by=owned_by,
        xp=xp if counted_xp is None else counted_xp,
        xp_target=xp_target,
    )


def _counter_value(node):
    """What a counter node stands at. Zero on a card built from library
    alone: a preview has no assignment to hold a value."""
    held = getattr(node.assignment, "counter_value", None) if node.assignment else None
    return held.value if held else 0


def _weapon_changes(weapon_state):
    """A ``changes_for`` callback for one weapon profile's statline."""
    if weapon_state is None:
        return None

    def changes_for(field_name):
        return [c for c in weapon_state.stat_changes if c.stat.field_name == field_name]

    return changes_for


def _provenance_within(card):
    """A ``provenance_of`` resolving causes among one card's own nodes."""
    nodes_by_key = {node.key: node for node in card.all_nodes()}

    def provenance_of(node):
        cause = nodes_by_key.get(node.caused_by_key)
        return Provenance(
            source=cause.name if cause else None,
            source_kind=kind_of(cause.assignable) if cause else None,
            reason=node.reason,
        )

    return provenance_of


def _gang_rows(gang_card, gang_computed):
    """The gang's own rows as lines, same skipping rules as a model card:
    a Hidden draws nothing, an answer is drawn as its choice's row, and
    counters have their own readings."""
    from n26.library.models import Counter

    answers = (
        {
            slot.resolved_with.key
            for slot in gang_computed.choices
            if slot.resolved_with is not None
        }
        if gang_computed
        else set()
    )
    provenance_of = _provenance_within(gang_card)
    rows = []
    for node in gang_card.roots:
        if node.key in answers:
            continue
        if isinstance(node.assignable, (Hidden, Counter)):
            continue
        rows.append(AssignableLine(name=node.name, provenance=provenance_of(node)))
    return rows


def render_gang(gang, with_effects=True):
    """A whole gang sheet. A fixed number of queries, whatever its size."""
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang, counter_readings
    from n26.core.models import Miniature

    models = list(
        Miniature.objects.filter(
            membership__gang=gang,
            membership__archived=False,
            # Ownership is derived by walking membership -> what caused it -> the
            # model that carried the purchase. Joined here so a roster of pets
            # costs no more queries than a roster without.
        ).select_related("membership__caused_by__miniature_root")
    )
    gang_card = build_gang_card(gang)
    cards = gang_card.members

    computed = {}
    gang_computed = None
    if with_effects:
        # One index for the whole gang, not one per model. The gang's own
        # nodes are listed too — they also ride member cards as broadcast,
        # and the index's seen-set makes the overlap free.
        assignables = [
            node.assignable for card in cards.values() for node in card.all_nodes()
        ] + [node.assignable for node in gang_card.all_nodes()]
        index = build_modifier_index(assignables)
        computed = {model_id: compute(card, index) for model_id, card in cards.items()}
        gang_computed = compute_gang(gang_card, index)

    stash_provenance = _provenance_within(gang_card)
    return GangSheet(
        name=gang.name,
        gang_type=gang.gang_type.name,
        rating=gang.rating,
        credits=gang.credits,
        wealth=gang.wealth,
        colour=gang.colour,
        rows=_gang_rows(gang_card, gang_computed),
        choices=(
            [
                ChoiceLine(
                    kind_label=slot.kind_label,
                    chosen=slot.chosen_name,
                    provenance=Provenance(
                        source=slot.source,
                        source_kind=slot.source_kind,
                        computed=True,
                    ),
                )
                for slot in gang_computed.choices
            ]
            if gang_computed
            else []
        ),
        counters=(
            gang_computed.counters if gang_computed else counter_readings(gang_card)
        ),
        stash=[
            StashLine(
                name=node.name,
                rating=node.rating_with_extras,
                kind=kind_of(node.assignable),
                provenance=stash_provenance(node),
            )
            for node in gang_card.stash_roots
            # No row of its own is the kind's whole contract — a chosen
            # option's Hidden carrier rides the stash invisibly.
            if not isinstance(node.assignable, Hidden)
        ],
        stash_rating=gang_card.stash_rating,
        notes=gang_computed.notes if gang_computed else [],
        models=[
            build_model_card(
                model, card=cards.get(model.pk), computed=computed.get(model.pk)
            )
            for model in models
        ],
    )


# --- The ledger ----------------------------------------------------------


@dataclass
class EventLine:
    """One thing that happened, from the append-only log."""

    kind: str
    actor: str
    credits: int
    trade_points: int
    rating: int
    note: str = ""


@dataclass
class LedgerLine:
    """One acquisition: what it was, what it cost, and what happened to it."""

    what: str
    where: str
    reason: str
    list_price: int
    discount: int
    paid: int
    rating: int
    removed: bool = False
    events: list[EventLine] = field(default_factory=list)

    @property
    def counts_towards_rating(self):
        """A removed thing keeps its entry but stops being counted."""
        return not self.removed


@dataclass
class LedgerView:
    gang: str
    starting_credits: int
    lines: list[LedgerLine] = field(default_factory=list)

    @property
    def total_spent(self):
        return sum(line.paid for line in self.lines)

    @property
    def total_rating(self):
        return sum(line.rating for line in self.lines if line.counts_towards_rating)

    @property
    def credits_remaining(self):
        return self.starting_credits - self.total_spent


def _where(assignment):
    """A short description of what an assignment is attached to."""
    if assignment.parent_id:
        return f"on {assignment.parent.assignable}"
    if assignment.miniature_id:
        return f"on {assignment.miniature.name}"
    if assignment.stash_id:
        return "in the stash"
    if assignment.gang_id:
        return "in the gang"
    return "—"


def build_ledger(gang):
    """The gang's whole ledger — entries and their events — in a fixed number
    of queries, including things that have since been removed."""
    from n26.core.models import LedgerEntry
    from n26.core.models.assignment import ASSIGNABLE_FIELDS

    entries = (
        LedgerEntry.objects.filter(assignment__gang_root=gang)
        .select_related(
            "assignment",
            "assignment__miniature",
            "assignment__parent",
            *(f"assignment__{name}" for name in ASSIGNABLE_FIELDS),
            *(f"assignment__parent__{name}" for name in ASSIGNABLE_FIELDS),
        )
        .prefetch_related("assignment__ledger_events__actor")
        .order_by("created")
    )

    lines = []
    for entry in entries:
        assignment = entry.assignment
        lines.append(
            LedgerLine(
                what=str(assignment.assignable),
                where=_where(assignment),
                reason=entry.get_reason_display(),
                list_price=entry.list_price,
                discount=entry.discount,
                paid=entry.paid,
                rating=entry.rating_contribution,
                removed=assignment.archived,
                events=[
                    EventLine(
                        kind=event.get_kind_display(),
                        actor=event.actor.username if event.actor else "—",
                        credits=event.credits_delta,
                        trade_points=event.trade_points_delta,
                        rating=event.rating_delta,
                        note=event.note,
                    )
                    for event in assignment.ledger_events.all()
                ],
            )
        )
    return LedgerView(
        gang=gang.name, starting_credits=gang.starting_credits, lines=lines
    )
