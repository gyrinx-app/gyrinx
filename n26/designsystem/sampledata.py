"""Fixed sample data for the composition demos.

Hard-coded rather than read from the content app: a gallery page must render the
same thing on an empty database, and these exist to show a layout working, not to
prove the ORM does.
"""

from dataclasses import dataclass, replace

from django.utils.text import slugify

from n26.core.browse import CategoryGroup, CollectionView, PricedLine, SectionGroup
from n26.core.hire import STANDARD_OPTION_NAME, HireEntry, HireGroup, HireOption
from n26.core.notes import INFO, WARNING, Note
from n26.core.render import (
    AssignableLine,
    ChoiceLine,
    EffectLine,
    GangSheet,
    ModelCard,
    Provenance,
    StashLine,
    StatCell,
    Statline,
    WeaponLine,
    WeaponProfileLine,
)

HOUSES = [
    {
        "value": "ash-waste-nomads",
        "label": "Ash Wastes Nomads (BotO)",
    },
    {
        "value": "astartes",
        "label": "Astartes",
    },
    {
        "value": "badzone-enforcers",
        "label": "Badzone Enforcers (WD)",
    },
    {
        "value": "delaque",
        "label": "Delaque (HoS)",
    },
    {
        "value": "goliath",
        "label": "Goliath (HoC)",
    },
    {
        "value": "ironhead-prospectors",
        "label": "Ironhead Squat Prospectors (BotO)",
    },
    {
        "value": "ironhead-squats",
        "label": "Ironhead Squats (HotA)",
    },
    {
        "value": "spyre-hunting-party",
        "label": "Spyre Hunting Party",
    },
    {
        "value": "underhive-outcasts",
        "label": "Underhive Outcasts",
    },
    {
        "value": "van-saar",
        "label": "Van Saar (HoA)",
    },
    {
        "value": "venators",
        "label": "Venators (AN)",
    },
]

SORTS = [
    {"value": "recent", "label": "Recently edited"},
    {"value": "created", "label": "Newest first"},
    {"value": "name", "label": "Name A–Z"},
    {"value": "rating", "label": "Gang rating"},
    {"value": "starred", "label": "Most starred"},
]

STATUSES = [
    {"value": "active", "label": "Active"},
    {"value": "campaign", "label": "In a campaign"},
    {"value": "retired", "label": "Retired"},
    {"value": "draft", "label": "Draft"},
]

# Rows for the browse-screen composition.
LISTS = [
    {
        "name": "Rust in Peace",
        "house": "Goliath (HoC)",
        "rating": 1240,
        "status": "Active",
        "tone": "green",
        "edited": "4 weeks ago",
        "stars": 12,
    },
    {
        "name": "The Silent Ledger",
        "house": "Delaque (HoS)",
        "rating": 980,
        "status": "In a campaign",
        "tone": "blue",
        "edited": "2 days ago",
        "stars": 4,
    },
    {
        "name": "Sump City Rats",
        "house": "Underhive Outcasts",
        "rating": 1475,
        "status": "Active",
        "tone": "green",
        "edited": "yesterday",
        "stars": 31,
    },
    {
        "name": "Cog and Coil",
        "house": "Van Saar (HoA)",
        "rating": 1105,
        "status": "Retired",
        "tone": "ink",
        "edited": "8 months ago",
        "stars": 2,
    },
    {
        "name": "Prospect 19",
        "house": "Ironhead Squats (HotA)",
        "rating": 860,
        "status": "Draft",
        "tone": "amber",
        "edited": "3 hours ago",
        "stars": 0,
    },
]


# Rows for the collection-picker composition: a trading post, which is the
# case it was built for — long, categorised, browsed with a budget in mind.
#
# Names, costs and rarity ratings only. What any of it *does* is rulebook text
# and does not belong in this repository; see CLAUDE.md.
#
# `rarity` is 0 for common, otherwise the rating. `owned` marks the few already
# in the stash, which is what the row's optional icon is for.
#: What the gang already has, so a row can show it.
#:
#: Deliberately not on the line. A PricedLine says what a thing costs *here*;
#: whether you own one is gang state and belongs to whoever is doing the
#: shopping, so the sample keeps the two apart exactly as the real code does.
IN_STASH = {"Autopistol", "Stub gun", "Shotgun", "Mesh armour", "Photo-goggles"}


@dataclass(frozen=True)
class _Category:
    """Stands in for library.Category — a name, and the section it files under.

    ``narrow()`` matches categories as objects rather than names, because a
    category name is only unique within its section, so the sample needs
    objects for the real function to accept it — and ``position``, because
    re-shelving a narrowed view sorts the whole taxonomy by it. Both came from
    handing the sample to the real function and reading the error, which is the
    argument for building it this way at all.
    """

    name: str
    section: str
    position: int

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class _Stock:
    """Stands in for a library assignable in a list: a name and a home."""

    name: str
    category: _Category

    def __str__(self):
        return self.name


# The catalogue, as (section, category, [(name, credits, trade points, exclusive)]).
#
# Trade points rather than the "rarity" this sample used to invent: main settled
# the vocabulary, and R9 was never a thing the domain had. Exclusive is the "E"
# of both editions — equipment list only, and so absent from a trading post's
# sweeps — which is why two items here carry it.
_CATALOGUE = [
    (
        "Weapons",
        "Pistols",
        [
            ("Autopistol", 10, 0, False),
            ("Laspistol", 10, 0, False),
            ("Stub gun", 5, 0, False),
            ("Hand flamer", 75, 8, False),
            ("Plasma pistol", 50, 10, False),
            ("Needle pistol", 30, 9, False),
        ],
    ),
    (
        "Weapons",
        "Basic weapons",
        [
            ("Autogun", 15, 0, False),
            ("Lasgun", 15, 0, False),
            ("Shotgun", 30, 0, False),
            ("Boltgun", 55, 8, False),
            ("Combi-bolter", 80, 12, False),
        ],
    ),
    (
        "Weapons",
        "Special weapons",
        [
            ("Flamer", 130, 8, False),
            ("Grenade launcher", 65, 8, False),
            ("Long rifle", 35, 9, False),
            ("Meltagun", 135, 11, False),
            ("Plasma gun", 100, 10, False),
        ],
    ),
    (
        "Weapons",
        "Close combat",
        [
            ("Fighting knife", 15, 0, False),
            ("Stiletto knife", 20, 9, False),
            ("Chainsword", 25, 0, False),
            ("Power sword", 70, 9, False),
            ("Shock whip", 55, 9, False),
            ("Thunder hammer", 145, 12, False),
        ],
    ),
    (
        "Equipment",
        "Armour",
        [
            ("Flak armour", 10, 0, False),
            ("Mesh armour", 15, 0, False),
            ("Carapace armour, light", 80, 9, False),
            ("Carapace armour, heavy", 100, 11, False),
            ("Hazard suit", 10, 7, False),
            ("House flak, reinforced", 25, 0, True),
        ],
    ),
    (
        "Equipment",
        "Personal equipment",
        [
            ("Bio-booster", 35, 8, False),
            ("Photo-goggles", 35, 8, False),
            ("Respirator", 15, 7, False),
            ("Grapnel launcher", 60, 9, False),
            ("Infra-sight", 40, 9, False),
            ("Stimm-slug stash", 25, 10, False),
            ("Master-crafted toolkit", 45, 0, True),
        ],
    ),
]


#: Notes on the list, keyed by item name.
#:
#: Hand-written here because n26.browse.with_use_notes needs a fighter and a
#: database to ask its question of; the shape is exactly what it produces, so
#: the row draws the real thing.
USE_NOTES = {
    "Master-crafted toolkit": (
        Note(text="usable by Specialist only", about=None, level=WARNING),
    ),
    "Thunder hammer": (
        Note(text="takes the space of two weapons", about=None, level=INFO),
    ),
}


def trading_post() -> CollectionView:
    """The sample catalogue as a real n26.browse.CollectionView.

    Built as the render structure rather than as dicts, for the same reason the
    model card is built from n26.render dataclasses: the components are then
    typed against exactly what browse() produces, and a change in core breaks
    the gallery instead of quietly rendering something that is no longer true.

    charges_trade_points is on every line, because this is a trading post —
    an equipment list shows the same numbers and never charges them, and the
    flag rides the line so a till needs no idea where the line came from.
    """
    sections: list[SectionGroup] = []
    for position, (section_name, category_name, items) in enumerate(_CATALOGUE):
        if not sections or sections[-1].name != section_name:
            sections.append(SectionGroup(name=section_name))
        category = _Category(
            name=category_name, section=section_name, position=position
        )
        sections[-1].categories.append(
            CategoryGroup(
                name=category_name,
                lines=[
                    PricedLine(
                        thing=_Stock(name=name, category=category),
                        credits=credits,
                        trade_points=trade_points,
                        is_exclusive=exclusive,
                        charges_trade_points=True,
                        # A note is how the app says something without stopping
                        # anyone. with_use_notes() writes these for real, per
                        # fighter; the sample carries one so the row has a case
                        # to draw. Nothing is removed — we inform, never police.
                        notes=USE_NOTES.get(name, ()),
                    )
                    for name, credits, trade_points, exclusive in items
                ],
            )
        )
    return CollectionView(name="Trading Post", sections=sections)


def trading_post_context():
    """The list view needs the shape of its data as well as the data.

    The ends of each slider are also its "no filter" positions, so they have to
    span the data — derived here rather than typed into the template, where an
    item priced outside the range would silently vanish from the list.
    """
    view = trading_post()
    lines = [
        line
        for section in view.sections
        for category in section.categories
        for line in category.lines
    ]
    categories = [
        category.name for section in view.sections for category in section.categories
    ]
    return {
        "trading_post": view,
        # Both levels, with the first section flagged so it starts open. Flagged
        # here rather than tested in the template because a Cotton `:` attribute
        # resolves an expression rather than evaluating one, so `forloop.first`
        # is fine and `forloop.parentloop.first and forloop.first` silently was
        # not — it left every section shut.
        "trading_post_section_rows": [
            {"section": section, "first": index == 0}
            for index, section in enumerate(view.sections)
        ],
        "trading_post_categories": categories,
        "trading_post_sections": [section.name for section in view.sections],
        # The filter menu's values are the category names themselves: the group,
        # the item's registration and this menu all join on that one string, and
        # a separate slug would be a fourth thing to keep in step.
        "trading_post_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "trading_post_in_stash": IN_STASH,
        "trading_post_cost_floor": min(line.credits for line in lines),
        "trading_post_cost_ceiling": max(line.credits for line in lines),
        # Exclusive lines are left out of the ceiling: "E" is not a number, and
        # a bound derived from one would be meaningless.
        "trading_post_tp_ceiling": max(
            line.trade_points for line in lines if not line.is_exclusive
        ),
    }


#: Whose gangs these are. One constant because it appears in the dashboard's
#: greeting, in the gang sheet's breadcrumb and now in both forms' breadcrumbs —
#: three screens saying "tom" separately is three places for a rename to miss.
OWNER = "tom"


def nav_context():
    """The switchers a gang's screens draw, built as the real ones are built.

    The application's versions come from a query; these are the same
    structures with fixed rows, so the shell pages and the demos draw the
    controls the app draws with no database behind them.

    Two of them, because a gang's screen has two: the bar names the gang and
    offers the reader's others, and the heading — which is already the name —
    offers the same list as a chevron on its own, named differently so the two
    are told apart by anything reading the page aloud.
    """
    from n26.core.navigation import Switcher, SwitcherItem

    gangs = (
        SwitcherItem(label="The Ashen Choir", href="#the-ashen-choir", current=True),
        SwitcherItem(label="Gravebolt Kin", href="#gravebolt-kin"),
        SwitcherItem(label="Pit of Teeth", href="#pit-of-teeth"),
        SwitcherItem(label="The Rust Sermon", href="#the-rust-sermon"),
        SwitcherItem(label="Salt and Iron", href="#salt-and-iron"),
    )
    return {
        "sample_switcher": Switcher(
            label="The Ashen Choir",
            href="#the-ashen-choir",
            heading="Your gangs",
            menu_label="Switch to another gang",
            placeholder="Search gangs",
            empty="No gangs match",
            items=gangs,
        ),
        "sample_heading_switcher": Switcher(
            heading="Your gangs",
            menu_label="Your other gangs",
            placeholder="Search gangs",
            empty="No gangs match",
            items=gangs,
        ),
    }


def context():
    return {
        "houses": HOUSES,
        "gang_owner": OWNER,
        # Every demo that draws a gang type's badge needs the artwork as a
        # string, because that is what the library stores and what the component
        # sanitises. One name for it, so the demos cannot show two drawings.
        "sample_gang_icon": SAMPLE_GANG_ICON,
        "sorts": SORTS,
        "statuses": STATUSES,
        "lists": LISTS,
        **nav_context(),
        **trading_post_context(),
        **hire_context(),
        **gang_sheet_context(),
        **dashboard_context(),
    }


# ---------------------------------------------------------------- model cards

# Built as the real render dataclasses from n26.render, not as ad-hoc dicts, so
# the card components are typed against exactly what build_model_card() produces.
# No database needed: these are plain objects, and a gallery page has to render on
# an empty database.


def _cell(short, full, value, **flags):
    return StatCell(short_name=short, full_name=full, value=value, **flags)


def _printed(*names):
    """Assignables that are simply on the card, with nothing to explain."""
    return [AssignableLine(name=name) for name in names]


def _granted(name, source, source_kind):
    """One re-derived on read, because something else on the card grants it.

    `computed` is what separates a granted line from a bought one, and it is
    the flag the card renders differently — see n26.render.Provenance.
    """
    return AssignableLine(
        name=name,
        provenance=Provenance(source=source, source_kind=source_kind, computed=True),
    )


def _fighter_statline():
    """The Escher Gang Queen, from the rulebook page.

    Ld starts a new group and the four psychology stats are highlighted, which is
    what StatlineTypeStat.is_first_of_group and .is_highlighted mean in the
    database — the divider and the tint are not decisions the template makes.
    """
    return Statline(
        cells=[
            _cell("M", "Movement", '5"'),
            _cell(
                "WS",
                "Weapon Skill",
                "2+",
                # `modified` is derived from this list, so a modified cell is one
                # that can say what modified it — which is the whole point.
                modified_by=[
                    Provenance(
                        source="Weapon Skill", source_kind="advancement", computed=True
                    )
                ],
            ),
            _cell("BS", "Ballistic Skill", "3+"),
            _cell("S", "Strength", "3"),
            _cell("T", "Toughness", "3"),
            _cell("W", "Wounds", "3"),
            _cell("I", "Initiative", "5"),
            _cell("A", "Attacks", "3"),
            _cell("Sv", "Save", "5+"),
            _cell("Ld", "Leadership", "8", highlighted=True, first_of_group=True),
            _cell("Cl", "Cool", "8", highlighted=True),
            _cell("Wil", "Willpower", "7", highlighted=True),
            _cell("Int", "Intelligence", "7", highlighted=True),
        ]
    )


def _weapon_statline(rng_s, rng_l, acc_s, acc_l, strength, ap, damage, ammo):
    """A weapon profile's characteristics — the same machinery as a fighter's.

    Two columns are called S and L twice over, which is why full_name matters:
    the header can say what an ambiguous abbreviation means without the row
    getting any wider.
    """
    return Statline(
        cells=[
            _cell("S", "Short range", rng_s, first_of_group=True),
            _cell("L", "Long range", rng_l),
            _cell("S", "Short range accuracy", acc_s, first_of_group=True),
            _cell("L", "Long range accuracy", acc_l),
            _cell("Str", "Strength", strength, first_of_group=True),
            _cell("Ap", "Armour Piercing", ap),
            _cell("D", "Damage", damage),
            _cell("Am", "Ammo", ammo),
        ]
    )


def model_card():
    """One fighter's card, with enough going on to exercise the components.

    Deliberately includes the awkward cases: a modified characteristic, a weapon
    with a paid second profile, a trait granted by a modifier rather than printed,
    and an unresolved choice.
    """
    return ModelCard(
        # The miniature's own name, and separately the library entry she was
        # hired from. Different fields because they are different facts: she was
        # bought as an "Escher Gang Queen" and named afterwards, which is what
        # everybody does.
        name="Vesna Krail",
        profile_name="Escher Gang Queen",
        rating=135,
        # type_line is derived from these two, not stored: "Fighter (Leader)".
        profile_type="Fighter",
        subtypes=_printed("Leader"),
        statline=_fighter_statline(),
        weapons=[
            WeaponLine(
                name="Needle pistol",
                base_rating=30,
                profiles=[
                    WeaponProfileLine(
                        # Unnamed: this is the weapon's own line, and the card
                        # prints the weapon's name on it. Naming it after the
                        # weapon would render the same and mean something else —
                        # a profile that happens to share the name — so the two
                        # only agree by accident. See WeaponProfileLine.name.
                        name="",
                        rating=0,
                        statline=_weapon_statline(
                            '4"', '8"', "+2", "-", "-", "-", "1", "6+"
                        ),
                        traits=_printed("Sidearm", "Silent", "Toxin (2+)"),
                    )
                ],
            ),
            WeaponLine(
                name="Lasgun",
                base_rating=15,
                profiles=[
                    WeaponProfileLine(
                        name="",
                        rating=0,
                        statline=_weapon_statline(
                            '8"', '24"', "+1", "-", "3", "-", "1", "6+"
                        ),
                        traits=_printed("Plentiful"),
                    ),
                    WeaponProfileLine(
                        # No leading dash. It was standing in for "this hangs
                        # off the weapon above", which the indent on screen and
                        # the italic in print already say — and an em-dash in a
                        # name field is now the one thing that reads as a profile
                        # with no name at all.
                        name="Hotshot las pack",
                        rating=10,
                        statline=_weapon_statline(
                            '8"', '24"', "+1", "-", "4", "-1", "1", "5+"
                        ),
                        # Unstable is not printed on the ammo — a modifier grants
                        # it, and the provenance is what lets the card say so.
                        traits=[
                            *_printed("Plentiful"),
                            _granted("Unstable", "Hotshot las pack", "profile"),
                        ],
                    ),
                ],
                # Bolted to the weapon rather than carried by the fighter, which
                # is the whole point of the accessory scope: "the weapon I am
                # attached to". A card has to be able to say which weapon.
                accessories=[AssignableLine(name="Telescopic sight")],
            ),
            WeaponLine(
                # Two profiles, both free, neither named after the weapon — so the
                # first cannot be hoisted onto the weapon's own row. A grenade
                # launcher is not its frag round. This is the case a rule based on
                # profile count or cost would get wrong: there are two, and both
                # cost nothing.
                name="Grenade launcher",
                base_rating=65,
                profiles=[
                    WeaponProfileLine(
                        name="frag",
                        rating=0,
                        statline=_weapon_statline(
                            '6"', '24"', "-", "-", "3", "-", "1", "4+"
                        ),
                        traits=_printed('Blast (3")', "Knockback"),
                    ),
                    WeaponProfileLine(
                        name="krak",
                        rating=0,
                        statline=_weapon_statline(
                            '6"', '24"', "-", "-", "6", "-2", "2", "5+"
                        ),
                        traits=_printed("Knockback"),
                    ),
                ],
            ),
            WeaponLine(
                name="Stiletto knife",
                base_rating=20,
                profiles=[
                    WeaponProfileLine(
                        name="",
                        rating=0,
                        statline=_weapon_statline(
                            "-", "E", "-", "-", "-", "-", "1", "-"
                        ),
                        traits=_printed("Melee", "Toxin (4+)"),
                    )
                ],
            ),
        ],
        # Bought skills and granted ones now sit in one list, told apart by
        # provenance rather than by living in a separate field — which is why
        # the card no longer has a "Rules" row for the granted ones.
        # Sorted by name, as build_model_card() returns them. Overseer is not
        # here even though the fighter has it: it answers the Leader's skill
        # choice, and the builder draws a node that answers a choice as that
        # choice's row rather than as a loose skill as well.
        skills=[
            _granted("Gang Hierarchy", "Leader", "subtype"),
            _granted("Group Activation (2)", "Leader", "subtype"),
            _granted("Overseer", "Leader", "subtype"),
            *_printed("Spring Up"),
        ],
        equipment=_printed(
            "Mesh armour (15¢)", "Bio-booster (35¢)", "Photo-goggles (35¢)"
        ),
        # One choice, still open, and it asks for something the rows above do not
        # already list. A chosen skill is a skill — Overseer sits in `skills`
        # with the rest, marked as granted — so a row labelled "Skill" holding
        # one skill would be a third skills row on a card that has one.
        choices=[
            ChoiceLine(
                kind_label="Specialisation",
                chosen=None,
                provenance=Provenance(
                    source="Specialist", source_kind="subtype", computed=True
                ),
            ),
        ],
        # A Wyrd's powers, which are not skills. Drawn apart on the card
        # because the rules treat them apart, even though they are chosen the
        # same way — see ModelCard.powers.
        powers=[
            _printed("Assail")[0],
            _granted("Mind Lock", "Wyrd", "subtype"),
        ],
        # Where this fighter can shop. Access to buy, not things owned, which
        # is why the card draws it apart from gear — see ModelCard.collections.
        collections=[
            _granted("House Escher Equipment List", "Escher", "profile"),
            *_printed("Trading Post"),
        ],
        # Something the kit does beyond this card. A stored effect is *shown,
        # never run*, so a hire preview can say what taking a thing would do
        # before anyone takes it — which is what `happened` is for.
        effects=[
            EffectLine(
                description="Adds a Cyber-mastiff to the gang",
                happened=False,
                provenance=Provenance(
                    source="Cyber-mastiff", source_kind="wargear", computed=True
                ),
            ),
        ],
        owned_by="tom",
        xp=61,
        xp_target=79,
    )


# ------------------------------------------------------------------- hiring
#
# A gang list is a collection of profiles — Profile is an Assignable, so a sweep
# contains them exactly as it contains weapons. Which means hiring sections the
# same way everything else does: sections holding categories holding rows.
#
# Sections here are authored, not derived. library.CollectionSection makes the
# tiers a collection's schema, so "Gang List", "Brutes", "Hangers-on" are content
# strings with positions, and nothing in a template decides them.


@dataclass(frozen=True)
class _Named:
    """A content row that is only ever asked for its name — a ProfileType.

    HireEntry.profile_type reads `.profile.profile_type.name`, so a string here
    fails at render rather than at import. Which is the argument for the stand-in
    being an object: it makes the sample the same shape as the real row, and the
    failure loud when it is not.
    """

    name: str

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class _Hireable:
    """Stands in for library.Profile: a name, a type, and a home category."""

    name: str
    profile_type: _Named
    category: _Category

    def __str__(self):
        return self.name


#: (section, category, [(name, cost, subtype, [(option name, surcharge)])]).
#:
#: Invented names and numbers: the rulebook reference deliberately excludes
#: individual gang lists, so there is nothing to copy even if copying were
#: allowed. The shapes are what matter — a profile with no options, one with
#: two, and the subtypes the composition limit counts.
_GANG_LIST = [
    (
        "Gang List",
        "Leaders",
        [
            (
                "Gang Queen",
                135,
                "Leader",
                [("As standard", 0), ("with a needle pistol", 30)],
            ),
        ],
    ),
    (
        "Gang List",
        "Champions",
        [
            (
                "Death Maiden",
                105,
                "Champion",
                [("As standard", 0), ("with a shock whip", 55)],
            ),
            ("Matriarch", 95, "Champion", []),
        ],
    ),
    (
        "Gang List",
        "Gangers",
        [
            ("Ganger", 55, "Ganger", []),
            (
                "Sharpshooter",
                70,
                "Specialist",
                [("As standard", 0), ("with a long rifle", 35)],
            ),
        ],
    ),
    (
        "Gang List",
        "Juves",
        [
            ("Wild Runner", 35, "Prospect", []),
        ],
    ),
    (
        "Brutes",
        "Brutes",
        [
            ("Khimerix", 190, "Brute", [("As standard", 0), ("with talons", 25)]),
            ("Phelynx", 90, "Brute", []),
        ],
    ),
    (
        "Hangers-on",
        "Hangers-on",
        [
            ("Rogue Doc", 80, "Hanger-on", []),
            ("Ammo-jack", 70, "Hanger-on", []),
            ("Dome Runner", 45, "Hanger-on", []),
        ],
    ),
]

#: A second axis of choice, for the profiles that have one.
#:
#: Option groups are main's answer to combinatorial blow-up: twelve authored sets
#: where flat combinations needed forty. A group is an axis — "choose one" is a
#: radio, "choose any" is checkboxes — and the hire view shows one card per
#: option against an otherwise-default selection, never one card per combination.
_OPTION_GROUPS = {
    "Gang Queen": [
        ("Wargear", "any", [("photo-goggles", 35), ("bio-booster", 35)]),
    ],
    "Khimerix": [
        ("Mutation", "one", [("scaly hide", 0), ("caustic bite", 15), ("wings", 30)]),
    ],
}


def extra_groups(profile_name, subtype, base_price):
    """The named axes a profile offers beyond its plain options.

    Every option carries a card, as main builds them: that option against an
    otherwise-default selection, never one card per combination. So a price here
    is the base plus this one surcharge, and never a running total across axes.
    """
    return [
        HireGroup(
            name=group_name,
            choose=choose,
            options=[
                HireOption(
                    name=option_name,
                    price=surcharge,
                    total_price=base_price + surcharge,
                    # Nothing in a named group is the default unless the axis is
                    # a one-of: "choose any" starts with none taken.
                    is_default=(choose == "one" and number == 0),
                    card=_hire_card(
                        profile_name, subtype, base_price + surcharge, 1 + number
                    ),
                )
                for number, (option_name, surcharge) in enumerate(options)
            ],
        )
        for group_name, choose, options in _OPTION_GROUPS.get(profile_name, [])
    ]


#: The subtypes the composition limit counts against the rest of the gang.
#:
#: Rulebook, Gang Composition: the number of models with the Champion, Brute or
#: Hanger-on subtype must be less than or equal to the number without. The view
#: shows the count and marks the rows; it never blocks — refusing is the
#: operation's job, and notes are explicitly not gates.
LIMITED_SUBTYPES = frozenset({"Champion", "Brute", "Hanger-on"})


def _hire_card(name, subtype, rating, weapons):
    """A preview card for a profile, from the same dataclasses a real one uses."""
    base = model_card()
    return replace(
        base,
        name=name,
        rating=rating,
        subtypes=_printed(subtype),
        weapons=base.weapons[:weapons],
        # A preview has no XP and nobody owns it yet, which is most of what
        # distinguishes it from the card of a model you already have.
        xp=0,
        xp_target=None,
        owned_by=None,
        # Stored effects are shown, never run: this is what makes the tense on
        # the card read as a consequence rather than a fact.
        effects=base.effects,
    )


def hire_list():
    """Every profile a gang could hire, in sections of categories.

    Mirrors what n26.hire.build_hire_list plus n26.browse's shelving would
    return, built by hand because a gallery renders on an empty database. The
    entries are real HireEntry/HireOption objects holding real ModelCards, so the
    components are typed against what the server sends.
    """
    section_rows = []
    for position, (section_name, category_name, profiles) in enumerate(_GANG_LIST):
        if not section_rows or section_rows[-1]["name"] != section_name:
            section_rows.append({"name": section_name, "categories": []})
        category = _Category(
            name=category_name, section=section_name, position=position
        )
        entries = []
        for name, price, subtype, option_specs in profiles:
            specs = option_specs or [(STANDARD_OPTION_NAME, 0)]
            options = [
                HireOption(
                    name=option_name,
                    price=surcharge,
                    total_price=price + surcharge,
                    is_default=(number == 0),
                    card=_hire_card(name, subtype, price + surcharge, 1 + number),
                )
                for number, (option_name, surcharge) in enumerate(specs)
            ]
            entries.append(
                HireEntry(
                    profile=_Hireable(
                        name=name,
                        profile_type=_Named("Fighter"),
                        category=category,
                    ),
                    # The default group first, always — "As standard" is
                    # synthesised when a profile offers no plain alternatives, so
                    # a renderer never branches on whether choices exist.
                    groups=[HireGroup(name=None, choose="one", options=options)]
                    + extra_groups(name, subtype, price),
                )
            )
        section_rows[-1]["categories"].append(
            {"name": category_name, "entries": entries}
        )
    return section_rows


def hire_entry(value):
    """The sample entry a press names, looked up by what the rows submit.

    The shell's rows submit their slugified name, so pressing Hire on one
    of three hundred can be answered with that one's dialog rather than a
    fixed example that would name the wrong fighter.
    """
    if not value:
        return None
    for section_row in hire_list():
        for category in section_row["categories"]:
            for entry in category["entries"]:
                if slugify(entry.name) == value:
                    return entry
    return None


def hire_context():
    """What the hire view needs: the sections, and the ends of its one slider."""
    section_rows = hire_list()
    entries = [
        entry
        for section_row in section_rows
        for category in section_row["categories"]
        for entry in category["entries"]
    ]
    categories = [
        category["name"]
        for section_row in section_rows
        for category in section_row["categories"]
    ]
    return {
        "hire_section_rows": [
            {"section": section_row, "first": index == 0}
            for index, section_row in enumerate(section_rows)
        ],
        "hire_categories": categories,
        "hire_sections": [section_row["name"] for section_row in section_rows],
        "hire_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "hire_price_floor": min(entry.base_price for entry in entries),
        "hire_price_ceiling": max(entry.base_price for entry in entries),
        # What a press hands the name dialog: the row's answer, already
        # given, riding to the next request as fields nobody has to retype.
        "hire_dialog_choices": ["Chainsword"],
        "hire_dialog_fields": [
            {"name": "profile", "value": "ganger"},
            {"name": "ganger:1", "value": "1"},
        ],
        # What a real gang would supply. Shown, never enforced.
    }


# ------------------------------------------------------------------ gang sheet

# A gang is a n26.render.GangSheet, built here as the real dataclass for the same
# reason the cards are: the components end up typed against what render_gang()
# actually produces, and a rename upstream fails at import rather than at a glance.


@dataclass(frozen=True)
class _Counter:
    """Stands in for library.Counter: something a CounterReading can name."""

    name: str

    def __str__(self):
        return self.name


def _reading(name, value):
    """A n26.effects.CounterReading, which is what GangSheet.counters holds."""
    from n26.core.effects import CounterReading

    return CounterReading(thing=_Counter(name), value=value)


#: What the gang owns and nobody is carrying. Real StashLines with their kinds on
#: them, exactly as render_gang builds them now — the component does the grouping,
#: because n26.render keeps the list flat on purpose and says grouping is the
#: renderer's business.
#:
#: Kinds are lower case because that is how a model's verbose_name reads: written
#: to appear mid-sentence. Whoever uses one as a heading capitalises it.
STASH = [
    StashLine(name="Lasgun", rating=15, kind="weapon"),
    StashLine(name="Shotgun", rating=30, kind="weapon"),
    StashLine(name="Stub gun", rating=5, kind="weapon"),
    StashLine(name="Mesh armour", rating=15, kind="wargear"),
    StashLine(name="Photo-goggles", rating=35, kind="wargear"),
    # Nobody bought this one: a modifier put it there, and it carries the mark a
    # granted skill carries on a card.
    StashLine(
        name="Respirator",
        rating=0,
        kind="wargear",
        provenance=Provenance(
            computed=True, source="Ash Wastes Nomads", source_kind="gang type"
        ),
    ),
    # Deliberately out of kind order. regroup starts a new group whenever the key
    # changes rather than gathering equal keys, so a stash arriving in any order
    # is the case the component's dictsort exists for.
    StashLine(name="Fighting knife", rating=15, kind="weapon"),
]


def gang_sheet():
    """One gang, with enough going on to exercise the sheet.

    The awkward cases on purpose: a choice with three answers — the "list inside
    one control" the detail list exists for — an unresolved choice, counters, and
    a stash holding something granted rather than bought.
    """
    return GangSheet(
        name="The Ashen Choir",
        gang_type="Escher (HoB)",
        rating=360,
        credits=1037,
        wealth=1397,
        colour="violet",
        rows=[
            AssignableLine(name="Founded in Cycle 3"),
            AssignableLine(name="Escher house list"),
            _granted("Toxin Trade", "Escher", "gang type"),
        ],
        choices=[
            ChoiceLine(kind_label="Skill trees", chosen="Ferocity, Brawn, Cunning"),
            # Unresolved is information, not an error: n26.render is explicit that
            # a renderer informs and does not police.
            ChoiceLine(kind_label="Territory", chosen=None),
        ],
        counters=[_reading("Reputation", 7), _reading("Meat", 3)],
        stash=STASH,
        stash_rating=115,
        models=[model_card()],
    )


#: What a player writes on a card, as opposed to what the rules put there.
#: Separate from model_card() because n26.render.ModelCard has no field for
#: either yet — see design/asks/model-card-notes-lore.md. Rendered markup, since
#: both will come out of the rich text editor.
CARD_NOTES = (
    "<p>Base needs redoing after the sump run — the flock came off. "
    "Owes Kaine a favour from the Ash Wastes job.</p>"
)
CARD_LORE = (
    "<p>Came up through the Choir's third dome and never lost the accent. "
    "Took the Matriarch's needle pistol off a body nobody has claimed, which is "
    "the only reason anyone remembers her name.</p>"
)


def gang_sheet_context():
    """What the gang sheet view needs."""
    sheet = gang_sheet()
    return {
        "gang": sheet,
        "card_notes": CARD_NOTES,
        "card_lore": CARD_LORE,
        # A gang of one card is a poor test of a three-column grid, so the demo
        # repeats the sample fighter under other names. Copies rather than the same
        # object five times, because a renderer that mutated one would otherwise
        # look fine.
        #
        # Named the way a real gang is: the model's own name, and separately the
        # library profile it was hired from. Vex and Sull are both Gangers, which
        # is the case worth having in the sample — one content entry, two
        # miniatures, and a card header that has to say which is which.
        "gang_members": [
            replace(sheet.models[0], name=name, profile_name=profile, rating=rating)
            for name, profile, rating in (
                ("Vesna Krail", "Escher Gang Queen", 135),
                ("Sister Yara", "Death Maiden", 105),
                ("Ilse Vandt", "Matriarch", 95),
                ("Vex", "Ganger", 55),
                ("Sull", "Ganger", 55),
            )
        ],
        "gang_owner": OWNER,
    }


# -------------------------------------------------------------------- dashboard

# Gangs as real GangSheets, because that is what <c-n26.wealth> takes and building
# them any other way would let the row and the sheet drift about what a gang is
# worth. Only the four figures matter here; a dashboard row draws nothing else.


#: Stand-in artwork for a gang type, in the shape an author would paste into the
#: library: one <svg>, drawn in a single colour so it takes the colour of the
#: text it sits beside. Plainly ours rather than any house's, because what these
#: pages show is that a badge appears at all — and that a type without one leaves
#: no gap.
SAMPLE_GANG_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path d="M12 2 3 6v6c0 5.1 3.8 8.8 9 10 5.2-1.2 9-4.9 9-10V6l-9-4Zm0 2.2 '
    '7 3.1V12c0 4.1-2.9 7.1-7 8.1-4.1-1-7-4-7-8.1V7.3l7-3.1Z"/>'
    '<path d="M9 9h6v2H9Zm2 3h2v5h-2Z"/></svg>'
)

#: Which sample gang types carry artwork, keyed by the name a row shows. Only
#: one does, deliberately: a table where every row has a badge cannot show
#: whether a row without one keeps the column's left edge.
GANG_TYPE_ICONS = {"Goliath (HoC)": SAMPLE_GANG_ICON}


def _gang_summary(name, gang_type, rating, credits, stash_rating, colour=""):
    return GangSheet(
        name=name,
        gang_type=gang_type,
        rating=rating,
        credits=credits,
        stash_rating=stash_rating,
        wealth=rating + credits + stash_rating,
        colour=colour,
    )


#: Five gangs, deliberately unalike: a long name to test the row on a phone, two
#: of the same type so the filter has something to narrow, one with nothing in the
#: stash so a zero is drawn rather than hidden, and two with no colour, because a
#: list where some rows carry a mark and some do not is the one that ships.
GANGS = [
    _gang_summary("The Ashen Choir", "Escher (HoB)", 360, 1037, 100, "violet"),
    _gang_summary("Rust in Peace", "Goliath (HoC)", 1240, 85, 0, "amber"),
    _gang_summary(
        "The Silent Ledger and the Long Count", "Delaque (HoS)", 980, 210, 45
    ),
    _gang_summary("Sump City Rats", "Underhive Outcasts", 1475, 12, 260, "teal"),
    _gang_summary("Cog and Coil", "Goliath (HoC)", 1105, 430, 75),
]

#: What changed, newest first. The summaries are long enough to be clamped, which
#: is the case the two-line rule exists for.
CHANGELOG = [
    {
        "title": "Vehicles",
        "date": "6 Aug",
        "text": (
            "Hire a Trazior and it brings its own card, with its own statline and "
            "its own weapons. Crew sit on the vehicle rather than beside it, so a "
            "gang sheet shows who is driving what."
        ),
    },
    {
        "title": "Weapon accessories",
        "date": "4 Aug",
        "text": (
            "Sights, suspensors and the rest hang off the weapon they are attached "
            "to rather than off the fighter carrying it, and the card says which."
        ),
    },
    {
        "title": "The stash",
        "date": "1 Aug",
        "text": (
            "A fourth place a thing can live: owned by the gang, carried by nobody, "
            "counting towards wealth and never towards the fighting rating."
        ),
    },
    {
        "title": "Outcasts",
        "date": "28 Jul",
        "text": (
            "Archetypes and affiliations, chained picks, and the ratio notes that "
            "come with them. Said, never enforced."
        ),
    },
]


def dashboard_context():
    """What the dashboard needs: the gangs, their types, and the changelog.

    A row is a dict wrapping its sheet rather than the sheet itself: what a row
    draws beside a gang's type is that type's artwork, which is a fact about the
    library's row and not about what this gang is worth. Keeping it out of
    GangSheet keeps markup out of the renderer's dataclasses.
    """
    return {
        "dashboard_gangs": [
            {
                "sheet": gang,
                "name": gang.name,
                "type": gang.gang_type,
                "colour": gang.colour,
                "type_icon": GANG_TYPE_ICONS.get(gang.gang_type, ""),
            }
            for gang in GANGS
        ],
        # Deduplicated in order rather than sorted: the filter reads better in the
        # order the reader already saw the types down the list.
        "dashboard_types": [
            {"value": name, "label": name}
            for name in dict.fromkeys(gang.gang_type for gang in GANGS)
        ],
        "dashboard_changelog": CHANGELOG,
        "dashboard_username": OWNER,
    }
