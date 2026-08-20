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
from n26.core.effects import choice_notes, kind_of, limit_notes
from n26.library.models import (
    EMPTY_VALUE,
    Counter,
    Hidden,
    Pickable,
    Rule,
    Slot,
    Subtype,
    Weapon,
    WeaponProfile,
)
from n26.library.standard_content import XP_COUNTER

#: The kinds that never draw a line of their own. A hidden carrier by
#: definition; a slot because its line *is* its choice row; a pick
#: because it appears as that row's answer. Their effects still show,
#: named in whatever they changed.
DRAWS_NO_LINE = (Hidden, Slot, Pickable)

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
    """One assignable drawn on a card: its name, and where it came from.

    ``rating`` is what the line contributed to the model's rating, and
    zero is drawn as nothing — right for skills, traits and everything
    granted, where there is no figure to state, and for gear it means
    only lines that moved the rating carry a number.
    """

    name: str
    provenance: Provenance = field(default_factory=Provenance)
    rating: int = 0


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
class EditableStatCell:
    """One characteristic as a box an author types in.

    The reading half of this is ``StatCell``, and the two carry the same
    display facts on purpose: an editor that placed its dividers or its
    tint differently from the card would be showing a different statline
    from the one being edited.

    ``value`` is the stored string, which is already canonical — a
    Movement of four is held as ``4"`` — so what the author sees back is
    what a card prints. ``name`` is the input's name in the form that
    submits it, and ``error`` is the refusal to show against this box,
    empty when there is none.
    """

    short_name: str
    full_name: str
    name: str
    value: str = ""
    placeholder: str = ""
    highlighted: bool = False
    first_of_group: bool = False
    error: str = ""


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
        """What rides on the weapon: its paid profiles and its accessories.

        Both go where the weapon goes — selling it sells them — so both
        belong in what the weapon is worth. A screen that counted only
        the profiles would leave a sight's price attributed to the
        fighter with no line of theirs to account for it.
        """
        return sum(profile.rating for profile in self.profiles) + sum(
            accessory.rating for accessory in self.accessories
        )

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
    def own_stats(self):
        """The characteristics the weapon's own row carries, if any.

        Having an unnamed profile and having stats to print on the
        weapon's line are two different facts, and a combi-weapon is
        where they part company: it carries an unnamed profile that is
        the weapon's identity — "Combi-weapon (laspistol/meltagun)" —
        and does its shooting entirely through the named profiles
        beneath, so the weapon's own row has nothing to put in the stat
        columns.

        A renderer asks this rather than asking whether an own line
        exists, because what it needs to know is whether the name shares
        the row with anything: alone on it, the name takes the whole
        width instead of being squeezed into the first column while the
        rest of the row stands empty.
        """
        own = self.own_line
        return own.statline.cells if own is not None else []

    @property
    def named_profiles(self):
        """The profiles that get a row beneath the weapon — the named ones.

        With ``own_line`` this is the whole layout rule, kept here so the
        card on screen, the card on paper and the card as text derive it
        rather than each deciding it. They had drifted once already.
        """
        return [p for p in self.profiles if p.name]


#: What a gang's own choice slots are addressed under, where a model's are
#: addressed under the model's id. A ULID is never this word, so the two
#: kinds of host cannot collide in a slot key.
GANG_SLOT_HOST = "gang"


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
    #: What addresses this one slot: the card it is drawn on, the assignment
    #: carrying the offer, and the offer itself. All three are needed — one
    #: carrier may offer two slots of the same kind, and a gang-held carrier
    #: puts a slot on every card it reaches. Empty when the card draws no
    #: stored assignments: a preview depicts nobody, so it has no slot to
    #: choose for.
    key: str = ""
    #: Where a Choose control leads. Filled in by whoever knows the URL
    #: space, because this module knows what a slot *is* and not where a
    #: picker lives. Empty draws the prompt as plain text, which is what a
    #: print sheet and a gallery sample want.
    href: str = ""

    @property
    def is_resolved(self):
        return self.chosen is not None


@dataclass(frozen=True)
class Choosable:
    """One thing that could be chosen for a choice slot."""

    #: The identity a form submits — the model's label and its primary key,
    #: the same pair the equipment listing keys its Buy buttons on, because
    #: a bare key is ambiguous across the assignable tables.
    key: str
    name: str
    thing: object = None
    #: True for a thing the surface opens on already marked: what a slot
    #: already holds, or — where a list is ticked rather than picked — one
    #: the model already has.
    is_current: bool = False
    #: Remarks about picking this one — "usable by Walkers only". Said,
    #: never enforced; the list is an offer, not a rule.
    detail: str = ""
    #: What grants this, where the rules hand it over rather than an owner
    #: taking it — "Keen-eyed". No assignment is behind such a thing, so a
    #: surface offering things to tick draws it fixed: there is nothing a click
    #: could take away.
    granted_by: str = ""
    #: Why this one cannot be changed, where something other than a grant
    #: fixes it — money standing behind it. Drawn fixed like a granted
    #: line, saying this instead of a giver. A surface must not offer an
    #: act that would be refused: the refusal would arrive as a message
    #: about a change the card then denies.
    fixed_because: str = ""
    #: The other choice on this holder that has already settled on it,
    #: where the slot type says one pickable answers one choice. Marked
    #: and never withheld: the owner may still pick it, and the card says
    #: so afterwards.
    taken_for: str = ""
    #: What this option's own control does, where a choice is settled one
    #: option at a time: ``"choose"`` adds it, ``"remove"`` takes back the
    #: pick behind it, and empty draws no control at all. Empty
    #: throughout on a choice that holds one, where the whole list is
    #: settled in a single go.
    control: str = ""

    @property
    def remark(self):
        """The muted line under the option's name, whatever fills it."""
        said = [self.detail] if self.detail else []
        if self.taken_for:
            said.append(f"already chosen for {self.taken_for}")
        return " · ".join(said)


@dataclass
class ChoosableGroup:
    """One heading in a pick list, and what sits under it."""

    name: str
    options: list[Choosable] = field(default_factory=list)
    #: Which tier this heading sits in — "Primary". Only filled where the
    #: list spans more than one, because a page showing a single tier has
    #: already said which in its own heading, and repeating it over every
    #: group would be the same word down the page.
    caption: str = ""


@dataclass
class ChoiceOffer:
    """A slot and what may be chosen for it — the pick screen, as data.

    One structure whatever the offer names, which is the point: a skill, an
    archetype and an affiliation differ in the rows they list and in
    nothing else, so one page draws all three.

    A choice holding several picks is settled a pick at a time —
    ``takes_several`` — and each option carries its own control saying
    what a click on it does. One that holds a single pick is the older
    shape: the whole list is settled in a single go, and settling it
    again replaces what was chosen.
    """

    label: str
    chosen: str | None = None
    groups: list[ChoosableGroup] = field(default_factory=list)
    #: Whether the picker adds and removes one pick at a time rather than
    #: settling the whole list in a single go.
    takes_several: bool = False

    @property
    def is_empty(self):
        return not any(group.options for group in self.groups)


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
    #: content: many models across many gangs point at this one profile.
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
    #: Open questions filed into the card's own rows, kept apart from
    #: the general run. They are drawn in the Skills and Powers rows,
    #: beside what the model already knows, because those are the rows a
    #: reader looks at to find out what this fighter can do — a founding
    #: pick left in the general run of slots is an obligation filed
    #: under the same heading as their archetype. ``question_row`` says
    #: which questions qualify. A slot already chosen for is not here:
    #: the thing chosen is a skill or a power, and it sits in its row
    #: with the others.
    skill_choices: list[ChoiceLine] = field(default_factory=list)
    power_choices: list[ChoiceLine] = field(default_factory=list)

    #: The rows that draw questions, and the field each row's open ones
    #: land in. A card row is a kind's declaration (``card_row`` on the
    #: library model); *hosting questions* is this structure's, because
    #: a question needs somewhere to grow a Choose control and only the
    #: rows named here have one. ``question_row`` routes against this,
    #: and a guard test holds it to rows that really exist.
    QUESTION_BUCKETS = {"skills": "skill_choices", "powers": "power_choices"}
    #: Where the way into the skills screen leads, or empty when there is
    #: nowhere to send anyone. Filled in by whoever knows the URL space,
    #: like a choice's own href — this module knows what a grid *is* and
    #: not where a browsing screen lives. Empty draws no control, which
    #: is what a print sheet and a hire preview want.
    learn_href: str = ""
    #: The collections this model's grid places a category into, by id.
    #: Standing access, computed rather than assigned: it is what a
    #: screen for selecting is built on, and asking which of these hold
    #: what a model *is* costs one query for a whole roster rather than
    #: one per card.
    placed_in: tuple[str, ...] = ()
    effects: list[EffectLine] = field(default_factory=list)
    #: What the app has to say about this card — a limit the model is
    #: over. ``n26.core.notes`` Notes, drawn loud or quiet by level and
    #: never a gate. Not the player's own notes about the fighter, which
    #: are prose they write and this card does not carry.
    remarks: list = field(default_factory=list)
    owned_by: str | None = None
    xp: int = 0
    xp_target: int | None = None

    @property
    def questions(self):
        """Every question still open on this card, in one run.

        Where a question is drawn is a surface's business: on screen the
        ones filed to a row go in the Skills or Powers row, beside what
        the fighter already knows. A renderer with no rows to fold them
        into — the text card, the printed one — draws the lot, because a
        choice still to be made is worth a line on paper and none of them
        should go missing for want of somewhere to put it.
        """
        return [*self.choices, *self.skill_choices, *self.power_choices]

    @property
    def weapon_columns(self):
        """The stat columns a weapon table draws, as cells to read names off.

        One shape for the whole table: every weapon on a card is drawn to
        the same columns, so a renderer needs a single row of headings and
        a single count to span a nameless row across.

        The first profile that has any characteristics, rather than the
        first profile there is. A combi-weapon's own line carries the
        weapon's identity and no numbers, and asking that one for the
        columns gives a table of headings that is empty while every row
        beneath it still prints its stats.
        """
        for weapon in self.weapons:
            for profile in weapon.profiles:
                if profile.statline.cells:
                    return profile.statline.cells
        return []

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
    #: The assignment's pk, as a string — what a control acting on this
    #: line names. Every stash line has one; the stash holds stored
    #: assignments and nothing computed.
    id: str = ""
    #: An accessory moves onto a weapon rather than a model.
    is_accessory: bool = False
    #: What can happen to this line, each a link to a dialog on the page
    #: that drew it — see ``n26.core.views.owned.link_stash_actions``.
    #: Empty is a name with nothing to click, which is what a print-out
    #: and a reader who does not own the gang want.
    menu: tuple = ()


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
    #: The gang's own rows — its founding, the house list.
    rows: list[AssignableLine] = field(default_factory=list)
    #: The gang's special rules, apart from the other rows for the same
    #: reason a model card keeps its rules apart from its kit: the sheet
    #: prints them under their own term.
    rules: list[AssignableLine] = field(default_factory=list)
    #: Gang-level choices — a Venator's ranked skill trees.
    choices: list[ChoiceLine] = field(default_factory=list)
    #: Counters the gang keeps, with their standing values.
    counters: list = field(default_factory=list)
    stash: list[StashLine] = field(default_factory=list)
    stash_rating: int = 0
    #: A gang founded without a budget never spends against one, so its
    #: credits figure counts nothing. Stated rather than inferred from a
    #: zero, which is also what a gang that has spent everything has.
    credits_unlimited: bool = False
    #: Remarks worth drawing — the same tree chosen for two slots. Loud
    #: or quiet per the note's level; never a gate.
    notes: list = field(default_factory=list)
    models: list[ModelCard] = field(default_factory=list)
    #: The roster reduced to its arithmetic — how many of each profile at
    #: each rank, and what each model is worth. Derived from the same
    #: members the cards are built from, so a sheet's count and its cards
    #: cannot disagree and asking for it costs no query.
    summary: RosterSummary | None = None

    @property
    def questions(self):
        """Every question this sheet draws — the gang's own, one strip of
        them.

        Named to match a card's, so anything that has business with a
        holder's open questions — pointing them at their pickers, counting
        them — asks the two shapes the same way and cannot be told about
        one list and not another.
        """
        return self.choices


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
            number = _none_of_it(stat, raw)
        if number is None:
            return raw, sources  # not a number — leave it, but say it was touched
        raw = str(number + shift)
    return raw, sources


def _none_of_it(stat, raw):
    """Zero, where a dash on this stat means none of the quantity — else None.

    A weapon's Armour Piercing of "-" is no armour piercing, which is
    zero, so a rule that improves it by one gives -1. Counting the dash
    is the whole of what makes such a rule reach the guns it is written
    for: the book prints "-" on exactly the plain weapons a house's
    improvement is worth having on.

    A distance and a roll target are not quantities that can be zero. A
    melee weapon's Long Range and a fighter's absent Save are the thing
    not happening at all, and no shift brings either into existence.
    """
    countable = not (stat.is_inches or stat.is_target or stat.is_modifier)
    if countable and str(raw).strip() in ("", EMPTY_VALUE):
        return 0
    return None


#: What a hand-set cell names as having changed it. The card's tooltip
#: reads "M changed by …", so this is the phrase that finishes that
#: sentence.
SET_BY_THE_OWNER = Provenance(source="the owner")


def build_statline(owner, changes_for=None, stat_overrides=None):
    """The characteristics of a fighter profile or a weapon profile.

    Values are formatted by each stat's own rules — 4 becomes 4" for a
    distance, 3 becomes 3+ for a roll target — and anything that isn't a
    plain number passes through, which is what lets a weapon's range read
    ``E`` or ``T`` and its Strength read ``S+3``.

    The shape comes from the statline *type*, not from the values stored
    against it: a statline holding four of its five stats is a full row
    with one dash in it, and never four cells that slide the numbers
    under the wrong headings. Nothing stops content arriving that way —
    the completeness check lives in ``clean()``, which importers and the
    authoring verbs do not call.

    ``stat_overrides`` are the values one model's owner set by hand,
    keyed by the cell each stands in. Each replaces the printed value as
    the base a cell is drawn from, so a rule that improves the
    characteristic improves what was set rather than what the entry
    prints, and the cell says the owner is among the reasons it differs.
    """
    statline = getattr(owner, "statline", None) if owner is not None else None
    stat_overrides = stat_overrides or {}
    if statline is None and not stat_overrides:
        return Statline()

    stored = (
        {value.statline_type_stat_id: value.value for value in statline.stats.all()}
        if statline is not None
        else {}
    )
    cells = []
    for type_stat in _shape_of(owner, statline):
        stat = type_stat.stat
        changes = changes_for(stat.field_name) if changes_for else []
        hand_set = stat_overrides.get(type_stat.pk, "")
        raw, sources = apply_changes(
            stat, hand_set or stored.get(type_stat.pk, ""), changes
        )
        if hand_set:
            sources = [SET_BY_THE_OWNER, *sources]
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


def _shape_of(owner, statline):
    """The stats a statline is supposed to carry, in display order.

    A weapon may have no statline type at all, in which case there is no
    shape to hold the values to and the stored ones are all there is —
    and where there are none of those either, there is no row to draw.
    """
    statline_type = owner.statline_type
    if statline_type is None:
        if statline is None:
            return []
        return [value.statline_type_stat for value in statline.ordered_stats()]
    return list(statline_type.stats.all())


def _computed_provenance(contribution):
    return Provenance(
        source=contribution.source,
        source_kind=contribution.source_kind,
        computed=True,
    )


def _slot_key(slot, host):
    """What addresses one computed slot, or empty when nothing does.

    A slot hangs off an assignment, so a card built from a profile's
    default equipment has no row to choose against — the offer is real,
    the address is not, and an empty key is how a line says there is
    nowhere to send a reader.
    """
    anchor = getattr(slot.anchor, "assignment", None)
    if not host or anchor is None or slot.identity is None:
        return ""
    return f"{host}:{anchor.pk}:{slot.identity.pk}"


def _choice_line(slot, host):
    return ChoiceLine(
        kind_label=slot.kind_label,
        chosen=slot.chosen_name,
        key=_slot_key(slot, host),
        provenance=Provenance(
            source=slot.source,
            source_kind=slot.source_kind,
            computed=True,
        ),
    )


def question_row(slot):
    """Which of the card's named rows draws this question — or None for
    a row of its own.

    The label decides, and the rule is what an author would guess:
    a question labelled "Skills" or "Powers" sits in that row, beside
    what the fighter already has; a question labelled anything else —
    "Bonecrusher Wyrd Powers", "Favoured archetype" — is its own row,
    headed by exactly what was written. Unlabelled, the kind stands in:
    its declared ``card_row``, so a skill question sits with the skills
    and a power question with the powers with nothing said here.

    Only the rows in ``ModelCard.QUESTION_BUCKETS`` qualify — a row has
    to draw questions to take one, and a subtype's row is a type line
    with nowhere to put a button, so a subtype question stays a row of
    its own however its kind files its lines.

    Casefolded, because the row headings are prose and a label is typed
    by hand — "powers" and "Powers" are the same intent.
    """
    if slot.offer is None:
        return None
    if slot.offer.label:
        name = slot.offer.label.casefold()
        return name if name in ModelCard.QUESTION_BUCKETS else None
    row = getattr(slot.offer.of_kind.model_class(), "card_row", None)
    return row if row in ModelCard.QUESTION_BUCKETS else None


def choice_lines(computed, host=""):
    """A computed card's choice slots as lines a renderer draws.

    ``host`` is what the slots are addressed under — a model's id, or
    ``GANG_SLOT_HOST`` for the gang's own. Passed rather than derived
    because the same slot may sit on a member's card and on the gang's,
    and which one a reader clicked decides whose choice it is.
    """
    if not computed:
        return []
    return [_choice_line(slot, host) for slot in computed.choices]


def build_choice_offer(slot, computed):
    """What may be chosen for one slot, in the one shape a picker draws.

    The offer decides the list; this only flattens it. A slot narrowed to
    a tier draws the browsable view the fighter already buys from, so
    its categories become the headings and the fighter's own placements
    have already shaped it. An unnarrowed slot has no collection and
    draws the whole kind, which is one heading-less group. Neither
    branch knows what kind of thing is being picked — that is what lets a
    skill, an archetype and an affiliation share a screen.

    Where the slot type takes one pickable once, the ones this holder
    has already spent elsewhere are marked. Marked, not withheld: the
    list informs, the click still works, and the card says so
    afterwards.

    A choice holding more than one pick is settled a pick at a time:
    everything it holds is drawn chosen and carries the control that
    takes that one back, and everything else carries the control that
    adds it — until the choice is full, when the rest stop being offered.
    Swapping the earliest for whatever was clicked is the behaviour of a
    choice that holds exactly one, and only of that. A choice that holds
    none offers nothing at all.
    """
    from n26.core.browse import CollectionView, Listed, offered_by

    if slot.max_picks == 0:
        # A choice that holds nothing asks nothing: there is no pick a
        # click here could write, so there is nothing to draw.
        return ChoiceOffer(label=slot.kind_label, chosen=slot.chosen_name)

    offered = offered_by(slot, computed)
    current = slot.resolved_with.assignable if slot.resolved_with is not None else None

    if isinstance(offered, CollectionView):
        return offer_from_view(
            offered, label=slot.kind_label, chosen=slot.chosen_name, current=current
        )

    several = slot.max_picks > 1
    held = {option_key(pick.assignable) for pick in slot.picks}
    taken = _taken_elsewhere(slot, computed)
    options = []
    for item in offered or ():
        thing = item.thing if isinstance(item, Listed) else item
        name = item.name if isinstance(item, Listed) else None
        key = option_key(thing)
        if several and key not in held and slot.is_full:
            # Full: the way to something else is to take one back, not to
            # push one out unasked.
            continue
        options.append(
            _choosable(
                thing,
                current,
                taken=taken,
                name=name,
                held=held,
                control=("remove" if key in held else "choose") if several else "",
            )
        )

    if not several and slot.slot is not None and slot.min_picks == 0 and options:
        # A choice expecting no picks may be settled on nothing: the
        # None row resets it, and reads as current while nothing is
        # picked. Only where one pick is held in a single go — a choice
        # worked at a pick at a time already resets through each pick's
        # own Remove.
        options.append(Choosable(key=NONE_KEY, name="None", is_current=not slot.picks))

    groups = [ChoosableGroup(name="", options=options)] if options else []
    return ChoiceOffer(
        label=slot.kind_label,
        chosen=slot.chosen_name,
        groups=groups,
        takes_several=several,
    )


def offer_from_view(view, *, label, chosen=None, current=None, held=(), granted=None):
    """A browsed collection, flattened into the shape a picker draws.

    The half of a pick screen that has nothing to do with slots: a
    ``CollectionView`` goes in and groups of options come out, so
    choosing within one tier and browsing everything a fighter may select
    are two callers of one structure rather than two screens that look
    alike.

    ``current`` marks the thing already chosen, where something is; a
    listing nobody asked a question about has none.

    ``held`` names by key what the model already has, so a surface that
    ticks rather than picks opens on the truth rather than on nothing.
    ``granted`` maps a key to what grants it, for the ones no stored
    assignment is behind: they are held too, and a surface must not offer
    to take away something that would come straight back.
    """
    # Which tier a set sits in is worth saying only where the list spans
    # several: a question narrowed to one has named it in the page's own
    # heading, and captioning every group would print that word down the
    # whole page.
    tiered = len(view.sections) > 1
    groups = [
        # The category is the useful heading — the skill set, the power
        # family. The section names the whole list already, and stands in
        # where the content declared no category.
        ChoosableGroup(
            name=category.name or section.name,
            caption=section.name if tiered and category.name else "",
            options=[
                _choosable(line.thing, current, line.notes, held, granted)
                for line in category.lines
            ],
        )
        for section in view.sections
        for category in section.categories
    ]
    return ChoiceOffer(
        label=label,
        chosen=chosen,
        groups=[group for group in groups if group.options],
    )


def _taken_elsewhere(slot, computed):
    """What this holder has already picked for another choice of the same
    slot type, keyed the way the picker keys its options.

    Only where the slot type takes one pickable once: where it allows
    repeats, picking the same thing twice is the content working as
    written and there is nothing to say. The choice being made is left
    out of its own answer — what is already picked *here* is marked as
    the current pick, which is a different fact.
    """
    if slot.slot is None or slot.slot.slot_type.allows_repeats:
        return {}
    taken = {}
    for other in computed.choices:
        if other is slot or other.slot is None:
            continue
        if other.slot.slot_type_id != slot.slot.slot_type_id:
            continue
        for pick in other.picks:
            taken.setdefault(option_key(pick.assignable), other.source)
    return taken


#: The key the None row submits — the reset on a choice expecting no
#: picks. No stored thing is behind it, so the key is its own word
#: rather than a ``label:pk`` pair, which no real option can collide
#: with.
NONE_KEY = "none"


def option_key(thing):
    """How a picker names one option in a form.

    The model's label and its primary key, the same pair the equipment
    listing keys its Buy buttons on: a bare key is ambiguous across the
    assignable tables. Public because whoever reads a click back has to
    key what is held the same way the page keyed what it drew.
    """
    return f"{thing._meta.label_lower}:{thing.pk}"


def _choosable(
    thing, current, notes=(), held=(), granted=None, taken=None, name=None, control=""
):
    key = option_key(thing)
    granted_by = (granted or {}).get(key, "")
    return Choosable(
        key=key,
        # The wording a list gives a pickable, where it gives it one. The
        # thing's own name everywhere else, and on every other surface.
        name=name or str(thing),
        thing=thing,
        is_current=(current is not None and thing == current)
        or key in held
        or bool(granted_by),
        detail="; ".join(note.text for note in notes),
        granted_by=granted_by,
        taken_for=(taken or {}).get(key, ""),
        control=control,
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
        # Off the card, never off the model: what an owner set is loaded
        # by the build (``n26.core.card.set_by_hand``), because drawing
        # a card may not query.
        stat_overrides=card.stat_overrides,
    )


def card_to_model_card(
    card,
    computed=None,
    *,
    name,
    id="",
    owned_by=None,
    xp=0,
    xp_target=None,
    stat_overrides=None,
):
    """Turn a card into the structure a renderer draws.

    Everything about *who* the card is for arrives as arguments, so this
    works the same whether the card came from a player's assignments or
    from a profile's default equipment in a hire preview.

    ``xp`` is what to show when the card holds no XP counter; a card that
    holds one shows its value instead, so the cell moves with every tally.

    ``stat_overrides`` are the characteristics this model's owner set by
    hand — none on a preview, which depicts nobody and so has nobody's
    settings to honour.
    """
    primary = None
    equipment, weapons = [], []
    # The named line rows, keyed by the vocabulary the kinds declare
    # (``card_row``). One mapping serves the walk over stored assignments and
    # the merge of computed grants below — the two can not disagree
    # about where a kind's lines go.
    line_rows = {
        "subtypes": [],
        "skills": [],
        "powers": [],
        "rules": [],
        "collections": [],
    }
    counted_xp = None

    # A node chosen for a choice is drawn as that choice's row, not as a
    # loose piece of equipment as well. Questions filed to a row are the
    # exception, because what they settle on has a row already: choosing
    # for a skill question puts the skill in the Skills row with the
    # rest, choosing for a power question puts a power in Powers, and the
    # question stops being asked.
    chosen_keys = (
        {
            pick.key
            for slot in computed.choices
            for pick in slot.picks
            if question_row(slot) is None
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
            computed=node.computed,
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
                AssignableLine(
                    name=child.name,
                    provenance=provenance_of(child),
                    rating=child.rating_with_extras,
                )
                for child in node.children
                if not child.is_weapon_profile
            ],
            provenance=provenance_of(node),
        )

    # What the model owns, and then what a modifier handed it. A granted
    # line is drawn like any other — a weapon with its firing lines — and
    # tells itself apart by its provenance, which says it was computed.
    for node in (*card.roots, *card.granted):
        if node.key in chosen_keys:
            # A chosen thing is drawn as its choice's row, not as a loose
            # piece — except that a chosen *subtype* is still a subtype:
            # the type line states facts, and rules match on it (a chosen
            # Psyrender is a Psyrender).
            if isinstance(node.assignable, Subtype):
                line_rows["subtypes"].append(
                    AssignableLine(name=node.name, provenance=provenance_of(node))
                )
            continue
        if node.broadcast:
            # The gang's, not this model's. Its modifiers have already
            # reached this card and name it as their source; the line
            # itself belongs on the gang's sheet, not the fighter's.
            continue
        if node.suppressed:
            # Something has taken this away. The assignment is still in
            # the database and draws nothing: the card is what the fighter
            # has, and this is no longer part of it.
            continue
        thing = node.assignable
        if isinstance(thing, DRAWS_NO_LINE):
            # No row of its own. A hidden carrier's effects have already
            # landed (a shifted stat cell names it); a slot draws its
            # choice row instead; a pick appears as that row's answer, or
            # as nothing at all where no choice stands behind it.
            continue
        if getattr(thing, "card_row", None) is not None:
            # The kind said where its lines go — one declaration, read
            # here and everywhere else that files a line. Every named
            # row prints the same way: the name, the annotation after it.
            line_rows[thing.card_row].append(
                AssignableLine(name=node.name, provenance=provenance_of(node))
            )
        elif isinstance(thing, Weapon):
            weapons.append(weapon_line(node, node.children))
        elif isinstance(thing, WeaponProfile):
            # A profile assigned straight to the model rather than to a weapon.
            weapons.append(weapon_line(node, [node]))
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
                AssignableLine(
                    name=node.name,
                    provenance=provenance_of(node),
                    rating=node.rating,
                )
            )

    if computed:
        # Computed grants join the same rows the stored lines chose —
        # the mapping is the one the kinds declared, so a grant can
        # never land in a different row than a purchase of the same
        # thing. Deduplicated by name: two sources granting one skill
        # leave the fighter knowing it once.
        for row_name, lines in line_rows.items():
            for contribution in getattr(computed, row_name):
                if contribution.name not in {line.name for line in lines}:
                    lines.append(
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
        subtypes=sorted(line_rows["subtypes"], key=lambda line: line.name),
        statline=(
            build_statline(
                primary,
                changes_for=computed.changes_for if computed else None,
                stat_overrides=stat_overrides,
            )
            if primary
            else Statline()
        ),
        weapons=sorted(weapons, key=lambda w: w.name),
        skills=sorted(line_rows["skills"], key=lambda line: line.name),
        rules=sorted(line_rows["rules"], key=lambda line: line.name),
        powers=sorted(line_rows["powers"], key=lambda line: line.name),
        equipment=sorted(equipment, key=lambda line: line.name),
        collections=sorted(line_rows["collections"], key=lambda line: line.name),
        choices=[
            _choice_line(slot, id)
            for slot in (computed.choices if computed else [])
            if question_row(slot) is None
        ],
        # Only the open ones: a settled skill question is a skill, a
        # settled power question a power, and both are already in their
        # rows above.
        skill_choices=[
            _choice_line(slot, id)
            for slot in (computed.choices if computed else [])
            if question_row(slot) == "skills" and not slot.is_resolved
        ],
        power_choices=[
            _choice_line(slot, id)
            for slot in (computed.choices if computed else [])
            if question_row(slot) == "powers" and not slot.is_resolved
        ],
        placed_in=tuple(
            {
                str(placement.section.collection_id)
                for placement in (computed.placements if computed else [])
            }
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
        remarks=(
            [*limit_notes(card, computed), *choice_notes(computed)] if computed else []
        ),
        owned_by=owned_by,
        xp=xp if counted_xp is None else counted_xp,
        xp_target=xp_target,
    )


def _counter_value(node):
    """What a counter node stands at: the stored value — or, on a card
    built from library alone, what the built-in says it opens at, which
    is exactly what the hire will write."""
    held = getattr(node.assignment, "counter_value", None) if node.assignment else None
    if held is not None:
        return held.value
    return node.opens_at


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
            computed=node.computed,
        )

    return provenance_of


def _gang_rows(gang_card, gang_computed):
    """The gang's own rows as lines, same skipping rules as a model card:
    a Hidden draws nothing, a chosen thing is drawn as its choice's row,
    and counters have their own readings. Rules come back as their own list,
    dispatched the way a model card keeps rules apart from kit.

    What a rule grants the gang folds in from ``ComputedGang`` the way a
    model card folds in its contributions — a named rule with the rules,
    a standing list with the rows — told apart by provenance and gone
    when the granter goes. Only those two kinds can land here (the
    modifier models' ``accepts``): the gang's card has no type line, no
    skills row, and holds no weapons.
    """
    from n26.library.models import Counter

    chosen_keys = (
        {pick.key for slot in gang_computed.choices for pick in slot.picks}
        if gang_computed
        else set()
    )
    provenance_of = _provenance_within(gang_card)
    rows = []
    rules = []
    for node in gang_card.roots:
        if node.key in chosen_keys:
            continue
        if node.suppressed:
            # Taken away by a modifier — the assignment stays, the line goes.
            continue
        if isinstance(node.assignable, (*DRAWS_NO_LINE, Counter)):
            continue
        if isinstance(node.assignable, Rule):
            rules.append(AssignableLine(name=node.name, provenance=provenance_of(node)))
            continue
        rows.append(AssignableLine(name=node.name, provenance=provenance_of(node)))
    if gang_computed:
        for contribution in gang_computed.rules:
            if contribution.name not in {line.name for line in rules}:
                rules.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )
        for contribution in gang_computed.collections:
            if contribution.name not in {line.name for line in rows}:
                rows.append(
                    AssignableLine(
                        name=contribution.name,
                        provenance=_computed_provenance(contribution),
                    )
                )
    return rows, sorted(rules, key=lambda line: line.name)


def roster(gang):
    """The gang's models, in the order a printed gang list reads.

    By the profile's home category — Leader, then Champions, and so on
    down the taxonomy's own positions — and by name within a rank.
    Vehicles come after every fighter, whatever their category says: the
    gang list reads crew first, machines at the end. A model somebody's
    purchase brought in (a pet, a deployed platform) sorts directly
    after its owner, whatever its own rank: the book prints the beast
    with its keeper. One query, sorted here, because the owner half of a
    key lives on another model in the same list.
    """
    from n26.core.models import Miniature

    members = list(
        Miniature.objects.filter(
            membership__gang=gang,
            membership__archived=False,
            # Ownership is derived by walking membership -> what caused it -> the
            # model that carried the purchase. Joined here so a roster of pets
            # costs no more queries than a roster without. The profile's home
            # category and Type ride along for the same reason: they are the
            # rank half of the sort key.
        ).select_related(
            "membership__caused_by__miniature_root",
            "membership__profile__category",
            "membership__profile__profile_type",
        )
    )
    return _mustered(members)


def _mustered(members, recategorised=None):
    """Those members in the order the gang list reads.

    ``recategorised`` maps a model's pk to the category a rule re-files
    them under (``ChangesCategory``, folded off their computed card) —
    their rank sorts by it in place of the profile's own. Separate from
    :func:`roster` so a caller that has already computed the cards can
    re-order without re-fetching.
    """
    recategorised = recategorised or {}
    by_pk = {member.pk: member for member in members}

    def rank(member):
        """Where this model's rank sorts. Vehicles after every fighter —
        their Type decides that, not their category's position, which
        numbers them within their own section and would otherwise
        collide with a fighter rank's. Within a Type, the category's
        position alone, one ladder across sections: ranked by the
        section first, a supplementary Hanger-on could only ever sort
        where its whole section sorts. Uncategorised after everything
        placed."""
        profile = member.membership.profile if member.membership else None
        vehicle = profile is not None and profile.profile_type.name == "Vehicle"
        category = recategorised.get(member.pk) or (
            profile.category if profile else None
        )
        if category is None:
            return (vehicle, 1, 0)
        return (vehicle, 0, category.position)

    def key(member):
        owner = member.owned_by
        anchor = by_pk.get(owner.pk, member) if owner is not None else member
        return (
            *rank(anchor),
            anchor.name.casefold(),
            str(anchor.pk),
            # The owner first, then what it brought, then everyone else
            # whose name ties.
            0 if anchor is member else 1,
            member.name.casefold(),
        )

    return sorted(members, key=key)


@dataclass(frozen=True)
class RosterGroup:
    """One (profile, rank) the gang fields, and how many of them."""

    profile: str
    category: str
    count: int


@dataclass(frozen=True)
class RosterLine:
    """One model in the ratings tally: its name and its pinned rating."""

    name: str
    rating: int


@dataclass
class RosterSummary:
    """The roster reduced to its arithmetic — what a reader tallies.

    Two readings of the same list: which profiles at which ranks and how
    many of each, and every model with its pinned rating. Both keep the
    roster's own order — a group sits where its first member does, so a
    pet's row follows its keeper's the way the gang list prints them.
    """

    groups: list[RosterGroup]
    models: list[RosterLine]
    count: int
    rating: int


def summarise_roster(members, recategorised=None):
    """Reduce the list :func:`roster` returns to a :class:`RosterSummary`.

    Takes the members already fetched — their profile and its rank came
    back with them — so this issues no queries of its own. The rating
    total is the sum of the models listed, which is what the tally's
    last row must equal: the gang's own rating figure also counts what
    no single model carries.

    ``recategorised`` is the same map :func:`_mustered` takes: a model's
    pk to the category a rule re-files them under. The tally groups by
    that rank when one is given, so a sheet that has already re-ordered
    the roster does not then count the same model under a different one.
    """
    recategorised = recategorised or {}
    tallies: dict[tuple[str, str], int] = {}
    for member in members:
        profile = member.membership.profile if member.membership else None
        category = recategorised.get(member.pk) or (
            profile.category if profile is not None else None
        )
        home = (
            profile.name if profile is not None else "",
            category.name if category is not None else "",
        )
        tallies[home] = tallies.get(home, 0) + 1
    return RosterSummary(
        groups=[
            RosterGroup(profile=profile, category=category, count=count)
            for (profile, category), count in tallies.items()
        ],
        models=[
            RosterLine(name=member.name, rating=member.rating) for member in members
        ],
        count=len(members),
        rating=sum(member.rating for member in members),
    )


def stash_lines(gang_card):
    """The stash as drawable lines, from a gang card already built.

    Derived from the card rather than fetched, so a page that has one —
    the sheet, a print — pays nothing further for its stash block.
    """
    from n26.library.models import WeaponAccessory

    stash_provenance = _provenance_within(gang_card)
    return [
        StashLine(
            name=node.name,
            rating=node.rating_with_extras,
            kind=kind_of(node.assignable),
            provenance=stash_provenance(node),
            id=str(node.assignment.pk) if node.assignment is not None else "",
            is_accessory=isinstance(node.assignable, WeaponAccessory),
        )
        for node in gang_card.stash_roots
        # No row of its own is the kind's whole contract — a chosen
        # option's Hidden carrier rides the stash invisibly.
        if not isinstance(node.assignable, DRAWS_NO_LINE)
    ]


def render_gang(gang, with_effects=True):
    """A whole gang sheet. A fixed number of queries, whatever its size."""
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang, counter_readings

    models = roster(gang)
    gang_card = build_gang_card(gang)
    cards = gang_card.members

    computed = {}
    gang_computed = None
    recategorised = {}
    if with_effects:
        # One index for the whole gang, not one per model. The gang's own
        # nodes are listed too — they also ride member cards as broadcast,
        # and the index's seen-set makes the overlap free.
        assignables = [
            node.assignable for card in cards.values() for node in card.all_nodes()
        ] + [node.assignable for node in gang_card.all_nodes()]
        index = build_modifier_index(assignables)
        # The gang first: what it holds by grant is dealt onto every
        # member's card, and it is settled — after the gang's own
        # removals — before any member reads it.
        gang_computed = compute_gang(gang_card, index)
        computed = {model_id: compute(card, index) for model_id, card in cards.items()}
        # A rule that re-files a model (ChangesCategory) is a computed
        # fact, so the order is settled here — after the fold, from data
        # already in hand — rather than by roster's own query.
        recategorised = {
            pk: folded.sorted_under
            for pk, folded in computed.items()
            if folded.sorted_under is not None
        }
        if recategorised:
            models = _mustered(models, recategorised)

    gang_rows, gang_rules = _gang_rows(gang_card, gang_computed)
    return GangSheet(
        name=gang.name,
        gang_type=gang.gang_type.name,
        rating=gang.rating,
        credits=gang.credits,
        credits_unlimited=gang.credits_unlimited,
        wealth=gang.wealth,
        colour=gang.colour,
        rows=gang_rows,
        rules=gang_rules,
        choices=choice_lines(gang_computed, host=GANG_SLOT_HOST),
        counters=(
            gang_computed.counters if gang_computed else counter_readings(gang_card)
        ),
        stash=stash_lines(gang_card),
        stash_rating=gang_card.stash_rating,
        notes=gang_computed.notes if gang_computed else [],
        models=[
            build_model_card(
                model, card=cards.get(model.pk), computed=computed.get(model.pk)
            )
            for model in models
        ],
        summary=summarise_roster(models, recategorised),
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
