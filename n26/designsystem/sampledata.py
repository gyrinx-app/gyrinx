"""Fixed sample data for the composition demos.

Hard-coded rather than read from the content app: a gallery page must render the
same thing on an empty database, and these exist to show a layout working, not to
prove the ORM does.
"""

from dataclasses import dataclass, replace

from django.utils.text import slugify

from n26.core.actions import FOUNDING_HELP, VISIT_HELP, card_for
from n26.core.browse import (
    CategoryGroup,
    CollectionView,
    OfferedGroup,
    OfferedOption,
    PricedLine,
    SectionGroup,
)
from n26.core.confirm import Fact
from n26.core.hire import (
    STANDARD_OPTION_NAME,
    HireCategory,
    HireEntry,
    HireGroup,
    HireOption,
    HireSection,
)
from n26.core.images import MAX_PX, PORTRAIT
from n26.core.notes import INFO, WARNING, Note
from n26.core.render import (
    AssignableLine,
    ChoiceLine,
    ChoiceOffer,
    Choosable,
    ChoosableGroup,
    CounterLine,
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
from n26.core.views.equip import PRICE_CEILING

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
#: buying, so the sample keeps the two apart exactly as the real code does.
IN_STASH = {"Autopistol", "Stub gun", "Shotgun", "Mesh armour", "Photo-goggles"}


@dataclass(frozen=True)
class _Category:
    """Stands in for library.Category — a name, and the section it files under.

    ``narrow()`` matches categories as objects rather than names, because a
    category name is only unique within its section, so the sample needs
    objects for the real function to accept it — and ``position``, because
    regrouping a narrowed view sorts the whole taxonomy by it. Both came from
    handing the sample to the real function and reading the error, which is the
    argument for building it this way at all.
    """

    name: str
    section: str
    position: int

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class _Label:
    """The one thing ``thing_key`` reads off a model's ``_meta``."""

    label_lower: str


@dataclass(frozen=True)
class _Stock:
    """Stands in for a library assignable in a list: a name and a home.

    Carries a key the way a real row does, because a catalogue names every
    input after the row's content key and the shell posts nothing without
    one. The label is a fiction the same size as the real thing: what
    matters is that two rows never collide.
    """

    name: str
    category: _Category

    def __str__(self):
        return self.name

    @property
    def pk(self):
        return slugify(self.name)

    @property
    def _meta(self):
        return _Label("library.wargear")


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
    (
        "Equipment",
        "Mounts",
        [
            ("Grav-cutter", 150, 12, False),
            ("Ridge-runner", 90, 8, False),
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

#: Paid parts riding a line, keyed by the item they belong to, as
#: ``(name, credits, trade points)``. A gun's ammo is not a second thing on
#: the list — it is a way the gun is built — so a row that has any draws
#: tick boxes under it and buys them on the same click.
#:
#: Two guns carry some, and which two matters: the Boltgun is one nobody
#: holds, so its boxes sit on the row in the open, and the Meltagun is one
#: the fighter already has, so its boxes are inside the row that offers
#: another. Those are the two places a part is ever drawn.
PAID_PARTS = {
    "Boltgun": [("Kraken round", 15, 10)],
    "Meltagun": [("Melta round", 20, 11)],
}

#: The questions a line asks before it will sell you the thing, keyed by
#: the item that asks them, as ``(choose, [(name, surcharge)])``. A mount
#: comes with a weapon and will swap it for a dearer one; a fitting may be
#: added or left off. Both are ways the thing being bought is built rather
#: than second things on the list, so they are controls under one Buy.
#:
#: One item carries both kinds, because the two are drawn differently and
#: the second set is what puts a rule and a "how many to take" line on the
#: screen. The surcharges are distances from the row's own price, which is
#: what the real browse computes: the standard option adds nothing.
OFFERED = {
    "Grav-cutter": [
        (
            "one",
            [
                ("Grav-cutter grenade launchers", 0),
                ("Grav-cutter heavy stubbers", 10),
                ("Grav-cutter plasma guns", 15),
            ],
        ),
        ("one-or-none", [("Smoke dispenser", 20)]),
    ],
    #: The mount the sample fighter already owns. A second optioned line
    #: so that one can be drawn as a row still for sale, with its
    #: controls, while the other is drawn as a row already bought,
    #: naming what it was bought with.
    "Ridge-runner": [
        (
            "one",
            [("Ridge-runner scattergun", 0), ("Ridge-runner harpoon", 25)],
        ),
        ("one-or-none", [("Ridge-runner spikes", 10)]),
    ],
}


@dataclass(frozen=True)
class _Set:
    """What an option would bring, as far as a drawing needs to know.

    Only its identity is read here: a control starts picked when the
    thing being drawn holds this set, and the gallery holds nothing that
    could be fetched. The option's own name serves, because two options
    of one offer never share it.
    """

    pk: str


def _offered_choices(name):
    """The alternatives one line offers, as the structure browse builds."""
    return tuple(
        OfferedGroup(
            choose=choose,
            options=tuple(
                OfferedOption(
                    name=option,
                    surcharge=surcharge,
                    is_default=(choose == "one" and position == 0),
                    default_set=_Set(option),
                )
                for position, (option, surcharge) in enumerate(options)
            ),
        )
        for choose, options in OFFERED.get(name, ())
    )


def _part_lines(name, category):
    """The paid parts of one line, as the lines they really are."""
    return tuple(
        PricedLine(
            thing=_Stock(name=part, category=category),
            credits=credits,
            trade_points=trade_points,
            is_exclusive=False,
            charges_trade_points=True,
            shows_trade_points=True,
        )
        for part, credits, trade_points in PAID_PARTS.get(name, ())
    )


def trading_post() -> CollectionView:
    """The sample catalogue as a real n26.browse.CollectionView.

    Built as the render structure rather than as dicts, for the same reason the
    model card is built from n26.render dataclasses: the components are then
    typed against exactly what browse() produces, and a change in core breaks
    the gallery instead of quietly rendering something that is no longer true.

    Both trade-point flags are on every line, because this is a trading post:
    a post deals in Trade Points, so its rows print them, and a trading trip
    charges them. An equipment list does neither, and a sample of one would
    draw no TP column at all. Both ride the line so nothing downstream needs
    to know where a line came from.
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
                        shows_trade_points=True,
                        # A note is how the app says something without stopping
                        # anyone. with_use_notes() writes these for real, per
                        # fighter; the sample carries one so the row has a case
                        # to draw. Nothing is removed — we inform, never police.
                        notes=USE_NOTES.get(name, ()),
                        parts=_part_lines(name, category),
                        choices=_offered_choices(name),
                    )
                    for name, credits, trade_points, exclusive in items
                ],
            )
        )
    return CollectionView(name="Trading Post", sections=sections)


class _Collection:
    """A stand-in for a Collection where only its name and key are read.

    The tab strip is built by the equip screen's own function, so the
    gallery shortens names by the rule the real page uses rather than by
    a copy of it — and that function reads nothing else off a
    collection.
    """

    def __init__(self, name, pk):
        self.name = name
        self.pk = pk

    def __str__(self):
        return self.name


def _shop_tabs():
    """The lists one fighter can buy from: two their built-ins carry, then
    the Trading Post everyone reaches. Long names on purpose — that is
    what the strip has to survive on a phone."""
    from n26.core.views.equip import collection_tabs

    collections = [
        _Collection("Ash Waste Nomads Equipment List", "nomads"),
        _Collection("Dust Falls Trade Agreement Equipment List", "dust-falls"),
        _Collection("Trading Post", "post"),
    ]
    return collection_tabs(collections, collections[0])


def trading_post_context():
    """The list view needs the shape of its data as well as the data.

    The ends of each slider are also its "no filter" positions, so they have to
    span the data — derived here rather than typed into the template, where an
    item priced outside the range would silently vanish from the list.
    """
    from n26.core.listing import build_catalogue

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
        # The equip screen's own structure, built by the real function from the
        # sample catalogue and the sample fighter's kit. The shell then draws
        # it with the application's own row templates, so the two cannot come
        # to disagree about what a row looks like — the failure this replaces
        # was a hand-written copy of the row shape that nothing checked.
        "trading_post_catalogue": build_catalogue(view, carried()),
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
        # The bound the real purchase enforces, so the shell's boxes refuse what
        # the application's boxes refuse.
        "trading_post_price_cap": PRICE_CEILING,
        "trading_post_tabs": _shop_tabs(),
        "trading_post_price_floor": min(line.credits for line in lines),
        "trading_post_price_ceiling": max(line.credits for line in lines),
        # Exclusive lines are left out of the ceiling: "E" is not a number, and
        # a bound derived from one would be meaningless.
        "trading_post_tp_ceiling": max(
            line.trade_points for line in lines if not line.is_exclusive
        ),
    }


#: The crowded catalogue's shape: a section per supplier, sized the way the
#: biggest live catalogues are — most holding a handful of rows, a couple
#: holding dozens. The point of the numbers is their spread, not their sum:
#: a strip of twenty uneven tabs is what the component has to stay fast on.
_CROWDED_SUPPLIERS = (
    ("Ashfall Reclamators", 7),
    ("Bay Nineteen Auctions", 10),
    ("Cinder Row Outfitters", 5),
    ("Dredgeworks Combine", 4),
    ("Emberline Provisioners", 7),
    ("Flue Gate Traders", 7),
    ("Gantry Syndicate", 4),
    ("Hollowmarket", 7),
    ("Ironglass Exchange", 7),
    ("Junction Nine-Nine", 8),
    ("Kiln District Salvage", 3),
    ("Lift Shaft Consortium", 4),
    ("Meridian Vaults", 6),
    ("Null Zone Surplus", 6),
    ("Ossuary Lane Traders", 9),
    ("Pressline Wholesale", 5),
    ("Quench House", 14),
    ("Rustwater Cartel", 7),
    ("Sump Bottom Bazaar", 24),
)

_CROWDED_WARES = (
    "Autopistol",
    "Stub Gun",
    "Lasgun",
    "Shotgun",
    "Fighting Knife",
    "Flak Vest",
    "Respirator",
    "Grapnel Launcher",
    "Filter Plugs",
    "Photo-visor",
    "Cable Spool",
    "Servo Clamp",
)


def crowded_catalogue() -> CollectionView:
    """A catalogue at the volume the biggest live catalogues reach.

    Generated rather than written out — a couple of hundred rows typed
    by hand would be a page nobody maintains — and deterministic, so the
    strip and the counts read the same on every load. This is the
    specimen to open when a change might make the picker slower: the
    small demo above it stays fast whatever happens.
    """
    sections: list[SectionGroup] = []
    for supplier_index, (supplier, stocked) in enumerate(_CROWDED_SUPPLIERS):
        section = SectionGroup(name=supplier)
        for category_name, offset in (("Weapons", 0), ("Gear", 1)):
            category = _Category(
                name=f"{category_name} — {supplier}",
                section=supplier,
                position=supplier_index * 2 + offset,
            )
            lines = []
            for item_index in range(offset, stocked, 2):
                ware = _CROWDED_WARES[
                    (supplier_index + item_index) % len(_CROWDED_WARES)
                ]
                seed = supplier_index * 7 + item_index * 3
                lines.append(
                    PricedLine(
                        thing=_Stock(
                            name=f"{ware} (pattern {supplier_index + 1}-{item_index + 1})",
                            category=category,
                        ),
                        credits=5 * (seed % 38 + 1),
                        trade_points=seed % 13,
                        is_exclusive=False,
                        charges_trade_points=True,
                        shows_trade_points=True,
                    )
                )
            if lines:
                section.categories.append(
                    CategoryGroup(name=category.name, lines=lines)
                )
        sections.append(section)
    return CollectionView(name="Crowded Catalogue", sections=sections)


def crowded_catalogue_context():
    view = crowded_catalogue()
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
        "crowded_section_rows": [
            {"section": section, "first": index == 0}
            for index, section in enumerate(view.sections)
        ],
        "crowded_categories": categories,
        "crowded_sections": [section.name for section in view.sections],
        "crowded_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "crowded_line_count": len(lines),
        "crowded_price_floor": min(line.credits for line in lines),
        "crowded_price_ceiling": max(line.credits for line in lines),
        "crowded_tp_ceiling": max(line.trade_points for line in lines),
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
        # The chevron a model's own header carries: the gang's other
        # fighters, each row this same screen for them.
        # An inbox with something in it. A number rather than a string,
        # because the bar tests it for truth and "0" is true.
        "sample_unread": 3,
        "sample_fighter_switcher": Switcher(
            heading="Fighters",
            menu_label="Switch to another model",
            placeholder="Search fighters",
            empty="No fighters match",
            items=(
                SwitcherItem(label="Vesna Krail", href="#vesna-krail", current=True),
                SwitcherItem(label="Sister Yara", href="#sister-yara"),
                SwitcherItem(label="Ilse Vandt", href="#ilse-vandt"),
                SwitcherItem(label="Vex", href="#vex"),
                SwitcherItem(label="Sull", href="#sull"),
            ),
        ),
    }


def sample_miniature():
    """A stand-in for the model a header or an edit page is about.

    The components read ``pk`` and ``name`` and nothing else, so a
    namespace is the honest shape: the gallery renders on an empty
    database, and ``pk`` only has to be reversible into a URL.
    """
    from types import SimpleNamespace

    return SimpleNamespace(pk="sample", name="Vesna Krail")


def roster_summary():
    """The roster tally, in the shape ``n26.render.summarise_roster`` builds.

    Real dataclasses so the demo and the views cannot drift about what a
    tally is. The rows are a plausible mid-campaign gang: several ranks,
    two profiles that repeat, and pets — whose groups sit where their
    first keeper's does, exactly as the real reduction leaves them.
    """
    from n26.core.render import RosterGroup, RosterLine, RosterSummary

    groups = [
        RosterGroup(profile="Charter Master", category="Leader", count=1),
        RosterGroup(profile="Gyrinx Cat", category="Pet", count=2),
        RosterGroup(profile="Drill Master", category="Champion", count=2),
        RosterGroup(profile="Drill-kyn", category="Specialist", count=1),
        RosterGroup(profile="Drill-kyn", category="Ganger", count=1),
        RosterGroup(profile="Digger", category="Juve", count=2),
        RosterGroup(profile="Gearhead", category="Crew", count=1),
        RosterGroup(profile="Claim Jumper", category="Hanger-on", count=1),
        RosterGroup(profile="Techmite Autoveyor", category="Pet", count=1),
    ]
    models = [
        RosterLine(name="Vesna Krail", rating=135),
        RosterLine(name="Whiskers", rating=40),
        RosterLine(name="Sister Yara", rating=105),
        RosterLine(name="Ilse Vandt", rating=95),
        RosterLine(name="Vex", rating=55),
        RosterLine(name="Sull", rating=55),
        RosterLine(name="Pit", rating=30),
        RosterLine(name="Spanner", rating=30),
        RosterLine(name="Gears", rating=60),
        RosterLine(name="The Jumper", rating=80),
        RosterLine(name="Mote", rating=40),
        RosterLine(name="Tick", rating=25),
    ]
    return RosterSummary(
        groups=groups,
        models=models,
        count=sum(group.count for group in groups),
        rating=sum(line.rating for line in models),
    )


def context():
    return {
        "houses": HOUSES,
        "gang_owner": OWNER,
        "sample_miniature": sample_miniature(),
        "sample_roster_summary": roster_summary(),
        # Every demo that draws a gang type's badge needs the artwork as a
        # string, because that is what the library stores and what the component
        # sanitises. One name for it, so the demos cannot show two drawings.
        "sample_gang_icon": SAMPLE_GANG_ICON,
        # A stored picture's address for the components that draw one —
        # a data URI, because the gallery renders with no uploads store.
        "sample_picture": CARD_IMAGE,
        # The crop spec the picture components stamp onto the browser's
        # dialog, handed through from the server's own constants the way
        # a real page's view hands them — never spelt out in a demo.
        "sample_picture_shape": PORTRAIT,
        "sample_picture_max": MAX_PX,
        "sorts": SORTS,
        "choice_offer": choice_offer(),
        "empty_choice_offer": ChoiceOffer(label="Primary skill"),
        # A choice that holds several picks, part-way through and with no
        # room left: the two states where its acts differ.
        "choice_picks_offer": choice_picks_offer(),
        "full_choice_picks_offer": choice_picks_offer(full=True),
        # The same list a fighter's edit page ticks: what they hold, and
        # the one thing a rule gives them that no click can clear.
        "tick_list_offer": tick_list_offer(),
        # The two halves a pick list draws: what is held, and the rest of
        # the library its panel offers.
        "pick_list_held": pick_list_held(),
        "pick_list_addable": pick_list_addable(),
        # The same control where the groups are the point: skill sets,
        # each sitting in a tier.
        "pick_list_grouped": pick_list_grouped(),
        "editable_statline": editable_statline(),
        # A profile nobody has typed a statline for yet, and one where a
        # value was refused: the two states the editor has that a card
        # cannot have.
        "blank_editable_statline": editable_statline(filled=False),
        "refused_editable_statline": refused_statline(),
        # The same boxes as a player meets them, where an empty one keeps
        # the model's own value rather than meaning no value.
        "owner_statline_editor": owner_statline_editor(),
        "statuses": STATUSES,
        "lists": LISTS,
        **nav_context(),
        **trading_post_context(),
        **crowded_catalogue_context(),
        **hire_context(),
        **owned_context(),
        **gang_sheet_context(),
        **dashboard_context(),
        "sample_about": sample_about(),
    }


@dataclass(frozen=True)
class _Said:
    """A sentence as the about column reads one — duck-typed rather than
    imported, because the gallery shows the component working, and the
    real structure is the library's (n26.library.prose)."""

    text: str
    hint: str = ""
    href: str = ""


@dataclass(frozen=True)
class _AboutSample:
    referenced_by: tuple = ()
    does: tuple = ()
    assigned_to: object = None


@dataclass(frozen=True)
class _AssignedSample:
    gangs: int = 0
    rows: int = 0


def sample_about():
    """One thing's whole story, as the authoring pages tell it."""
    return _AboutSample(
        referenced_by=(
            _Said(
                text="Built into the Escher gang type.",
                hint=(
                    "Arrives free when the Escher gang type is assigned — "
                    "hired, founded, or bought. If that goes, this goes with it."
                ),
                href="#",
            ),
            _Said(
                text="Taken away from the gang by the Chaos Corrupted affiliation.",
                hint=(
                    "Removed while the Chaos Corrupted affiliation is assigned. "
                    "Nothing is deleted — remove the Chaos Corrupted "
                    "affiliation and this comes back. Paid-for items are never "
                    "removed."
                ),
                href="#",
            ),
        ),
        does=(
            _Said(
                text="Every fighter's weapons gain Backstab, while the gang holds this.",
                hint=(
                    "Applies while the item carrying this modifier is "
                    "assigned, and goes with it. Free — adds nothing to any "
                    "rating."
                ),
                href="#",
            ),
            _Said(
                text="It asks the gang to make the choice — the card says Choose until they pick.",
            ),
        ),
        assigned_to=_AssignedSample(gangs=14, rows=23),
    )


def choice_offer():
    """A pick list as a view hands it over: two headings, a line of
    detail on one option and, on another, the other choice that has
    already had it.

    Skill sets, because that is the case with headings worth showing —
    the same structure with one nameless group is what an offer naming a
    whole kind produces, and the component draws that with no legend.
    """
    return ChoiceOffer(
        label="Primary skill",
        groups=[
            ChoosableGroup(
                name="Agility",
                options=[
                    Choosable(key="library.skill:1", name="Catfall"),
                    Choosable(key="library.skill:2", name="Clamber"),
                    Choosable(key="library.skill:3", name="Dodge", is_current=True),
                ],
            ),
            ChoosableGroup(
                name="Cunning",
                options=[
                    Choosable(
                        key="library.skill:4",
                        name="Backstab",
                        taken_for="Second skill",
                    ),
                    Choosable(
                        key="library.skill:5",
                        name="Infiltrate",
                        detail="usable by Walkers only",
                    ),
                ],
            ),
        ],
    )


def choice_picks_offer(full=False):
    """A choice that holds several picks, part-way through being made.

    One nameless group, because a picklist has no headings — it is the
    pickables behind a choice and nothing else. Two of the three are held,
    so both acts are on the page at once; ``full`` is the same choice with
    no room left, where the ones it does not hold are not listed at all.
    """
    held = [
        Choosable(
            key="library.pickable:1",
            name="Cawdor",
            is_current=True,
            control="remove",
        ),
        Choosable(
            key="library.pickable:2",
            name="Escher",
            is_current=True,
            control="remove",
        ),
    ]
    rest = [
        Choosable(
            key="library.pickable:3",
            name="Ironhead Squats",
            control="choose",
            taken_for="Second legacy",
        ),
    ]
    return ChoiceOffer(
        label="Gang Legacy",
        takes_several=True,
        groups=[ChoosableGroup(name="", options=held if full else [*held, *rest])],
    )


def pick_list_held():
    """What the thing has, as a pick list draws it: one the owner added,
    one a rule gives that no click can clear, and one money stands behind
    that a removal would leave exactly where it is."""
    return ChoiceOffer(
        label="",
        groups=[
            ChoosableGroup(
                name="Skills",
                options=[
                    Choosable(
                        key="library.skill:1",
                        name="Catfall",
                        is_current=True,
                        detail="added by you",
                    ),
                    Choosable(
                        key="library.skill:3",
                        name="Dodge",
                        is_current=True,
                        granted_by="Keen-eyed",
                    ),
                    Choosable(
                        key="library.skill:9",
                        name="Sprint",
                        is_current=True,
                        fixed_because="bought — sell it to take it away",
                    ),
                ],
            )
        ],
    )


def pick_list_grouped():
    """The same control where the headings carry meaning: two skill sets,
    each saying which tier it sits in, one of them holding a skill a rule
    gives that no click can clear."""
    return ChoiceOffer(
        label="",
        groups=[
            ChoosableGroup(
                name="Agility",
                caption="Primary",
                options=[
                    Choosable(key="library.skill:1", name="Catfall", is_current=True),
                    Choosable(key="library.skill:2", name="Clamber"),
                    Choosable(
                        key="library.skill:3",
                        name="Dodge",
                        is_current=True,
                        granted_by="Keen-eyed",
                    ),
                ],
            ),
            ChoosableGroup(
                name="Savant",
                caption="Secondary",
                options=[
                    Choosable(key="library.skill:4", name="Connected"),
                    Choosable(
                        key="library.skill:5",
                        name="Fixer",
                        detail="usable by Leaders only",
                    ),
                ],
            ),
        ],
    )


def pick_list_addable():
    """The rest of the library the panel offers — enough rows that the
    filter box is the way through them rather than the eye."""
    names = [
        "Backstab",
        "Ballistic Expert",
        "Berserker",
        "Bull Charge",
        "Clamber",
        "Combat Master",
        "Escape Artist",
        "Fearsome",
        "Gunfighter",
        "Headbutt",
        "Infiltrate",
        "Iron Jaw",
        "Lie Low",
        "Mighty Leap",
        "Nerves of Steel",
        "Overwatch",
        "Parry",
        "Precision Shot",
        "Spring Up",
        "Unstoppable",
    ]
    return [
        Choosable(key=f"library.skill:{100 + at}", name=name)
        for at, name in enumerate(names)
    ]


def tick_list_offer():
    """The same list as a tick list: two tiers, some of it held already,
    and one line a rule grants.

    Two sections, so every heading says which tier its set sits in — the
    one-tier case is the same structure with the captions empty, and the
    component simply draws no caption.
    """
    return ChoiceOffer(
        label="",
        groups=[
            ChoosableGroup(
                name="Agility",
                caption="Primary",
                options=[
                    Choosable(key="library.skill:1", name="Catfall", is_current=True),
                    Choosable(key="library.skill:2", name="Clamber"),
                    Choosable(
                        key="library.skill:3",
                        name="Dodge",
                        is_current=True,
                        granted_by="Keen-eyed",
                    ),
                ],
            ),
            ChoosableGroup(
                name="Cunning",
                caption="Secondary",
                options=[
                    Choosable(key="library.skill:4", name="Backstab"),
                    Choosable(
                        key="library.skill:5",
                        name="Infiltrate",
                        detail="usable by Walkers only",
                    ),
                ],
            ),
        ],
    )


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


def _placeholder_for(value):
    """What an empty box suggests, read off the shape of the value the card
    shows: a distance suggests a distance, a roll target a target.

    The real placeholder comes from the stat's own display flags. Those are
    a database row, and this app has none, so the flags are inferred from
    how the value prints — which is what they decide.
    """
    if value.endswith('"'):
        return '4"'
    if value.endswith("+"):
        return "3+"
    return "3"


def editable_statline(filled=True, errors=None):
    """The card's characteristics as boxes an author types in.

    Derived from the display statline rather than written out a second
    time. Both sit on one gallery page, and an editor showing different
    columns from the card above it would be showing a different statline.

    ``errors`` names the characteristics to draw a refusal against, so the
    demo can show what a page looks like when a value is refused without
    anyone hand-building a broken cell.
    """
    from n26.core.render import EditableStatCell
    from n26.library.models import Stat

    return [
        EditableStatCell(
            short_name=cell.short_name,
            full_name=cell.full_name,
            # Input names are the stat's internal name, derived from the full
            # name exactly as the library derives it — so a demo cannot show a
            # form field the real page would not produce.
            name=Stat.derive_field_name(cell.full_name),
            value=cell.value if filled else "",
            placeholder=_placeholder_for(cell.value),
            highlighted=cell.highlighted,
            first_of_group=cell.first_of_group,
            error=errors.get(cell.short_name, "") if errors else "",
        )
        for cell in _fighter_statline().cells
    ]


def owner_statline_editor():
    """The characteristics as their owner sets them on a model's page.

    The author's boxes, with the one difference that matters: an empty
    box here means "keep what the model's entry prints", so the value it
    prints is what the box suggests rather than an example.
    """
    return [
        replace(cell, value="", placeholder=printed.value)
        for cell, printed in zip(
            editable_statline(filled=False), _fighter_statline().cells, strict=True
        )
    ]


def refused_statline():
    """The editor with one value refused.

    The box keeps what the author typed rather than the value that was
    already stored: a refusal they cannot see the cause of is one they
    cannot act on.
    """
    refusal = (
        "Movement is longer than 10 characters — a statline cell holds a "
        "short value like 4, 3+ or S."
    )
    return [
        replace(cell, value="five inches or so") if cell.short_name == "M" else cell
        for cell in editable_statline(errors={"M": refusal})
    ]


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
        # An id, because the card component reads it as "this depicts a stored
        # model" and only then draws the tab strip. Never a link target here —
        # the gallery passes hrefs of its own or none.
        id="vesna-krail",
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
                        # No leading dash in the name: the card draws its own
                        # mark for a named profile, so one stored here would
                        # print twice — and a name that is only a dash reads as
                        # a profile with no name at all, which means the weapon.
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
        # here even though the fighter has it: it was chosen for the Leader's
        # skill choice, and the builder draws a chosen node as that choice's
        # row rather than as a loose skill as well.
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
                kind_label="Gang Legacy",
                chosen=None,
                # A real card's slot carries the address of its own picker.
                # "#" stands in because the gallery has no gang behind it;
                # what matters for the card is that the prompt is a control.
                href="#",
                provenance=Provenance(
                    source="Specialist", source_kind="subtype", computed=True
                ),
            ),
            # A choice worked at a pick at a time, with room left: what it
            # holds is drawn, and Add stays beside it until it is full.
            ChoiceLine(
                kind_label="Lasting Injuries",
                chosen="Eye Injury, Out Cold",
                is_full=False,
                takes_several=True,
                href="#",
                provenance=Provenance(
                    source="Ganger", source_kind="profile", computed=True
                ),
            ),
        ],
        # A question asking for a skill, kept apart because the card draws it
        # in the Skills row rather than as a row of its own. Only open ones are
        # ever here: once chosen for, it would be a skill above.
        skill_choices=[
            ChoiceLine(
                kind_label="Primary skill",
                chosen=None,
                href="#",
                provenance=Provenance(
                    source="Leader", source_kind="subtype", computed=True
                ),
            ),
        ],
        # This fighter has a grid, so there is a screen of what she may select
        # and the Skills row carries the way to it. A card with no grid — and
        # every card on a print sheet — leaves this empty and draws nothing.
        skills_href="#",
        # A Wyrd's powers, which are not skills. Drawn apart on the card
        # because the rules treat them apart, even though they are chosen the
        # same way — see ModelCard.powers.
        powers=[
            _printed("Assail")[0],
            _granted("Mind Lock", "Wyrd", "subtype"),
        ],
        # Where this fighter can buy from. Access to buy, not things owned, which
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
        # The running numbers, as every card but one draws them: settled
        # values with nothing to click. XP keeps no line here — it has a
        # cell in the statline with its target beside it, and the line
        # exists only to be the control. model_card_editable() is the
        # card that carries the addresses.
        counters=[
            CounterLine(name="XP", value=61, assignment_id="xp", is_xp=True),
            CounterLine(name="Kill Count", value=3, assignment_id="kills"),
            # At zero, so the editable card shows that the minus is not
            # drawn: the value floors there and the control would offer
            # nothing.
            CounterLine(name="Glitch Count", value=0, assignment_id="glitch"),
        ],
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

#: A second set of options, for the profiles that have one.
#:
#: Option groups are the answer to combinatorial blow-up: twelve authored sets
#: where flat combinations needed forty. "Choose one" is a radio, "choose any"
#: is checkboxes — and the hire view shows one card per option against an
#: otherwise-default selection, never one card per combination.
#:
#: A set carries no label here because the structure carries none: what the
#: content calls one is written for authors, and a player reads the options.
_OPTION_GROUPS = {
    "Gang Queen": [
        ("any", [("photo-goggles", 35), ("bio-booster", 35)]),
    ],
    "Khimerix": [
        ("one", [("scaly hide", 0), ("caustic bite", 15), ("wings", 30)]),
    ],
}


def extra_groups(profile_name, subtype, base_price):
    """The further sets a profile offers beyond its plain options.

    Every option carries a card, as main builds them: that option against an
    otherwise-default selection, never one card per combination. So a price here
    is the base plus this one surcharge, and never a running total across sets.
    """
    return [
        HireGroup(
            choose=choose,
            options=[
                HireOption(
                    name=option_name,
                    price=surcharge,
                    total_price=base_price + surcharge,
                    # Nothing in a named group is the default unless the set is
                    # a one-of: "choose any" starts with none taken.
                    is_default=(choose == "one" and number == 0),
                    card=_hire_card(
                        profile_name, subtype, base_price + surcharge, 1 + number
                    ),
                )
                for number, (option_name, surcharge) in enumerate(options)
            ],
        )
        for choose, options in _OPTION_GROUPS.get(profile_name, [])
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
        # A preview depicts nobody stored, which is what an empty id
        # says — and what keeps the tab strip off it, here as on the
        # real hire list.
        id="",
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

    Mirrors what n26.hire.build_hire_list plus n26.hire.section_hire_list would
    return, built by hand because a gallery renders on an empty database. The
    sections, entries and options are the real structures holding real
    ModelCards, so the components are typed against what the server sends.
    """
    sections = []
    for position, (section_name, category_name, profiles) in enumerate(_GANG_LIST):
        if not sections or sections[-1].name != section_name:
            sections.append(HireSection(name=section_name))
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
                    groups=[HireGroup(choose="one", options=options)]
                    + extra_groups(name, subtype, price),
                )
            )
        sections[-1].categories.append(
            HireCategory(name=category_name, entries=entries)
        )
    return sections


def hire_entry(value):
    """The sample entry a click names, looked up by what the rows submit.

    The shell's rows submit their slugified name, so clicking Hire on one
    of three hundred can be answered with that one's dialog rather than a
    fixed example that would name the wrong fighter.
    """
    if not value:
        return None
    for section in hire_list():
        for entry in section.all_entries():
            if slugify(entry.name) == value:
                return entry
    return None


def hire_context():
    """What the hire view needs: the sections, and the ends of its one slider."""
    sections = hire_list()
    entries = [entry for section in sections for entry in section.all_entries()]
    categories = [
        category.name for section in sections for category in section.categories
    ]
    return {
        "hire_list": sections,
        "hire_categories": categories,
        "hire_sections": [section.name for section in sections],
        "hire_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "hire_price_floor": min(entry.base_price for entry in entries),
        "hire_price_ceiling": max(entry.base_price for entry in entries),
        # What a click hands the name dialog: the row's answer, already
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
    # Granted AND rated: the one shape where a price is drawn inside the
    # tooltip's trigger, beside the dotted-underlined name. The gallery must
    # hold a specimen or that arm of assignable-lines is drawn nowhere.
    StashLine(
        name="Blindsnake pouch",
        rating=60,
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


#: The gang's open questions. Each carries the address of its own picker —
#: "#" here, because the gallery has no gang behind it, and what the strip is
#: showing is that a slot is a control whether or not a choice has been made.
#:
#: The third has no address at all: a card built from a profile's default
#: equipment has real offers and no stored rows to choose against, so it
#: draws as a fact rather than as a button that goes nowhere.
CHOICES = [
    ChoiceLine(kind_label="Skill trees", chosen="Ferocity, Brawn, Cunning", href="#"),
    # Unresolved is information, not an error: n26.render is explicit that
    # a renderer informs and does not police.
    ChoiceLine(kind_label="Territory", chosen=None, href="#"),
    ChoiceLine(kind_label="Alliance", chosen=None),
]


def gang_sheet():
    """One gang, with enough going on to exercise the sheet.

    The awkward cases on purpose: a choice holding three things — the "list inside
    one control" the detail list exists for — an unresolved choice, a choice with
    nowhere to send anyone, counters, and a stash holding something granted rather
    than bought.
    """
    return GangSheet(
        name="The Ashen Choir",
        gang_type="Escher (HoB)",
        rating=360,
        credits=1037,
        wealth=1397,
        # Mid-trip: an allowance was taken to a post and some of it spent.
        # Both, or the strip reads the figure as unset and draws an em dash.
        visiting_trading_post=True,
        trade_points_left=3,
        colour="violet",
        rows=[
            AssignableLine(name="Founded in Cycle 3"),
            AssignableLine(name="Escher house list"),
        ],
        # One assigned to the gang directly and one that arrived with the
        # founding, whose provenance names the gang type that brought it.
        rules=[
            AssignableLine(name="Chem Dealers"),
            AssignableLine(
                name="Toxin Trade",
                provenance=Provenance(source="Escher", source_kind="gang type"),
            ),
        ],
        choices=CHOICES,
        counters=[_reading("Reputation", 7), _reading("Meat", 3)],
        stash=STASH,
        stash_rating=115,
        models=[model_card()],
    )


#: What a player writes on a card, as opposed to what the rules put there.
#: Editor markup, as the rich text editor stores it; the card sanitises it on
#: the way out, so the sample walks the same path a saved note does.
CARD_NOTES = (
    "<p>Base needs redoing after the sump run — the flock came off. "
    "Owes Kaine a favour from the Ash Wastes job.</p>"
)
CARD_LORE = (
    "<p>Came up through the Choir's third dome and never lost the accent. "
    "Took the Matriarch's needle pistol off a body nobody has claimed, which is "
    "the only reason anyone remembers her name.</p>"
)


#: A stand-in photograph, drawn rather than shipped: the gallery keeps no
#: image files, and a data URI exercises the same <img> path a stored
#: upload's URL does.
CARD_IMAGE = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 250'%3E"
    "%3Crect width='200' height='250' fill='%23433a52'/%3E"
    "%3Ccircle cx='100' cy='95' r='45' fill='%23d8cde8'/%3E"
    "%3Cpath d='M30 250c0-50 31-80 70-80s70 30 70 80z' fill='%23d8cde8'/%3E"
    "%3C/svg%3E"
)


def model_card_written():
    """The sample card with its picture and its Lore and Notes tabs filled."""
    return replace(model_card(), notes=CARD_NOTES, lore=CARD_LORE, image_url=CARD_IMAGE)


def model_card_editable():
    """The sample card as the model's own page draws it: its counters
    carry addresses, so the lines grow their controls and XP joins them,
    and kit it holds offers the same Sell and more-menu the listing does.

    A card of its own rather than a flag on the base one, because the
    base card is what the gang sheet, the hire previews and the print
    specimens are all built from, and none of those may offer to change
    a number or part with a weapon. The addresses go nowhere, as every
    href in this gallery does.
    """
    from n26.core.listing import DANGER, LINK, SECONDARY, Action

    sell = Action("Sell", LINK, "#", DANGER)
    more = (
        Action("Reassign", LINK, "#", SECONDARY),
        Action("Refund", LINK, "#", SECONDARY),
        Action("Delete", LINK, "#", SECONDARY),
    )
    part_more = (
        Action("Refund", LINK, "#", SECONDARY),
        Action("Remove", LINK, "#", SECONDARY),
    )
    accessorise = Action("Add accessory", LINK, "#", SECONDARY)

    card = replace(model_card())
    card.counters = [replace(line, href="#") for line in card.counters]
    card.equipment = [replace(line, sell=sell, more=more) for line in card.equipment]
    for weapon in card.weapons:
        weapon.sell = sell
        weapon.more = more
        weapon.accessorise = accessorise
        weapon.accessories = [
            replace(line, sell=sell, more=part_more) for line in weapon.accessories
        ]
        for profile in weapon.named_profiles:
            profile.sell = sell
            profile.more = part_more
    return card


def gang_sheet_context():
    """What the gang sheet view needs."""
    from n26.core.models import Action
    from n26.core.render import RosterGroup, RosterLine, RosterSummary

    sheet = gang_sheet()
    members = [
        ("Vesna Krail", "Escher Gang Queen", 135),
        ("Sister Yara", "Death Maiden", 105),
        ("Ilse Vandt", "Matriarch", 95),
        ("Vex", "Ganger", 55),
        ("Sull", "Ganger", 55),
    ]
    # The sheet's own tally, over the cards this demo actually draws rather
    # than the fuller one the tally component is shown with on its own page:
    # a header counting twelve models above a grid of five is the kind of
    # thing a reader takes for a bug in the component.
    sheet.summary = RosterSummary(
        groups=[
            RosterGroup(profile="Escher Gang Queen", category="Leader", count=1),
            RosterGroup(profile="Death Maiden", category="Champion", count=1),
            RosterGroup(profile="Matriarch", category="Champion", count=1),
            RosterGroup(profile="Ganger", category="Ganger", count=2),
        ],
        models=[RosterLine(name=name, rating=rating) for name, _, rating in members],
        count=len(members),
        rating=sum(rating for _, _, rating in members),
    )
    visit_facts = (
        Fact("Available", "4", sub="Leader, Champion × 2"),
        Fact("Spent", "1"),
        Fact("Remaining", "3", ruled=True, strong=True),
    )
    return {
        "gang": sheet,
        # The three states an action card has: a visit, which has figures to
        # show; the founding, which has none; and one nobody has started,
        # which is the control on its own. Built by the real function off
        # the real kinds, so a title or a label changed there changes here.
        "sample_action_visit": card_for(
            Action.Kind.TRADING_POST_VISIT,
            "#",
            is_open=True,
            help=VISIT_HELP,
            facts=visit_facts,
        ),
        "sample_action_founding": card_for(
            Action.Kind.FOUNDING, "#", is_open=True, help=FOUNDING_HELP
        ),
        "sample_action_closed": card_for(Action.Kind.FOUNDING, "#", is_open=False),
        # Two tallies: the Visit Trading Post card's, and the one the
        # overspend confirmation draws under it. The second carries two
        # totals, which is what the component's per-row emphasis is for.
        "tally_facts": visit_facts,
        "tally_overspend": (
            Fact("Available", "4"),
            Fact("Spent", "3"),
            Fact("Remaining", "1", ruled=True, strong=True),
            Fact("This purchase", "3"),
            Fact("Remaining after", "-2", ruled=True, strong=True),
        ),
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
            for name, profile, rating in members
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
            "Gang legacies, chained picks, and the ratio notes that "
            "come with them. Said, never enforced."
        ),
    },
]


# ------------------------------------------------------------- what is owned

# An equip row for something the fighter already has, and the three
# confirmations behind it. Real OwnedThings put through the real conversion,
# because the components end up typed against what a catalogue produces — a
# rename upstream should fail at import rather than at a glance, and the acts
# a copy offers should appear here the day the structure grows one.
#
# Every address is "#". These are confirmations over the page the reader is
# on, and a gallery page is not one — a link that navigated away would be a
# demo you cannot look at twice.


@dataclass(frozen=True)
class _Roster:
    """Stands in for a Miniature: someone the move dialog can offer."""

    pk: str
    name: str


def carried():
    """What the fighter buying from the sample list is already holding.

    Keyed the way :func:`n26.core.owned.owned_things` keys it — by the
    content row, not by the copy — so ``build_catalogue`` joins it to the
    catalogue exactly as the application does. The shell's owned rows are
    owned rows because the real function said so, and not because a
    template drew them differently.

    Two Stub guns, a Meltagun with a paid round, and a mount bought with
    one option from each of its two sets: a count above one, a part
    under a copy, a copy naming what it was bought with, and everything
    else on the list untouched. Those are the states a row has, and one
    sample answers for every surface that asks what this fighter is
    carrying.
    """
    from n26.core.owned import OwnedPart, OwnedThing, thing_key

    def copy(name, rating, index=0, parts=(), chosen=(), fit_href=""):
        stock = _stock(name)
        pk = f"{stock.pk}-{index}"
        return thing_key(stock), OwnedThing(
            id=pk,
            key=thing_key(stock),
            name=name,
            rating=rating,
            parts=parts,
            sell_href="#",
            reassign_href="#",
            refund_href="#",
            remove_href="#",
            fit_href=fit_href,
            chosen=chosen,
        )

    round_ = OwnedPart(
        id="melta-round",
        key=thing_key(_stock("Melta round")),
        name="Melta round",
        rating=20,
        sell_href="#",
        refund_href="#",
        remove_href="#",
    )
    held = {}
    for key, thing in (
        copy("Meltagun", 135, parts=(round_,)),
        copy("Stub gun", 5, index=0),
        copy("Stub gun", 5, index=1),
        # A mount bought with one option taken from each of its two sets
        # — the options themselves, never the author's name for the set
        # they came from. The list's other mount is left unbought, so one
        # of the two draws its controls and the other draws its picks.
        copy(
            "Ridge-runner",
            125,
            chosen=("Ridge-runner harpoon", "Ridge-runner spikes"),
        ),
        # An accessory nothing is holding yet, so its row is the one that
        # offers to bolt it onto one of the guns above.
        copy("Infra-sight", 40, fit_href="#"),
    ):
        held.setdefault(key, []).append(thing)
    return held


def _stock(name):
    """The catalogue row of that name, for keying what is held against it."""
    for line in trading_post().all_lines():
        if line.name == name:
            return line.thing
        for part in line.parts:
            if part.name == name:
                return part.thing
    raise KeyError(name)


def owned_context():
    """What a fighter is carrying, and the things that can happen to it."""
    from n26.core.listing import copy_row, pick_groups

    named = {"cancel_url": "#", "action": "#", "list": "", "name": "Meltagun"}
    return {
        "owned_copies": [
            copy_row(thing) for copies in carried().values() for thing in copies
        ],
        # The gun and its round together, which is what a sale of the gun
        # is priced on: what goes with it counts towards what it fetches.
        "owned_sell_dialog": {
            **named,
            "kind": "sell",
            "title": "Sell Meltagun?",
            "rating": 155,
            "proceeds": 78,
            "sum": "Half of 155¢, rounded up — 78¢.",
            "submit_label": "Sell",
            "submit_variant": "danger",
        },
        "owned_move_dialog": {
            **named,
            "kind": "reassign",
            "title": "Move Meltagun",
            "models": [_Roster("nell", "Nell"), _Roster("vex", "Vex")],
            "submit_label": "Move",
            "submit_variant": "primary",
        },
        # The same gun, priced the other way: a sale returns half of the
        # 155¢ it is worth, a refund returns the 120¢ somebody actually
        # handed over. The two figures differ here on purpose — this gun
        # was haggled down, which is the case that makes the distinction
        # visible at all.
        # The guns the card is carrying, which is the whole of what a
        # fitting may name — and the same question with none to offer,
        # since a card carrying no gun is the state that draws no submit.
        "owned_fit_dialog": {
            **named,
            "kind": "fit",
            "name": "Infra-sight",
            "title": "Fit Infra-sight to a weapon",
            "weapons": [
                {"pk": "meltagun", "label": "Meltagun"},
                {"pk": "stub-gun", "label": "Stub gun"},
            ],
            "submit_label": "Fit",
            "submit_variant": "primary",
        },
        "owned_detach_dialog": {
            **named,
            "kind": "detach",
            "name": "Telescopic sight",
            "title": "Take Telescopic sight off Meltagun?",
            "submit_label": "Detach",
            "submit_variant": "primary",
        },
        "owned_fit_nothing_dialog": {
            **named,
            "kind": "fit",
            "name": "Infra-sight",
            "title": "Fit Infra-sight to a weapon",
            "weapons": [],
            "submit_label": "",
            "submit_variant": "primary",
        },
        "owned_refund_dialog": {
            **named,
            "kind": "refund",
            "title": "Refund Meltagun?",
            "proceeds": 120,
            "sum": "120¢ comes back — what was paid for it, not what it is worth.",
            "submit_label": "Refund",
            "submit_variant": "danger",
        },
        # The same sale, of a gun with something bolted to it. Two prices,
        # because keeping the sight sells the gun alone: 78¢ against the
        # 91¢ the pair would fetch.
        "owned_sell_kitted_dialog": {
            **named,
            "kind": "sell",
            "title": "Sell Meltagun?",
            "rating": 155,
            "proceeds": 78,
            "sum": "Half of 155¢, rounded up — 78¢.",
            "keepable": "Telescopic sight",
            "keep_label": "Stash the accessory",
            "keep_detail": "Keep to refit later. 78¢ for the gun alone.",
            "sell_all_label": "Sell the accessory too",
            "sell_all_detail": "Everything goes together. 91¢.",
            "submit_label": "Sell",
            "submit_variant": "danger",
        },
        # The mount the sample fighter owns, reopened on its alternatives.
        # Built by the real loader from the real offer, so what starts
        # picked here is decided the way the application decides it: the
        # harpoon and the spikes, which is what the copy was bought with.
        "owned_rechoose_dialog": {
            **named,
            "kind": "rechoose",
            "name": "Ridge-runner",
            "title": "Change Ridge-runner's options",
            "choices": pick_groups(
                _offered_choices("Ridge-runner"),
                "library.wargear:ridge-runner",
                taken={"Ridge-runner harpoon", "Ridge-runner spikes"},
            ),
            "submit_label": "Save options",
            "submit_variant": "success",
        },
        "owned_accessorise_dialog": {
            **named,
            "kind": "accessorise",
            "title": "Add an accessory to Meltagun",
            "accessories": [
                {"pk": "1", "name": "Telescopic sight", "price": 25},
                {"pk": "2", "name": "Gun stabiliser", "price": 30},
            ],
            "submit_label": "Add accessory",
            "submit_variant": "success",
        },
        "owned_remove_dialog": {
            **named,
            "kind": "remove",
            "title": "Delete Meltagun?",
            "submit_label": "Delete",
            "submit_variant": "danger",
        },
    }


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
