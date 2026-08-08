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
WEAPON_CHARACTERISTICS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("LR", "Long Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {}),
    ("L", "Lethality", {}),
]

MODEL_STATLINE = "Model"
WEAPON_STATLINE = "Weapon"

#: What each Type calls a lasting effect (core rules: the Lasting
#: Injury and Lasting Damage tables). The Types themselves are the
#: model's closed set — stated there, never restated here — and a
#: guard test keeps this covering exactly them.
LASTING_EFFECT_TERMS = {"Fighter": "Injury", "Vehicle": "Damage"}

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

#: The eight fields a Specialist chooses between, and the skill each
#: grants — the core rules' Specialist table, as ``(specialisation,
#: skill)``. Every skill named here is one of the sets' own, so the
#: grant resolves against rows the skills seed already created.
#:
#: Which specialisations exist is *content*, which is why they are
#: created here rather than invented by whatever first mentions one: an
#: equipment list saying "(Gunner specialist only)" resolves against
#: this, and says so plainly when it cannot.
SPECIALISATIONS = [
    ("Heavy", "Bulging Biceps"),
    ("Gunner", "Hip-shooting"),
    ("Gunslinger", "Gunfighter"),
    ("Scout", "Clamber"),
    ("Sniper", "Precision Shot"),
    ("Brawler", "Berserker"),
    ("Medic", "Medicate"),
    ("Tech", "Munitioneer"),
]

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

    rows = [
        (_stat(short, full, flags), display)
        for short, full, flags, display in MODEL_CHARACTERISTICS
    ]
    statline_type = _statline_type(MODEL_STATLINE, rows)
    for name in TYPE_NAMES:
        ProfileType.objects.get_or_create(
            name=name,
            defaults={
                "statline_type": statline_type,
                "lasting_effect_term": LASTING_EFFECT_TERMS[name],
            },
        )


def _check_model_characteristics():
    from n26.library.models import ProfileType, Stat, StatlineType

    names = [full for _, full, _, _ in MODEL_CHARACTERISTICS]
    present = _count(Stat, full_name__in=names)
    present += _count(StatlineType, name=MODEL_STATLINE)
    present += _count(ProfileType, name__in=TYPE_NAMES)
    return present, len(names) + 1 + len(TYPE_NAMES)


def _create_weapon_characteristics():
    rows = [
        (_stat(short, full, flags), {}) for short, full, flags in WEAPON_CHARACTERISTICS
    ]
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


def _create_skills_collection():
    from n26.library.models.collection import Collection, CollectionSection

    collection, _ = Collection.objects.get_or_create(name=SKILLS_COLLECTION)
    for position, (name, is_default) in enumerate(SKILL_TIERS):
        CollectionSection.objects.get_or_create(
            collection=collection,
            name=name,
            defaults={"position": position, "is_default": is_default},
        )


def _check_skills_collection():
    from n26.library.models.collection import Collection, CollectionSection

    present = _count(Collection, name=SKILLS_COLLECTION)
    present += _count(
        CollectionSection,
        collection__name=SKILLS_COLLECTION,
        name__in=[name for name, _ in SKILL_TIERS],
    )
    return present, 1 + len(SKILL_TIERS)


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


def _create_specialisations():
    """The Specialist's eight fields, each wired to the skill it grants.

    A specialisation is only half itself without the skill it grants, so
    this seed owns that dependency and creates the skills first rather than
    relying on which button someone pressed. ``_create_skills`` is
    get-or-create throughout, so saying so costs nothing when they are
    already there.

    Idempotent: a specialisation already present is left alone, because
    ``create_specialisation`` builds the granting modifier and calling it
    again would hang a second copy.
    """
    from n26.library.authoring import create_specialisation
    from n26.library.models import Skill, Specialisation

    _create_skills()
    for name, skill_name in SPECIALISATIONS:
        if Specialisation.objects.filter(name=name).exists():
            continue
        skill = Skill.objects.filter(name=skill_name).first()
        if skill is None:
            # The skills exist, so this can only be a typo in the
            # table above — say which, rather than create it unwired.
            raise LookupError(f"{name} grants {skill_name!r}, which no Skill Set names")
        create_specialisation(name, grants_skill=skill)


def _check_specialisations():
    """Counts the rows *and* their grants: a specialisation that grants
    nothing is created but not wired, which is half the point missing."""
    from n26.library.models import Specialisation

    names = [name for name, _ in SPECIALISATIONS]
    present = _count(Specialisation, name__in=names)
    present += (
        Specialisation.objects.filter(name__in=names, modifiers__isnull=False)
        .distinct()
        .count()
    )
    return present, 2 * len(names)


def _create_trading_post():
    from n26.library.authoring import create_trading_post
    from n26.library.models import Collection

    if not Collection.objects.filter(name=TRADING_POST_COLLECTION).exists():
        create_trading_post(TRADING_POST_COLLECTION)


def _check_trading_post():
    from n26.library.models import Collection, CollectionSelector

    present = _count(Collection, name=TRADING_POST_COLLECTION)
    present += _count(
        CollectionSelector,
        collection__name=TRADING_POST_COLLECTION,
        with_trade_point_price=True,
    )
    return present, 3  # the collection and its two sweeps


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
                "its Primary tier."
            ),
            check=_check_skills_collection,
            create=_create_skills_collection,
        ),
        StandardContent(
            key="specialisations",
            name="Specialisations",
            help=(
                "The eight fields a Specialist chooses between — Heavy, "
                "Gunner, Gunslinger, Scout, Sniper, Brawler, Medic, Tech "
                "— each wired to the skill it grants. An equipment list "
                'narrowed to "(Gunner specialist only)" resolves against '
                "these, so create them before importing one."
            ),
            check=_check_specialisations,
            create=_create_specialisations,
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
