"""Standard content — the rows we know must exist, created on demand.

Some rows aren't anybody's authoring decision: the thirteen model
characteristics, the shape a weapon profile prints in, the Subtypes the
core rules name. Every pack needs them, they are the same every time,
and nothing else can be built until they are there — a weapon has no
stats to fill in until a weapon statline type exists.

So each is a named set of rows that can say whether it is already
there and can create what is missing. Buttons rather than a data
migration, deliberately — a migration runs once, invisibly, in an
order nobody remembers, whereas this shows its status on the page and
can be run again after a reset or a half-finished import.

Two rules hold:

* **Idempotent.** Running twice does nothing the second time. Every
  row is matched on its natural key and left alone if it is already
  there, so this can run against a database that has some of it.
* **Names and numbers only.** These carry what the rulebook *fixes* —
  a characteristic's short name and how it displays, a Subtype's name —
  and never rules text (CLAUDE.md).

Adding one is a definition list and one entry in ``STANDARD_CONTENT``.
"""

from collections.abc import Callable
from dataclasses import dataclass

from n26.library.models.profile import TYPE_NAMES

#: The 2026 model characteristics profile (core rules): nine battle
#: stats, then the four psychology stats — plain numbers, higher better,
#: never a plus. One shape serves Fighters and Vehicles alike; the Type
#: line tells them apart. ``(short, full, stat flags, display flags)``.
MODEL_CHARACTERISTICS = [
    ("M", "Movement", {"is_inches": True}, {"is_first_of_group": True}),
    ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}, {}),
    ("BS", "Ballistic Skill", {"is_target": True, "is_inverted": True}, {}),
    ("S", "Strength", {}, {}),
    ("T", "Toughness", {}, {}),
    ("W", "Wounds", {}, {}),
    ("I", "Initiative", {}, {}),
    ("A", "Attacks", {}, {}),
    ("Sv", "Save", {"is_target": True, "is_inverted": True}, {}),
    ("Ld", "Leadership", {}, {"is_highlighted": True, "is_first_of_group": True}),
    ("Cl", "Cool", {}, {"is_highlighted": True}),
    ("Wil", "Willpower", {}, {"is_highlighted": True}),
    ("Int", "Intelligence", {}, {"is_highlighted": True}),
]

#: The shape every weapon table prints (core rules). Strength is the
#: *same definition* as a fighter's — stat rows are shared across
#: statline types by design, so this seed reuses one if it is there.
#:
#: Armour Piercing is inverted: it is written as a negative number and
#: improving it means a lower one, so a house rule that improves AP by
#: one takes -1 to -2 rather than to zero.
WEAPON_CHARACTERISTICS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("LR", "Long Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {"is_inverted": True}),
    ("L", "Lethality", {}),
]

MODEL_STATLINE = "Model"
WEAPON_STATLINE = "Weapon"

#: Every Subtype the core rules name (core rules). Gang lists add their
#: own; these are the ones any pack can rely on.
FIGHTER_SUBTYPES = [
    "Beast",
    "Brute",
    "Champion",
    "Flying",
    "Ganger",
    "Hanger-On",
    "Leader",
    "Loner",
    "Mounted",
    "Agile",
    "Pet",
    "Prospect",
    "Specialist",
    "Support",
    "Wyrd",
]
VEHICLE_SUBTYPES = [
    "Hybrid",
    "Manoeuvrable",
    "Skimmer",
    "Tracked",
    "Transport",
    "Walker",
    "Wheeled",
]

#: The counters the core rules keep for every fighter. "Starting XP 61"
#: is a DefaultAssignment against the XP counter with ``amount=61``.
PROGRESSION_COUNTERS = ["XP"]
XP_COUNTER = "XP"

#: The counter a Visit Trading Post action reads to work out what each
#: model adds. Undrawn: no card shows it, and nothing offers to tally it
#: — the visit screen is the only reader. What raises it is a modifier on
#: each rank, so a fighter promoted into a rank adds what the rank adds
#: and one who has lost it adds nothing.
VISIT_CONTRIBUTION_COUNTER = "Trading Post visit contribution"

#: What each rank adds to a Trading Post visit (core rules), as
#: ``(subtype, amount)``, biggest first. A model holding both ranks adds
#: the better figure and not the sum: the same fighter cannot perform the
#: action twice. Each rank after the first is therefore scoped away from
#: models holding any rank above it.
VISIT_CONTRIBUTIONS = [("Leader", 2), ("Champion", 1)]

#: What each rank's contribution modifier is filed under. Named here so
#: that a clear of imported content can leave them standing by reading
#: this list rather than restating the names.
VISIT_CONTRIBUTION_MODIFIERS = [
    f"{rank} adds {amount} Trade Point{'' if amount == 1 else 's'} to a Trading Post visit"
    for rank, amount in VISIT_CONTRIBUTIONS
]

#: The heading a gang's own fighter entries are filed under. Everything
#: else a gang may hire — allies, hired guns, hangers-on — is filed
#: under a heading of its own, which is what tells the two apart.
GANG_LIST_SECTION = "Gang List"

#: The counter a fighter's founding budget is read off. Undrawn, like the
#: visit's: no card shows it, and the equip screen is the only reader.
#: What raises it is a modifier on the gang type, so a model hired into
#: a Venator gang gets the Venator figure and one hired into any other
#: gang gets none.
FOUNDING_BUDGET_COUNTER = "Founding TP budget"

#: What each rank on a gang's own list may spend at founding, by gang
#: type, biggest first (Venators and Outcast gang books).
#:
#: The rank is the subtype a gang's entries come with, and it is used to
#: find those entries rather than to reach models: a rank's subtype is
#: carried right across the library, and an ally or a hired gun ranked
#: Champion is nobody's Champion but their own. So each modifier names
#: the gang's own Gang List entries at that rank outright. A gang's
#: entry that carries two of these ranks is named by the better one and
#: left out of the rest, which is what keeps 5 and 4 from coming to 9.
#:
#: In a Venator gang the Hunter rank is the Specialist subtype: every
#: Hunter entry carries it.
FOUNDING_BUDGETS = [
    ("Venators", [("Leader", 5), ("Champion", 4), ("Specialist", 3)]),
    ("Outcast", [("Leader", 4), ("Champion", 3)]),
]

#: What an affiliation adds on top of the gang type's figure, as
#: ``(affiliation, gang type, ranks, amount)`` (Outcast gang book). Held
#: by the gang, so it reaches every model on the roster the way a Clan
#: House affiliation reaches them with its equipment list — and narrowed
#: to the same entries the gang type's own figures name.
FOUNDING_BUDGET_AFFILIATIONS = [("Clanless", "Outcast", ["Leader", "Champion"], 1)]


def _budget_modifier_name(carrier, ranks, amount, more=False):
    """What a founding-budget modifier is filed under on the authoring
    pages."""
    points = "Trade Point" if amount == 1 else "Trade Points"
    return (
        f"{carrier} {' or '.join(ranks)} may spend "
        f"{amount} {'more ' if more else ''}{points} at founding"
    )


#: The six Skill Sets and their skills, in D6 order (core rules) —
#: the number a skill is rolled on is its position within its set. Names
#: only: what each skill *does* is the book's wording (CLAUDE.md).
SKILL_SETS = {
    "Agility": [
        "Catfall",
        "Clamber",
        "Dodge",
        "Mighty Leap",
        "Spring Up",
        "Sprint",
    ],
    "Brawn": [
        "Bull Charge",
        "Bulging Biceps",
        "Fearsome",
        "Iron Jaw",
        "Nerves of Steel",
        "Unstoppable",
    ],
    "Combat": [
        "Berserker",
        "Combat Master",
        "Headbutt",
        "Heavy Blows",
        "Rain of Blows",
        "Two-weapon Fighter",
    ],
    "Cunning": [
        "Backstab",
        "Counter-attack",
        "Cut-throat",
        "Infiltrate",
        "Lie Low",
        "Overwatch",
    ],
    "Savant": [
        "Connected",
        "Fast Reload",
        "Iron Will",
        "Medicate",
        "Mentor",
        "Munitioneer",
    ],
    "Shooting": [
        "Fast Shot",
        "Gunfighter",
        "Hip-shooting",
        "Marksman",
        "Precision Shot",
        "Sharpshooter",
    ],
}

#: Skills no Skill Set offers: a rule grants them, so they are rolled
#: for on no table and carry no D6 number. Free Ogryns' Immovable
#: Brutes grants Juggernaut.
INHERENT_SKILLS = ["Hit & Run", "Inspiring", "Juggernaut"]

#: Where the sets sit in the taxonomy — the heading above them.
SKILLS_SECTION = "Skills"
INHERENT_SET = "Inherent"

#: The collection whose tiers the printed Primary/Secondary skill grids
#: place skill sets into (design/collections.md). The tiers are rows of
#: its schema, so a placement aims at "Primary (Skills & Powers)" rather
#: than restating a string.
SKILLS_COLLECTION = "Skills & Powers"
SKILL_TIERS = [("Primary", False), ("Secondary", False), ("Other", True)]

#: The Trading Post: membership is having a trade point price, so it is
#: two sweeps and no hand-kept list — author a weapon with a TP and it
#: is simply there.
TRADING_POST_COLLECTION = "Trading Post"

#: The taxonomy section whose profiles every gang may hire, whichever
#: gang type authored them — hangers-on, brutes, hired guns. Being
#: supplementary is a fact of the taxonomy, not of a gang type: an
#: author files a profile's home category under this section and it
#: appears on every gang's hire screen.
SUPPLEMENTARY_SECTION = "Supplementary Profiles"

#: Every gang the published lists cover. Names only — a gang type's
#: profiles, equipment list and rules are authored content, hung on
#: these rows later.
GANG_TYPES = [
    "Ash Waste Nomads",
    "Cawdor",
    "Chaos Helot Cult",
    "Corpse Grinder Cults",
    "Delaque",
    "Escher",
    "Free Ogryn",
    "Genestealer Cults",
    "Goliath",
    "Ironhead Squats",
    "Malstrain",
    "Orlock",
    "Outcast",
    "Palanite Enforcers",
    "Spyre Hunters",
    "Van Saar",
    "Venators",
]


@dataclass(frozen=True)
class StandardContent:
    """One known-necessary set of rows: what it is, and how it stands."""

    key: str
    name: str
    help: str
    #: ``() -> (present, total)`` — how much of this is already there.
    check: Callable
    #: ``() -> None`` — create what is missing. Safe to call any time.
    create: Callable

    def status(self):
        present, total = self.check()
        if present == 0:
            return "missing"
        return "complete" if present >= total else "incomplete"


# --- Helpers ---------------------------------------------------------


def _stat(short, full, flags):
    """One characteristic definition, matched on its name."""
    from n26.library.models import Stat

    stat = Stat.objects.filter(full_name=full).first()
    if stat is None:
        stat = Stat.objects.create(short_name=short, full_name=full, **flags)
    return stat


def _heading(stat, short):
    """How this shape heads the column, where the shared definition
    abbreviates it differently. Strength is one definition, printed S on
    a model and Str on a weapon, and whichever shape is seeded second
    finds the other's abbreviation already on the row."""
    return {} if stat.short_name == short else {"short_name_override": short}


def _statline_type(name, rows):
    """A statline shape and its ordered stats. ``rows`` are
    ``(stat, display flags)`` in print order."""
    from n26.library.models import StatlineType, StatlineTypeStat

    statline_type, _ = StatlineType.objects.get_or_create(name=name)
    for position, (stat, display) in enumerate(rows):
        StatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=stat,
            defaults={"position": position, **display},
        )
    return statline_type


def _named(model, names):
    """Rows of a name-only kind, one per name, left alone if present."""
    for name in names:
        model.objects.get_or_create(name=name)


def _count(model, **lookup):
    return model.objects.filter(**lookup).count()


# --- The seeds --------------------------------------------------------------


def _create_model_characteristics():
    from n26.library.models import ProfileType

    rows = []
    for short, full, flags, display in MODEL_CHARACTERISTICS:
        stat = _stat(short, full, flags)
        rows.append((stat, display | _heading(stat, short)))
    statline_type = _statline_type(MODEL_STATLINE, rows)
    for name in TYPE_NAMES:
        ProfileType.objects.get_or_create(
            name=name,
            defaults={"statline_type": statline_type},
        )


def _check_model_characteristics():
    from n26.library.models import ProfileType, Stat, StatlineType

    names = [full for _, full, _, _ in MODEL_CHARACTERISTICS]
    present = _count(Stat, full_name__in=names)
    present += _count(StatlineType, name=MODEL_STATLINE)
    present += _count(ProfileType, name__in=TYPE_NAMES)
    return present, len(names) + 1 + len(TYPE_NAMES)


def _create_weapon_characteristics():
    rows = []
    for short, full, flags in WEAPON_CHARACTERISTICS:
        stat = _stat(short, full, flags)
        rows.append((stat, _heading(stat, short)))
    _statline_type(WEAPON_STATLINE, rows)


def _check_weapon_characteristics():
    from n26.library.models import Stat, StatlineType

    names = [full for _, full, _ in WEAPON_CHARACTERISTICS]
    present = _count(Stat, full_name__in=names)
    present += _count(StatlineType, name=WEAPON_STATLINE)
    return present, len(names) + 1


def _create_progression_counters():
    from n26.library.models import Counter

    _named(Counter, PROGRESSION_COUNTERS)


def _check_progression_counters():
    from n26.library.models import Counter

    return (
        _count(Counter, name__in=PROGRESSION_COUNTERS),
        len(PROGRESSION_COUNTERS),
    )


def visit_contribution_counter():
    """The standard visit-contribution counter, or None where the library
    has none.

    Pinned to the default pack, as the Trading Post is: names are unique
    per pack, so a homebrew pack's counter of the same name must not
    stand in for the standard one. The seed, its own completeness check
    and every reader ask this one question, because two statements of
    what counts as the row drift in silence.

    The pack is named by its slug rather than fetched first, so a page
    asking this pays one query and not two. A library with no default
    pack has no counter in it either, which is the same None.
    """
    from django.conf import settings

    from n26.library.models import Counter

    return Counter.objects.filter(
        name__iexact=VISIT_CONTRIBUTION_COUNTER,
        pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
    ).first()


def _create_visit_contribution():
    """The visit counter, and one modifier per rank that raises it.

    The subtypes are matched, not duplicated: the core subtypes seed
    creates the same two rows, and either seed may be run first.

    Ranks are read biggest first, and each modifier after the first is
    narrowed to models holding none of the ranks above it. That is what
    makes a Leader who is also a Champion add 2 rather than 3.

    A rank's contribution is matched by what it does — a modifier this
    rank carries that raises this counter — rather than by its name. A
    rank carrying two of them would add twice what it should, and a name
    is the one part of a modifier that may be reworded later.
    """
    from n26.library.authoring import (
        ef_contributes_to_counter,
        has_subtypes,
        modifier,
        targets_model,
    )
    from n26.library.models import Counter, Subtype

    counter = visit_contribution_counter()
    if counter is None:
        counter = Counter.objects.create(name=VISIT_CONTRIBUTION_COUNTER, drawn=False)
    better = []
    for (rank, amount), name in zip(
        VISIT_CONTRIBUTIONS, VISIT_CONTRIBUTION_MODIFIERS, strict=True
    ):
        subtype = _by_name(Subtype, rank)
        if subtype is None:
            subtype = Subtype.objects.create(name=rank)
        if not _raises_visit_counter(subtype, counter).exists():
            subtype.modifiers.add(
                modifier(
                    name,
                    targets_model(
                        *([has_subtypes(*better, negate=True)] if better else [])
                    ),
                    ef_contributes_to_counter(counter, amount),
                )
            )
        better.append(subtype)


def _raises_visit_counter(subtype, counter):
    """The modifiers this rank carries that raise this counter."""
    return subtype.modifiers.filter(contributes_to_counter__counter=counter)


def _check_visit_contribution():
    """Asked exactly as the create asks it — the same counter lookup, the
    same rank lookup, the same behaviour predicate — so a half-built
    library reports what a second run would leave alone."""
    from n26.library.models import Subtype

    counter = visit_contribution_counter()
    if counter is None:
        return 0, 1 + len(VISIT_CONTRIBUTIONS)
    present = 1
    for rank, _ in VISIT_CONTRIBUTIONS:
        subtype = _by_name(Subtype, rank)
        if subtype is not None and _raises_visit_counter(subtype, counter).exists():
            present += 1
    return present, 1 + len(VISIT_CONTRIBUTIONS)


def founding_budget_counter():
    """The standard founding-budget counter, or None where the library
    has none.

    Pinned to the default pack, as the visit's is: names are unique per
    pack, so a homebrew pack's counter of the same name must not stand in
    for the standard one. The seed, its own completeness check and every
    reader ask this one question, because two statements of what counts
    as the row drift in silence.

    The pack is named by its slug rather than fetched first, so a page
    asking this pays one query and not two. A library with no default
    pack has no counter in it either, which is the same None.
    """
    from django.conf import settings

    from n26.library.models import Counter

    return Counter.objects.filter(
        name__iexact=FOUNDING_BUDGET_COUNTER,
        pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
    ).first()


def _by_name(model, name):
    """A row of this kind called this in the default pack, or None.

    Pinned to the pack for the same reason the counter is: names are
    unique per pack, so a homebrew pack's gang type or subtype of the
    same name is a different thing and must not stand in for the
    standard one.
    """
    from django.conf import settings

    return model.objects.filter(
        name__iexact=name, pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG
    ).first()


def _gang_list_profiles(gang_type, subtype):
    """The gang's own entries at this rank, biggest name last.

    Its own list, and not everything ranked that way: a rank's subtype is
    carried right across the library — fourteen allied entries and three
    Dramatis Personae are ranked Champion — and none of them is on this
    gang's list or given its founding allowance. What tells them apart is
    the heading each is filed under.

    Read from the library rather than listed, so an entry authored later
    is named the next time the seed runs, and the completeness check
    says so until it has been.
    """
    from django.conf import settings

    from n26.library.models import Profile

    return list(
        Profile.objects.filter(
            gang_type=gang_type,
            category__section__name__iexact=GANG_LIST_SECTION,
            built_ins__members__subtype=subtype,
            pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        )
        .distinct()
        .order_by("name")
    )


def _raises_founding_budget(carrier, counter, amount):
    """The modifiers this carrier holds that raise this counter by this
    much.

    Each rank a carrier grants an allowance to grants a different figure,
    so the figure is what tells one rank's modifier from another's. A
    name is the one part of a modifier that may be reworded later, and
    the entries it reaches are the part the seed keeps up to date.
    """
    return carrier.modifiers.filter(
        contributes_to_counter__counter=counter,
        contributes_to_counter__amount=amount,
    )


def _naming_rows(modifier):
    """The rows naming the entries a founding-budget modifier reaches.

    The positive ones only: a negated row says who it misses, which is
    not a set the seed keeps.
    """
    scope = modifier.targets_miniature
    return [] if scope is None else list(scope.is_profile.filter(negate=False))


def _named_profiles(modifier):
    """The entries a founding-budget modifier reaches, by id."""
    return {
        pk
        for row in _naming_rows(modifier)
        for pk in row.profiles.values_list("pk", flat=True)
    }


def _budget_ranks(gang_type):
    """Each rank this gang type grants an allowance to, with the figure
    and the entries it reaches — biggest figure first, and no entry named
    twice.

    An entry carrying two of these ranks belongs to the better one, which
    is what keeps 5 and 4 from coming to 9 for a model that is both. It
    is also why the set is worked out whole every time rather than added
    to: giving a Champion entry the Leader rank moves it between two
    figures, and an entry left named by the one it has left would raise
    the counter twice.
    """
    from n26.library.models import Subtype

    ranks = dict(FOUNDING_BUDGETS).get(gang_type.name, [])
    claimed, found = set(), []
    for rank, amount in ranks:
        subtype = _by_name(Subtype, rank)
        profiles = [] if subtype is None else _gang_list_profiles(gang_type, subtype)
        profiles = [one for one in profiles if one.pk not in claimed]
        claimed.update(one.pk for one in profiles)
        found.append((rank, amount, subtype, profiles))
    return found


def _drop_modifier(row):
    """Take a modifier away, parts and all.

    A modifier's columns cascade *from* its scope and its effect, so the
    parts are what a delete has to reach; left behind, they would keep
    nothing alive but themselves.
    """
    scope, effect = row.scope, row.effect
    row.delete()
    for part in (scope, effect):
        if part is not None:
            part.delete()


def _settle_budget(carrier, counter, name, amount, subtypes, wanted):
    """Make this contribution say what it should, whatever it said before.

    One modifier per figure per carrier, and its set of entries is
    rewritten rather than added to: an entry that has moved to another
    rank must stop being named here, or it would raise the counter twice.
    With no entry left to reach, the modifier goes — a rank nothing is
    filed under is not a rank this library grants anything to.

    The scope names the rank as well as the entries. The two narrow
    together, so while the set is intact it says exactly what the entries
    say — and if something outside the seed empties the set, what is left
    reaches that rank rather than the whole roster.
    """
    from n26.library.authoring import (
        ef_contributes_to_counter,
        has_subtypes,
        is_profile,
        modifier,
        targets_every_model,
    )
    from n26.library.models import IsProfile

    standing = _raises_founding_budget(carrier, counter, amount).first()
    wanted = {one.pk for one in wanted}
    if not wanted:
        if standing is not None:
            _drop_modifier(standing)
        return
    if standing is None:
        carrier.modifiers.add(
            modifier(
                name,
                targets_every_model(
                    has_subtypes(*subtypes),
                    is_profile(*_profiles_by_id(wanted)),
                ),
                ef_contributes_to_counter(counter, amount),
            )
        )
        return
    scope = standing.targets_miniature
    if scope is None:
        # It reaches something other than the models — an author's own
        # doing. Nothing here rewrites that; the completeness check says
        # the rank is not done until somebody looks.
        return
    rows = _naming_rows(standing) or [IsProfile.objects.create(scope=scope)]
    for row in rows:
        surplus = set(row.profiles.values_list("pk", flat=True)) - wanted
        if surplus:
            row.profiles.remove(*surplus)
    missing = wanted - _named_profiles(standing)
    if missing:
        rows[0].profiles.add(*missing)


def _profiles_by_id(ids):
    from n26.library.models import Profile

    return list(Profile.objects.filter(pk__in=ids))


def _empty_budget_modifiers(counter):
    """Every founding-budget modifier left naming no entry at all.

    Deleting a fighter entry takes it out of the sets naming it, and a
    modifier that named nothing else is then a contribution with nothing
    to reach. It is rebuilt below where the library still has entries for
    it, and stays gone where it does not.
    """
    from n26.library.models import Modifier

    return [
        row
        for row in Modifier.objects.filter(contributes_to_counter__counter=counter)
        if not _named_profiles(row)
    ]


def _create_founding_budgets():
    """The founding-budget counter, and one modifier per rank that raises
    it for the gang's own entries at that rank.

    Gang types and subtypes are matched, not duplicated: their own seeds
    create the same rows, and any of them may be run first. An
    affiliation is authored content and is never created here — a library
    without one has no gang holding it either.

    A rank's contribution is matched by what it does — a modifier this
    carrier holds that raises this counter by this figure — rather than
    by its name, so rewording one does not hang a second contribution on
    the carrier. What it *reaches* is worked out whole on every run, so
    an entry authored since the last one is named and an entry that has
    moved to another rank stops being.
    """
    from n26.library.models import Affiliation, Counter, GangType, Subtype

    counter = founding_budget_counter()
    if counter is None:
        counter = Counter.objects.create(name=FOUNDING_BUDGET_COUNTER, drawn=False)

    for row in _empty_budget_modifiers(counter):
        _drop_modifier(row)

    for gang_type_name, ranks in FOUNDING_BUDGETS:
        gang_type = _by_name(GangType, gang_type_name) or GangType.objects.create(
            name=gang_type_name
        )
        for rank, _ in ranks:
            if _by_name(Subtype, rank) is None:
                Subtype.objects.create(name=rank)
        for rank, amount, subtype, profiles in _budget_ranks(gang_type):
            _settle_budget(
                gang_type,
                counter,
                _budget_modifier_name(gang_type_name, [rank], amount),
                amount,
                [subtype] if subtype is not None else [],
                profiles,
            )

    for name, gang_type_name, ranks, amount in FOUNDING_BUDGET_AFFILIATIONS:
        affiliation = _by_name(Affiliation, name)
        gang_type = _by_name(GangType, gang_type_name)
        if affiliation is None or gang_type is None:
            continue
        subtypes = [_by_name(Subtype, rank) for rank in ranks]
        _settle_budget(
            affiliation,
            counter,
            _budget_modifier_name(name, ranks, amount, more=True),
            amount,
            [one for one in subtypes if one is not None],
            _affiliation_profiles(gang_type, ranks),
        )


def _affiliation_profiles(gang_type, ranks):
    """The entries an affiliation's extra figure reaches: the same ones
    the gang type's own figures name, at the ranks it lists."""
    wanted = set(ranks)
    return [
        one
        for rank, _, _, profiles in _budget_ranks(gang_type)
        if rank in wanted
        for one in profiles
    ]


def _check_founding_budgets():
    """Asked exactly as the create asks it — the same counter lookup, the
    same entry lookup, the same behaviour predicate — so a half-built
    library reports what a second run would leave alone.

    A rank counts as done only where its modifier names exactly the
    entries it should. An entry authored since the last run, one that has
    moved to another rank, and one deleted altogether each show the seed
    incomplete rather than being quietly left with the wrong figure.

    An affiliation that is not in the library is not counted, because the
    seed does not create one: it is authored content, and a library
    without it has no gang holding it.
    """
    from n26.library.models import Affiliation, GangType

    counter = founding_budget_counter()
    wanted, present = 1, 1 if counter is not None else 0

    def settled(carrier, amount, entries):
        """Whether this figure already says what a run would make it say —
        including saying nothing, where the modifier should be gone."""
        standing = (
            None
            if counter is None
            else _raises_founding_budget(carrier, counter, amount).first()
        )
        if not entries:
            return standing is None
        return standing is not None and _named_profiles(standing) == {
            one.pk for one in entries
        }

    def count(carrier, amount, entries):
        nonlocal wanted, present
        done = settled(carrier, amount, entries)
        if not entries and done:
            # Nothing to reach and nothing standing: this rank is not
            # something the library has, so it is nobody's business.
            return
        wanted += 1
        present += 1 if done else 0

    for gang_type_name, _ in FOUNDING_BUDGETS:
        gang_type = _by_name(GangType, gang_type_name)
        if gang_type is None:
            continue
        for _, amount, _, profiles in _budget_ranks(gang_type):
            count(gang_type, amount, profiles)

    for name, gang_type_name, ranks, amount in FOUNDING_BUDGET_AFFILIATIONS:
        affiliation = _by_name(Affiliation, name)
        gang_type = _by_name(GangType, gang_type_name)
        if affiliation is None or gang_type is None:
            continue
        count(affiliation, amount, _affiliation_profiles(gang_type, ranks))

    return present, wanted


def skills_collection_sweeps():
    """Every kind this collection lists: what a model selects rather than
    carries. A power is not a skill, and both are here because a grid
    places both into the same tiers — a kind missing from here is one no
    fighter can be shown."""
    from n26.library.models import Power, Skill

    return (Skill, Power)


def _create_skills_collection():
    """The collection, its tiers, and a sweep per kind it lists.

    Swept rather than listed by hand: membership is being that kind of
    thing, so authoring a skill puts it in front of every fighter whose
    grid names its set, with nothing to remember. Tops up an existing
    collection for the same reason the post does — a kind added later
    would otherwise be invisible.
    """
    from django.contrib.contenttypes.models import ContentType

    from n26.library.models.collection import (
        Collection,
        CollectionSection,
        CollectionSelector,
    )

    collection, _ = Collection.objects.get_or_create(name=SKILLS_COLLECTION)
    for position, (name, is_default) in enumerate(SKILL_TIERS):
        CollectionSection.objects.get_or_create(
            collection=collection,
            name=name,
            defaults={"position": position, "is_default": is_default},
        )
    for position, model in enumerate(skills_collection_sweeps()):
        CollectionSelector.objects.get_or_create(
            collection=collection,
            of_kind=ContentType.objects.get_for_model(model),
            defaults={"position": position},
        )


def _check_skills_collection():
    from django.contrib.contenttypes.models import ContentType

    from n26.library.models.collection import (
        Collection,
        CollectionSection,
        CollectionSelector,
    )

    present = _count(Collection, name=SKILLS_COLLECTION)
    present += _count(
        CollectionSection,
        collection__name=SKILLS_COLLECTION,
        name__in=[name for name, _ in SKILL_TIERS],
    )
    present += _count(
        CollectionSelector,
        collection__name=SKILLS_COLLECTION,
        of_kind__in=[
            ContentType.objects.get_for_model(model)
            for model in skills_collection_sweeps()
        ],
    )
    return present, 1 + len(SKILL_TIERS) + len(skills_collection_sweeps())


def _skill_rows():
    """``(set, skill, D6 number)`` for every skill the core rules name.

    The numbered sets first, in print order, then the inherent ones —
    which are granted rather than rolled, so they carry no number and
    fall back to sorting by name.
    """
    for set_name, skills in SKILL_SETS.items():
        for number, skill in enumerate(skills, start=1):
            yield set_name, skill, number
    for skill in INHERENT_SKILLS:
        yield INHERENT_SET, skill, 0


def _create_skills():
    from n26.library.models import Category, Section, Skill

    section, _ = Section.objects.get_or_create(name=SKILLS_SECTION)
    sets = {}
    for position, set_name in enumerate([*SKILL_SETS, INHERENT_SET]):
        sets[set_name], _ = Category.objects.get_or_create(
            section=section, name=set_name, defaults={"position": position}
        )
    for set_name, skill, number in _skill_rows():
        Skill.objects.get_or_create(
            name=skill,
            defaults={"category": sets[set_name], "position": number},
        )


def _check_skills():
    from n26.library.models import Category, Section, Skill

    names = [skill for _, skill, _ in _skill_rows()]
    present = _count(Section, name=SKILLS_SECTION)
    present += _count(
        Category, section__name=SKILLS_SECTION, name__in=[*SKILL_SETS, INHERENT_SET]
    )
    present += _count(Skill, name__in=names)
    return present, 1 + len(SKILL_SETS) + 1 + len(names)


def trading_post_sweeps():
    """Every kind the post offers: whatever a fighter can buy with Trade
    Points. An accessory is bought there as readily as the gun it bolts
    onto, so a kind missing from here is one nobody can buy."""
    from n26.library.models import Wargear, Weapon, WeaponAccessory

    return (Weapon, Wargear, WeaponAccessory)


def _create_trading_post():
    """The post, and one sweep per kind it offers.

    Tops up rather than skipping: a post built before a kind existed is
    the ordinary state of a library that has been running a while, and
    leaving it short would quietly keep those items out of the post.
    """
    from django.contrib.contenttypes.models import ContentType

    from n26.library.authoring import create_trading_post
    from n26.library.models import Collection, CollectionSelector

    post = Collection.objects.filter(name=TRADING_POST_COLLECTION).first()
    if post is None:
        create_trading_post(TRADING_POST_COLLECTION, contains=trading_post_sweeps())
        return
    for position, model in enumerate(trading_post_sweeps()):
        CollectionSelector.objects.get_or_create(
            collection=post,
            of_kind=ContentType.objects.get_for_model(model),
            with_trade_point_price=True,
            defaults={"position": position},
        )


def _check_trading_post():
    from n26.library.models import Collection, CollectionSelector

    present = _count(Collection, name=TRADING_POST_COLLECTION)
    present += _count(
        CollectionSelector,
        collection__name=TRADING_POST_COLLECTION,
        with_trade_point_price=True,
    )
    return present, 1 + len(trading_post_sweeps())


def _create_gang_types():
    from n26.library.models import GangType

    _named(GangType, GANG_TYPES)


def _check_gang_types():
    from n26.library.models import GangType

    return _count(GangType, name__in=GANG_TYPES), len(GANG_TYPES)


def _all_subtypes():
    return FIGHTER_SUBTYPES + VEHICLE_SUBTYPES


def _create_subtypes():
    from n26.library.models import Subtype

    _named(Subtype, _all_subtypes())


def _check_subtypes():
    from n26.library.models import Subtype

    names = _all_subtypes()
    return _count(Subtype, name__in=names), len(names)


#: The lasting-effect tables (core rules: the Lasting Injury and Lasting
#: Damage tables; the Spyre Hunters list's Hunting Rig Glitches; the
#: alliance rules' delegation injuries), as ``(band low, band high,
#: result)``. Names and bands only — what a result *does* is a modifier,
#: which seeds never write, so the results that change a characteristic
#: or move a counter are finished by hand.
LASTING_INJURY_TABLE = [
    (11, 11, "Lesson Learnt"),
    (12, 12, "Eternal Enmity"),
    (13, 13, "Bitter Enmity"),
    (14, 14, "Personal Enmity"),
    (15, 15, "Horrid Scars"),
    (16, 16, "Impressive Scars"),
    (21, 26, "Out Cold"),
    (31, 46, "Grievous Wound"),
    (51, 51, "Eye Injury"),
    (52, 52, "Hand Injury"),
    (53, 53, "Hobbled"),
    (54, 54, "Spinal Injury"),
    (55, 55, "Enfeebled"),
    (56, 56, "Head Injury"),
    (61, 62, "Captured"),
    (63, 65, "Critical Injury"),
    (66, 66, "Memorable Death"),
]

LASTING_DAMAGE_TABLE = [
    (11, 11, "Lesson Learnt"),
    (12, 12, "Eternal Enmity"),
    (13, 13, "Bitter Enmity"),
    (14, 14, "Personal Enmity"),
    (15, 16, "Percussive Repair"),
    (21, 26, "Superficial Damage"),
    (31, 46, "Major Damage"),
    (51, 52, "Busted Sights"),
    (53, 53, "Drive System Fault"),
    (54, 54, "Buckled Frame"),
    (55, 56, "Engine Fracture"),
    (61, 62, "Captured"),
    (63, 65, "Critical Damage"),
    (66, 66, "Catastrophic Explosion!"),
]

#: A Spyrer's suit takes the hit: their own D66 in place of the Lasting
#: Injury table. Ten results each move the Glitch Count as well.
SPYRER_GLITCH_TABLE = [
    (11, 11, "Lesson Learnt"),
    (12, 12, "Eternal Enmity"),
    (13, 13, "Bitter Enmity"),
    (14, 14, "Personal Enmity"),
    (15, 15, "Horrid Scars"),
    (16, 16, "Impressive Scars"),
    (21, 26, "Superficial Damage"),
    (31, 46, "Grievous Wound"),
    (51, 51, "Anxiety Suppression Damaged"),
    (52, 52, "Neural Feedback"),
    (53, 53, "Humbled"),
    (54, 54, "Vox Ghosts"),
    (55, 55, "Gyroscopic Destabilisation"),
    (56, 56, "Seized Locomotors"),
    (61, 61, "Targeting Uplink Disruption"),
    (62, 62, "Stuttering Servos"),
    (63, 63, "Damaged Musculature"),
    (64, 64, "Reduced Plate Density"),
    (65, 65, "Multiple Glitches"),
    (66, 66, "Critical Overload"),
]

#: An alliance's delegation rolls a D6, not a D66.
DELEGATION_INJURY_TABLE = [
    (1, 2, "Out Cold"),
    (3, 5, "Grievous Wound"),
    (6, 6, "Critical Injury"),
]

#: ``(slot type, plural — the card's heading, rows, die, qualifier)``.
#: A pack holds one pickable per name and qualifier, and several results
#: sit on more than one table at the same rolls. A table's qualifier
#: goes on each of its results that an earlier table already names, so
#: the first table's rows stay plain and every later twin is told apart
#: — author-facing only, never a player's word.
LASTING_EFFECT_TABLES = [
    ("Lasting Injury", "Lasting Injuries", LASTING_INJURY_TABLE, "d66", ""),
    ("Lasting Damage", "Lasting Damage", LASTING_DAMAGE_TABLE, "d66", "vehicle"),
    (
        "Spyrer Hunting Rig Glitch",
        "Spyrer Hunting Rig Glitches",
        SPYRER_GLITCH_TABLE,
        "d66",
        "spyrer",
    ),
    (
        "Delegation Lasting Injury",
        "Delegation Lasting Injuries",
        DELEGATION_INJURY_TABLE,
        "d6",
        "delegation",
    ),
]


def _twin_qualifier(table_index, result):
    """The qualifier a result carries on this table: the table's own if
    an earlier table already names the result, else none."""
    earlier = LASTING_EFFECT_TABLES[:table_index]
    if any(result in {row[2] for row in rows} for _, _, rows, _, _ in earlier):
        return LASTING_EFFECT_TABLES[table_index][4]
    return ""


#: Every result named on more than one table.
SHARED_LASTING_RESULTS = {
    result
    for index, (_, _, rows, _, _) in enumerate(LASTING_EFFECT_TABLES)
    for _, _, result in rows
    if _twin_qualifier(index, result)
}


def _lasting_row(model, name, qualifier, slot_type, defaults):
    """One pickable or slot for a table, matched three ways in turn.

    Its own slot type's row of that name is the one, whatever qualifier
    it was created with — a table seeded before a later table shared the
    name must not gain a second copy. Failing that, a row of that name
    and qualifier under another slot type is a name already claimed,
    refused in words rather than tripping the per-pack unique constraint
    (lowercased name and qualifier, not slot type) as a bare error.
    Otherwise the row is created.
    """
    own = model.objects.filter(name__iexact=name, slot_type=slot_type).first()
    if own is not None:
        return own
    taken = model.objects.filter(name__iexact=name, qualifier__iexact=qualifier).first()
    if taken is not None:
        raise RuntimeError(
            f'A {model._meta.verbose_name} named "{name}" already belongs '
            f'to the "{taken.slot_type}" slot type, so the "{slot_type}" '
            f"table cannot claim the name."
        )
    return model.objects.create(
        name=name, qualifier=qualifier, slot_type=slot_type, **defaults
    )


def _create_lasting_effect_tables():
    from n26.library.models import Pickable, Picklist, PicklistMember, Slot, SlotType

    for index, (name, plural, rows, dice, _) in enumerate(LASTING_EFFECT_TABLES):
        slot_type = SlotType.objects.filter(name__iexact=name).first()
        if slot_type is None:
            slot_type = SlotType.objects.create(
                name=name, plural_name=plural, allows_repeats=True
            )
        table = Picklist.objects.filter(
            slot_type=slot_type, name__iexact=f"{name} Table"
        ).first()
        if table is None:
            table = Picklist.objects.create(
                name=f"{name} Table",
                slot_type=slot_type,
                dice=dice,
                roll_selects="band",
            )
        for position, (low, high, result) in enumerate(rows):
            pickable = _lasting_row(
                Pickable, result, _twin_qualifier(index, result), slot_type, {}
            )
            PicklistMember.objects.get_or_create(
                picklist=table,
                pickable=pickable,
                defaults={
                    "roll_low": low,
                    "roll_high": high,
                    "position": position,
                },
            )
        _lasting_row(
            Slot,
            name,
            "",
            slot_type,
            {"picklist": table, "label": plural, "min_picks": 0, "max_picks": 20},
        )


def _check_lasting_effect_tables():
    from n26.library.models import PicklistMember, Slot, SlotType

    names = [name for name, _, _, _, _ in LASTING_EFFECT_TABLES]
    members = sum(len(rows) for _, _, rows, _, _ in LASTING_EFFECT_TABLES)
    present = _count(SlotType, name__in=names)
    present += _count(
        PicklistMember,
        picklist__name__in=[f"{name} Table" for name in names],
    )
    present += _count(Slot, name__in=names)
    return present, len(names) + members + len(names)


STANDARD_CONTENT = {
    item.key: item
    for item in [
        StandardContent(
            key="model-characteristics",
            name="Model characteristics",
            help=(
                "The thirteen characteristics every model has, the "
                "statline shape they print in, and the only two Types "
                "there are — Fighter and Vehicle. Nothing can be hired "
                "until these exist."
            ),
            check=_check_model_characteristics,
            create=_create_model_characteristics,
        ),
        StandardContent(
            key="weapon-characteristics",
            name="Weapon profile shape",
            help=(
                "Short and long range, Strength, Armour Piercing and "
                "Lethality, and the statline shape a weapon's profiles "
                "print in. A weapon has no stats to fill in without it."
            ),
            check=_check_weapon_characteristics,
            create=_create_weapon_characteristics,
        ),
        StandardContent(
            key="lasting-effect-tables",
            name="Lasting effect tables",
            help=(
                "The Lasting Injury and Lasting Damage tables, the Spyrer "
                "Hunting Rig Glitches and the delegation injuries as roll "
                "tables — a slot type, results at their bands, and a "
                "standing choice each. Names and bands only: results that "
                "change a characteristic or move a counter still need their "
                "modifiers attached, and each gang type a modifier that "
                "gives its models the right choice."
            ),
            check=_check_lasting_effect_tables,
            create=_create_lasting_effect_tables,
        ),
        StandardContent(
            key="core-subtypes",
            name="Core subtypes",
            help=(
                "Every Subtype the core rules name, for fighters and "
                "vehicles alike — Leader, Champion, Ganger, Wyrd, "
                "Mounted, Walker and the rest. Gang lists add their own."
            ),
            check=_check_subtypes,
            create=_create_subtypes,
        ),
        StandardContent(
            key="skills",
            name="Skills",
            help=(
                "Every skill the core rules name, in its Skill Set and "
                "at the D6 number it is rolled on — Agility, Brawn, "
                "Combat, Cunning, Savant, Shooting, and the inherent "
                "ones a rule grants. Names only: what each does stays "
                "in the book."
            ),
            check=_check_skills,
            create=_create_skills,
        ),
        StandardContent(
            key="progression-counters",
            name="Progression counters",
            help=(
                "The counters the core rules keep for every fighter — "
                "XP. A fighter entry's Starting XP is a built-in "
                "against this counter with its opening value."
            ),
            check=_check_progression_counters,
            create=_create_progression_counters,
        ),
        StandardContent(
            key="visit-contribution",
            name="Trading Post visit contribution",
            help=(
                "The counter for what each model adds to a Visit Trading "
                "Post action, and the modifiers that raise it: 2 on the "
                "Leader subtype, 1 on Champion. The counter is not drawn "
                "on any card. A model holding both ranks adds 2, not 3."
            ),
            check=_check_visit_contribution,
            create=_create_visit_contribution,
        ),
        StandardContent(
            key="founding-budgets",
            name="Founding TP budgets",
            help=(
                "The counter for the Trade Points a model may spend "
                "while its gang is being founded, and the modifiers that "
                "raise it: 5 on a Venator Leader, 4 on a Venator "
                "Champion, 3 on a Venator Specialist, 4 on an Outcast "
                "Leader, 3 on an Outcast Champion, and 1 more for a "
                "Clanless gang's Leaders and Champions. In a Venator "
                "gang the Hunter rank is the Specialist subtype. The "
                "counter is not drawn on any card. A model holding two "
                "ranks spends the better figure, not the sum."
            ),
            check=_check_founding_budgets,
            create=_create_founding_budgets,
        ),
        StandardContent(
            key="gang-types",
            name="Gang types",
            help=(
                "Every gang the published lists cover, from Ash Waste "
                "Nomads to Venators. Names only — each one's profiles, "
                "equipment list and rules are authored onto it later."
            ),
            check=_check_gang_types,
            create=_create_gang_types,
        ),
        StandardContent(
            key="skills-collection",
            name="Skills & Powers collection",
            help=(
                "The collection whose Primary, Secondary and Other "
                "tiers the printed skill grids place skill sets into. "
                "A gang list's Primary column is a placement aimed at "
                "its Primary tier. It sweeps in every skill and every "
                "power, so what a fighter may select follows from their "
                "grid alone."
            ),
            check=_check_skills_collection,
            create=_create_skills_collection,
        ),
        StandardContent(
            key="trading-post",
            name="Trading Post",
            help=(
                "The collection whose membership is having a trade "
                "point price: two sweeps — every weapon and every "
                "wargear with a TP set — and no hand-kept list. Author "
                "an item with a TP price and it is simply there; a "
                "weapon's TP-priced ammo rows ride under it."
            ),
            check=_check_trading_post,
            create=_create_trading_post,
        ),
    ]
}
