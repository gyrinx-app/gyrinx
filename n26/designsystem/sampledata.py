"""Fixed sample data for composition demos. Use production display dataclasses without
querying content so the gallery renders consistently on an empty database.
"""

from dataclasses import dataclass, replace
from datetime import timedelta

from django.utils import timezone
from django.utils.text import slugify

from n26.core.action_flow import ActionPanel, ActionUseLink
from n26.core.activities import (
    FOUNDING_ABOUT,
    FOUNDING_HELP,
    VISIT_HELP,
    ActivitiesSquare,
    VisitLine,
    open_card,
    steps_waiting,
)
from n26.core.browse import (
    CategoryGroup,
    CollectionView,
    OfferedGroup,
    OfferedOption,
    PricedLine,
    SectionGroup,
)
from n26.core.confirm import Fact
from n26.core.flow import FlowStep, PaymentFigures
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
    AssetTypeColumn,
    AssignableLine,
    CampaignAssetEntry,
    CampaignAssetLine,
    CampaignAssetTable,
    CampaignBlock,
    CampaignGangLine,
    CampaignSheet,
    ChoiceLine,
    ChoiceOffer,
    Choosable,
    ChoosableGroup,
    CounterLine,
    EffectLine,
    GangSheet,
    GearGroup,
    HeldTable,
    ModelCard,
    Provenance,
    RollResult,
    RollTable,
    StartingRoll,
    StashLine,
    StatCell,
    Statline,
    WeaponLine,
    WeaponProfileLine,
)
from n26.core.status import Status, label_for
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

STATUSES = [
    {"value": "active", "label": "Active"},
    {"value": "campaign", "label": "In a campaign"},
    {"value": "retired", "label": "Retired"},
    {"value": "draft", "label": "Draft"},
]


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


# Sample catalogue data contains names, prices and availability only; rules text is
# excluded. Track owned equipment separately because ownership is gang state, while
# PricedLine describes an offer.
IN_STASH = {"Autopistol", "Stub gun", "Shotgun", "Mesh armour", "Photo-goggles"}


@dataclass(frozen=True)
class _Category:
    """Minimal library category with its section and position. The catalogue compares
    category objects because names are unique only within their section, then sorts by
    position.
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
    """Minimal library assignable with category and content identity. Catalogue field names
    require a unique combination of model label and primary key.
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


# Catalogue entries are section, category and (name, credits, Trade Points, exclusive)
# tuples. Exclusive entries exercise equipment-list-only availability.
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


#: Static use notes match with_use_notes output without requiring a fighter or database.
USE_NOTES = {
    "Master-crafted toolkit": (
        Note(text="usable by Specialist only", about=None, level=WARNING),
    ),
    "Thunder hammer": (
        Note(text="takes the space of two weapons", about=None, level=INFO),
    ),
}

#: Paid parts are keyed by their parent item. Include an unowned Boltgun and an owned
#: Meltagun to exercise part controls in both catalogue states.
PAID_PARTS = {
    "Boltgun": [("Kraken round", 15, 10)],
    "Meltagun": [("Melta round", 20, 11)],
}

#: Option groups are keyed by item and contain selection limits plus surcharge
#: alternatives. Include single-choice and optional groups; surcharges are relative to
#: the base price.
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
    #: The owned Ridge-runner shows selected options; the unowned Grav-cutter
    #: shows purchase controls.
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
    """The identity and price of an option's set, without database access."""

    pk: str
    price: int


def _offered_choices(name):
    """Build option groups for a sample catalogue entry."""
    return tuple(
        OfferedGroup(
            choose=choose,
            options=tuple(
                OfferedOption(
                    name=option,
                    surcharge=surcharge,
                    is_default=(choose == "one" and position == 0),
                    default_set=_Set(option, surcharge),
                )
                for position, (option, surcharge) in enumerate(options)
            ),
        )
        for choose, options in OFFERED.get(name, ())
    )


def _part_lines(name, category):
    """Build priced parts for a sample catalogue entry."""
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
    """Build a CollectionView using the production browse dataclasses. Enable both Trade
    Point display and charging on each line to model a Trading Post visit.
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
                        # Inform rather than police. Include a use note without removing
                        # the offered equipment.
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
    """Collection name and key required by the equipment tab builder."""

    def __init__(self, name, pk):
        self.name = name
        self.pk = pk

    def __str__(self):
        return self.name


def _shop_tabs():
    """Build equipment tabs with long collection names to exercise narrow layouts."""
    from n26.core.views.equip import collection_tabs

    collections = [
        _Collection("Ash Waste Nomads Equipment List", "nomads"),
        _Collection("Dust Falls Trade Agreement Equipment List", "dust-falls"),
        _Collection("Trading Post", "post"),
    ]
    return collection_tabs(collections, collections[0])


def trading_post_context():
    """Prepare the sample catalogue and filter ranges. Derive slider bounds from the data
    so an unfiltered range includes every priced entry.
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
        # Use the production catalogue builder with sample ownership data so shared
        # templates receive the real display structure.
        "trading_post_catalogue": build_catalogue(view, carried()),
        # Compute nested first-section state here because Cotton attributes cannot
        # evaluate a combined boolean expression.
        "trading_post_section_rows": [
            {"section": section, "first": index == 0}
            for index, section in enumerate(view.sections)
        ],
        "trading_post_categories": categories,
        "trading_post_sections": [section.name for section in view.sections],
        # Use category names consistently as menu values and catalogue filter keys.
        "trading_post_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "trading_post_in_stash": IN_STASH,
        # Use the production purchase limit in the sample price inputs.
        "trading_post_price_cap": PRICE_CEILING,
        "trading_post_tabs": _shop_tabs(),
        "trading_post_price_floor": min(line.credits for line in lines),
        "trading_post_price_ceiling": max(line.credits for line in lines),
        # Exclude exclusive availability from numeric slider bounds.
        "trading_post_tp_ceiling": max(
            line.trade_points for line in lines if not line.is_exclusive
        ),
    }


#: Uneven supplier sections exercise both long tab strips and large groups of entries.
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
    """Build a deterministic catalogue with uneven section sizes for performance and
    overflow checks.
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


#: Share the sample owner name across dashboard greetings and gang breadcrumbs.
OWNER = "tom"


@dataclass(frozen=True)
class SampleUser:
    """Username-only stand-in for gallery account displays. With no profile, the platform
    badge lookup returns no badge.
    """

    username: str


def nav_context():
    """Build fixed gang and model switchers using production navigation structures. Give
    adjacent switchers distinct accessible names.
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
        # Provide the model switcher and a numeric unread count; the string "0" would be
        # truthy.
        "sample_unread": 3,
        "sample_account_menu": _sample_account_menu(),
        "sample_account_menu_unread": _sample_account_menu(unread=3, theme=False),
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
    """Provide the pk and name read by model headers and edit previews, with no database
    record.
    """
    from types import SimpleNamespace

    return SimpleNamespace(pk="sample", name="Vesna Krail")


def roster_summary():
    """Build a RosterSummary with repeated profiles and pets to exercise grouped counts."""
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


def _sample_account_menu(*, unread=0, theme=True):
    """Sample account-menu props matching n26.core.templatetags.account_menu."""
    from n26.core.templatetags.theme_choice import theme_choice_props

    unread_noun = "unread notification" if unread == 1 else "unread notifications"
    items = [
        {"type": "person"},
        {"type": "separator"},
        {"type": "link", "label": "Your account", "href": "#"},
        {
            "type": "link",
            "label": "Notifications",
            "href": "#",
            "count": unread,
            "countLabel": unread_noun,
        },
    ]
    if theme:
        items.append(
            {
                "type": "group",
                "label": "Theme",
                "items": [{"type": "theme", **theme_choice_props("n26-theme")}],
            }
        )
    items += [
        {"type": "separator"},
        {"type": "link", "label": "Sign out", "href": "#", "tone": "danger"},
    ]
    return {
        "label": "Open account menu",
        "unread": unread,
        "unreadText": f"{unread} {unread_noun}",
        "person": {"name": "tom", "badge": None},
        "badges": {},
        "items": items,
    }


def context():
    from n26.core.checkbox_card import CheckboxCardItem
    from n26.core.effects import stacked_name_items
    from n26.core.rating import RatingContribution, RatingReceipt

    return {
        "name_list_items": stacked_name_items(
            ["Ruins, North", "Shop", "Shop", "Settlement"]
        ),
        "checkbox_card_weapons": (
            CheckboxCardItem("demo-weapons", "lasgun", "Lasgun", True, "15¢"),
            CheckboxCardItem(
                "demo-weapons", "stiletto", "Stiletto knife", False, "20¢"
            ),
        ),
        "rating_receipt_demo": RatingReceipt(
            100,
            30,
            (
                RatingContribution("Weapons", 25),
                RatingContribution("Gear", 20),
                RatingContribution("Advancements", 10),
            ),
            185,
        ),
        "augmentation_flow_steps": (
            FlowStep("Choice", complete=True),
            FlowStep("Item and tier", complete=True),
            FlowStep("Review", current=True),
            FlowStep("Completed"),
        ),
        "advancement_flow_steps": (
            FlowStep("Choice", complete=True),
            FlowStep("Roll", complete=True),
            FlowStep("Advancement", current=True),
            FlowStep("Skill"),
            FlowStep("Review"),
            FlowStep("Completed"),
        ),
        "skipped_flow_steps": (
            FlowStep("Choice", complete=True),
            FlowStep("Roll", skipped=True),
            FlowStep("Promotion", complete=True),
            FlowStep("Skill", skipped=True),
            FlowStep("Review", current=True),
            FlowStep("Completed"),
        ),
        "campaign_counter_adjustable": CounterLine(
            name="Meat", value=5, tallied=2, href="#", back="#", adjust_href="#"
        ),
        "counter_payment_figures": PaymentFigures("Kill Count", "8", "4", "4"),
        "credit_payment_figures": PaymentFigures("", "430¢", "100¢", "330¢"),
        "sample_action_panels": (
            ActionPanel(
                action_id="suit-evolution",
                name="Suit Evolution",
                timing="post-battle action",
                prices=(PaymentFigures("Kill Count", "8", "4", "4"),),
                flagged=True,
                drafts=[
                    ActionUseLink(
                        "suit-evolution-draft",
                        "Resume Suit Evolution flow",
                        "#resume-suit-evolution",
                    )
                ],
                completed=[
                    ActionUseLink(
                        "suit-evolution-result",
                        "Hunting Rig Augmentation",
                        "#suit-evolution-result",
                        "Hunting rig: Tier 1. Improve S by 1",
                        timezone.now() - timedelta(minutes=12),
                    )
                ],
            ),
            ActionPanel(
                action_id="advancement",
                name="Advancement",
                timing="when an XP threshold is reached",
                allowance_id="advancement-allowance",
                available_uses=1,
                start_href="#start-advancement",
                flagged=True,
            ),
        ),
        "houses": HOUSES,
        "gang_owner": OWNER,
        # Use a fixed second user so previews remain the same for every viewer.
        "sample_user": SampleUser("kesh"),
        "sortable_table": {
            "label": "Example territory inventory",
            "columns": [
                {
                    "token": column,
                    "label": label,
                    "className": "text-right" if column == "income" else "",
                }
                for column, label in (
                    ("name", "Territory"),
                    ("income", "Income"),
                    ("holder", "Held by"),
                )
            ],
            "rows": [
                {
                    "id": "ruins-one",
                    "values": {
                        "name": "Old Ruins",
                        "income": 20,
                        "holder": "Unclaimed",
                    },
                    "groups": {"status": "Unclaimed", "holder": "Unclaimed"},
                },
                {
                    "id": "ruins-two",
                    "values": {
                        "name": "Old Ruins",
                        "income": 30,
                        "holder": "Cinder Crew",
                    },
                    "groups": {"status": "Held", "holder": "Cinder Crew"},
                },
                {
                    "id": "workshop",
                    "values": {
                        "name": "Workshop",
                        "income": 25,
                        "holder": "Rust Kings",
                    },
                    "groups": {"status": "Held", "holder": "Rust Kings"},
                },
            ],
            "groupOptions": [
                {"token": column, "label": label}
                for column, label in (
                    ("status", "Held or unclaimed"),
                    ("holder", "Holding gang"),
                )
            ],
            "sort": "name",
            "group": "status",
        },
        "campaign_sheet": campaign_sheet(),
        "sample_miniature": sample_miniature(),
        "sample_roster_summary": roster_summary(),
        # Supply artwork as the stored SVG string consumed by the sanitising component.
        "sample_gang_icon": SAMPLE_GANG_ICON,
        # Use a data URI so image previews need no upload storage.
        "sample_picture": CARD_IMAGE,
        # Use the server image constants for crop settings so component previews match
        # uploads.
        "sample_picture_shape": PORTRAIT,
        "sample_picture_max": MAX_PX,
        "choice_offer": choice_offer(),
        "empty_choice_offer": ChoiceOffer(label="Primary skill"),
        "arrival_screen": arrival_screen(),
        # Include partially filled and full multi-pick offers to exercise different
        # actions.
        "choice_picks_offer": choice_picks_offer(),
        "full_choice_picks_offer": choice_picks_offer(full=True),
        # Include resolved, empty and applied roll states.
        "roll_table": RollTable(dice_label="D66", lowest=11, highest=66),
        "roll_landed": RollResult(
            key="roll-1",
            total=24,
            dice_label="D66",
            faces=(2, 4),
            landed=("Out Cold",),
            add=Choosable(key="library.pickable:7", name="Out Cold", control="choose"),
        ),
        "roll_entered_threshold": RollResult(
            key="roll-2",
            total=8,
            dice_label="2D6",
            landed=("Toughness", "Leadership"),
            entered=True,
            threshold=True,
        ),
        "roll_spent": RollResult(
            key="roll-3",
            total=51,
            dice_label="D66",
            faces=(5, 1),
            landed=("Eye Injury",),
            applied="Eye Injury",
        ),
        "tick_list_offer": tick_list_offer(),
        "pick_list_held": pick_list_held(),
        "pick_list_addable": pick_list_addable(),
        "pick_list_grouped": pick_list_grouped(),
        "editable_statline": editable_statline(),
        # Include an empty profile statline and a rejected value to exercise editor-only
        # states.
        "blank_editable_statline": editable_statline(filled=False),
        "refused_editable_statline": refused_statline(),
        # An empty owner override inherits the model's value.
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
    """Minimal sentence object matching the fields read by the authoring about column."""

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
    """Build sample authoring descriptions and their source links."""
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
    """Build grouped skill choices with option details and a choice already taken for
    another slot.
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


def _gang_offer(label, options, chosen=None, first_key=1):
    """Build a gang-hosted choice offer for the follow-up screen."""
    return ChoiceOffer(
        label=label,
        chosen=chosen,
        groups=[
            ChoosableGroup(
                name="",
                options=[
                    Choosable(
                        key=f"library.pickable:{first_key + n}",
                        name=name,
                        is_current=name == chosen,
                    )
                    for n, name in enumerate(options)
                ],
            )
        ],
    )


def arrival_screen():
    """Build compulsory, completed and optional gang choices for the screen after founding.
    Model-specific choices are shown after hiring instead.
    """
    from n26.core.render import ArrivalBlock, ArrivalQuestion, ArrivalScreen

    # Use a local placeholder target because the gallery creates no gang.
    back = "#"
    bearer = "The Forgotten"
    return ArrivalScreen(
        blocks=(
            ArrivalBlock(
                heading="Choose a gang archetype",
                description=(
                    "A gang archetype changes who you can hire, what "
                    "equipment you can buy, and which gang rules you "
                    "have.\n\nPick one before hiring anybody."
                ),
                questions=(
                    ArrivalQuestion(
                        key="gang:1:1",
                        under="1",
                        label="Gang archetype",
                        bearer=bearer,
                        chosen=None,
                        settled=False,
                        offer=_gang_offer(
                            "Gang archetype",
                            ("Chymist Cult", "Wyld Hunt"),
                            first_key=1,
                        ),
                    ),
                ),
            ),
            ArrivalBlock(
                heading="Name the corruption",
                description="A corrupted gang keeps its house list and adds its own.",
                questions=(
                    ArrivalQuestion(
                        key="gang:1:2",
                        under="2",
                        label="Variant",
                        bearer=bearer,
                        chosen="Chaos Corrupted",
                        settled=True,
                        offer=_gang_offer(
                            "Variant",
                            (
                                "Chaos Corrupted",
                                "Genestealer Cult Corrupted",
                                "Malstrain Corrupted",
                            ),
                            chosen="Chaos Corrupted",
                            first_key=3,
                        ),
                    ),
                ),
            ),
            ArrivalBlock(
                heading="Choose a Chaos god",
                description="Can be chosen later, from the gang sheet.",
                questions=(
                    ArrivalQuestion(
                        key="gang:1:3",
                        under="3",
                        label="Chaos God",
                        bearer=bearer,
                        chosen=None,
                        settled=False,
                        offer=_gang_offer(
                            "Chaos God",
                            (
                                "Architect of Fate",
                                "Blood God",
                                "Dark Prince",
                                "Plague Lord",
                            ),
                            first_key=6,
                        ),
                    ),
                ),
                skippable=True,
            ),
        ),
        next_url=back,
    )


def choice_picks_offer(full=False):
    """Build a multi-pick choice with two selections. When full, omit unselected options so
    the demo shows removal without an add action.
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
    """Build owner-added, granted and purchased skills to exercise editable and fixed
    selections.
    """
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
    """Build skill groups with tier captions and a fixed granted selection."""
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
    """Build enough additional skills to exercise filtering in the picker."""
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
    """Build primary and secondary skill groups with selected and granted entries."""
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

# Use production render dataclasses so sample structures follow the components' actual
# input contracts without database access.


def _cell(short, full, value, **flags):
    return StatCell(short_name=short, full_name=full, value=value, **flags)


def _printed(*names):
    """Assignables that are simply on the card, with nothing to explain."""
    return [AssignableLine(name=name) for name in names]


def _granted(name, source, source_kind):
    """Build a computed assignable whose provenance identifies its grant source."""
    return AssignableLine(
        name=name,
        provenance=Provenance(source=source, source_kind=source_kind, computed=True),
    )


def _fighter_statline():
    """Build the sample fighter statline, including psychology highlighting and the group
    boundary at Leadership.
    """
    return Statline(
        cells=[
            _cell("M", "Movement", '5"'),
            _cell(
                "WS",
                "Weapon Skill",
                "2+",
                # Include the modifier source so the changed stat can explain its value.
                modified_by=[
                    Provenance(
                        source="Weapon Skill", source_kind="advancement", computed=True
                    )
                ],
                # Weapon Skill cannot improve beyond 2+; include its limit explanation.
                held_at="maximum",
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
    """Infer display-format placeholders from sample values. Production placeholders use
    the stat's stored display flags.
    """
    if value.endswith('"'):
        return '4"'
    if value.endswith("+"):
        return "3+"
    return "3"


def editable_statline(filled=True, errors=None):
    """Build editable cells from the display statline so the columns agree. errors
    identifies cells with validation errors.
    """
    from n26.core.render import EditableStatCell
    from n26.library.models import Stat

    return [
        EditableStatCell(
            short_name=cell.short_name,
            full_name=cell.full_name,
            # Derive input identifiers using the library's stat-name rule.
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
    """Build model stat overrides with the inherited value as each empty field's
    placeholder.
    """
    return [
        replace(cell, value="", placeholder=printed.value)
        for cell, printed in zip(
            editable_statline(filled=False), _fighter_statline().cells, strict=True
        )
    ]


def refused_statline():
    """Build a validation-error cell retaining the submitted value."""
    refusal = (
        "Movement is longer than 10 characters — a statline cell holds a "
        "short value like 4, 3+ or S."
    )
    return [
        replace(cell, value="five inches or so") if cell.short_name == "M" else cell
        for cell in editable_statline(errors={"M": refusal})
    ]


def _weapon_statline(rng_s, rng_l, acc_s, acc_l, strength, ap, damage, ammo):
    """Build a weapon statline with full names that disambiguate repeated S and L
    abbreviations.
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
    """Build a sample ModelCard with modified stats, paid weapon profiles, granted traits
    and unresolved choices.
    """
    return ModelCard(
        # An ID enables stored-model tabs. Gallery links supply their own targets.
        id="vesna-krail",
        # Keep the model's chosen name separate from its library profile name.
        name="Vesna Krail",
        profile_name="Escher Gang Queen",
        rating=135,
        profile_type="Fighter",
        subtypes=_printed("Leader"),
        statline=_fighter_statline(),
        weapons=[
            WeaponLine(
                name="Needle pistol",
                base_rating=30,
                profiles=[
                    WeaponProfileLine(
                        # An unnamed profile uses the weapon's name. A named profile
                        # with the same text would have a different meaning.
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
                        # The component adds its own marker for named profiles, so
                        # profile names contain no leading dash.
                        name="Hotshot las pack",
                        rating=10,
                        statline=_weapon_statline(
                            '8"', '24"', "+1", "-", "4", "-1", "1", "5+"
                        ),
                        # Mark Unstable as granted by a modifier so provenance explains
                        # its source.
                        traits=[
                            *_printed("Plentiful"),
                            _granted("Unstable", "Hotshot las pack", "profile"),
                        ],
                    ),
                ],
                # Accessory scope identifies the weapon to which this sight is attached.
                accessories=[AssignableLine(name="Telescopic sight")],
                # Display the weapon's augmentation choice beneath that weapon.
                choices=[
                    ChoiceLine(
                        kind_label="Augmentation",
                        chosen="Tier 2",
                        is_tier_ladder=True,
                        key="vesna-krail:lasgun:augmentation",
                        provenance=Provenance(
                            source="Lasgun", source_kind="weapon", computed=True
                        ),
                    )
                ],
            ),
            WeaponLine(
                # Two free named profiles must both remain separate from the weapon
                # heading; neither is its default unnamed profile.
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
        # List skills alphabetically with provenance. A skill selected for a choice
        # appears through that choice instead of being repeated independently.
        skills=[
            _granted("Gang Hierarchy", "Leader", "subtype"),
            _granted("Group Activation (2)", "Leader", "subtype"),
            _granted("Overseer", "Leader", "subtype"),
            *_printed("Spring Up"),
        ],
        equipment=[
            *_printed("Mesh armour (15¢)", "Photo-goggles (35¢)"),
            AssignableLine(
                name="Bio-booster (35¢)",
                choices=[
                    ChoiceLine(
                        kind_label="Augmentation",
                        chosen="Tier 1",
                        key="vesna-krail:bio-booster:augmentation",
                    )
                ],
            ),
            # Include a repeated equipment assignment to exercise the count suffix.
            AssignableLine(name="Stimm-slug (25¢)", count=2),
            # Include pet-granting equipment and identify the resulting pet, whose card
            # is model_card_pet().
            AssignableLine(name="Phyrr Cat (pet) (120¢)", brought_in=("Fang",)),
        ],
        # This equipment category uses a separate heading on the card.
        gear_groups=[
            GearGroup(
                name="Gene-smithing",
                lines=_printed("Iron flesh (30¢)"),
            )
        ],
        # Keep the unresolved variant separate from skills, whose resolved choices
        # appear in their own section.
        choices=[
            ChoiceLine(
                kind_label="Gang Legacy",
                chosen=None,
                # A nonempty placeholder URL renders the choice as a control without
                # requiring a stored gang.
                href="#",
                provenance=Provenance(
                    source="Specialist", source_kind="subtype", computed=True
                ),
            ),
            # A partially filled choice shows its current selections and an Add action.
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
            # A gang-level choice has no model-level edit URL, so display its value as
            # text.
            ChoiceLine(
                kind_label="Archetype",
                chosen="Brawler",
                is_full=True,
                provenance=Provenance(
                    source="the gang", source_kind="gang", computed=True
                ),
            ),
        ],
        # Unresolved skill choices appear within Skills. Resolved ones are displayed
        # through their selected skill.
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
        # Only cards with a selection URL offer the skill picker; print cards leave it
        # empty.
        skills_href="#",
        # Keep powers separate from skills, matching ModelCard.powers.
        powers=[
            _printed("Assail")[0],
            _granted("Mind Lock", "Wyrd", "subtype"),
        ],
        # Collections describe buying access and are displayed separately from owned
        # gear.
        collections=[
            _granted("House Escher Equipment List", "Escher", "profile"),
            *_printed("Trading Post"),
        ],
        # Display stored effects without executing them; happened controls whether
        # wording describes a completed effect or a preview.
        effects=[
            EffectLine(
                description="Adds a Cyber-mastiff to the gang",
                happened=False,
                provenance=Provenance(
                    source="Cyber-mastiff", source_kind="wargear", computed=True
                ),
            ),
        ],
        # This independently hired model has no granting owner; the pet variant supplies
        # one.
        owned_by=None,
        # Read-only cards omit adjustment URLs. XP appears in the statline; its separate
        # counter control is supplied by model_card_editable().
        counters=[
            CounterLine(
                name="XP", value=61, tallied=61, assignment_id="xp", is_xp=True
            ),
            CounterLine(name="Kill Count", value=3, tallied=3, assignment_id="kills"),
            # A zero stored value leaves nothing to subtract.
            CounterLine(name="Glitch Count", value=0, assignment_id="glitch"),
            # The displayed 2 comes entirely from a rule; the stored value available for
            # adjustment remains zero.
            CounterLine(name="Bounty", value=2, assignment_id="bounty"),
        ],
        xp=61,
        xp_target=79,
    )


# Hiring uses authored collection sections and categories, matching the other catalogue
# displays.


@dataclass(frozen=True)
class _Named:
    """Provide the name attribute read by HireEntry.profile_type."""

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


#: Sample entries contain section, category, price, subtype and option surcharges.
#: Invented values exercise profiles with different option counts.
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

#: Independent option groups use radios or checkboxes according to their selection limit.
#: Each option preview starts from defaults; group labels are author-facing and omitted
#: here.
_OPTION_GROUPS = {
    "Gang Queen": [
        ("any", [("photo-goggles", 35), ("bio-booster", 35)]),
    ],
    "Khimerix": [
        ("one", [("scaly hide", 0), ("caustic bite", 15), ("wings", 30)]),
    ],
}


def extra_groups(profile_name, subtype, base_price):
    """Build preview cards for additional option groups. Each preview applies one surcharge
    to the default selection, without combining independent groups.
    """
    return [
        HireGroup(
            choose=choose,
            options=[
                HireOption(
                    name=option_name,
                    price=surcharge,
                    total_price=base_price + surcharge,
                    # Only single-choice groups receive a default; optional groups start
                    # empty.
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


#: Composition checks compare Champion, Brute and Hanger-on counts against other members.
#: The view displays counts and notes; the operation enforces the limit.
LIMITED_SUBTYPES = frozenset({"Champion", "Brute", "Hanger-on"})


def _hire_card(name, subtype, rating, weapons):
    """Build a hire preview with production ModelCard dataclasses."""
    base = model_card()
    return replace(
        base,
        # Preview cards have no stored-model ID, so they display no tab strip.
        id="",
        name=name,
        rating=rating,
        subtypes=_printed(subtype),
        weapons=base.weapons[:weapons],
        # Unhired previews have no XP or owner.
        xp=0,
        xp_target=None,
        owned_by=None,
        # Use preview wording for stored effects without executing them.
        effects=base.effects,
    )


def hire_list():
    """Build the production hire-list display structures with sample profiles, options and
    preview cards, without database access.
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
                    # Always supply the default group, including a synthetic As standard
                    # option when there are no alternatives.
                    groups=[HireGroup(choose="one", options=options)]
                    + extra_groups(name, subtype, price),
                )
            )
        sections[-1].categories.append(
            HireCategory(name=category_name, entries=entries)
        )
    return sections


def hire_entry(value):
    """Find the sample hire entry by the slugified name submitted by its button."""
    if not value:
        return None
    for section in hire_list():
        for entry in section.all_entries():
            if slugify(entry.name) == value:
                return entry
    return None


def _hire_scope_tabs():
    """Build the three hire-list scope tabs."""
    from n26.core.views.hire import HIRE_SCOPES

    return [
        {"label": label, "href": f"?list={key}", "current": key == "gang"}
        for key, label in HIRE_SCOPES.items()
    ]


def hire_context():
    """Prepare sample hire sections and the price filter bounds."""
    sections = hire_list()
    entries = [entry for section in sections for entry in section.all_entries()]
    categories = [
        category.name for section in sections for category in section.categories
    ]
    return {
        "hire_list": sections,
        "hire_categories": categories,
        "hire_sections": [section.name for section in sections],
        "hire_scope_tabs": _hire_scope_tabs(),
        "hire_category_options": [
            {"value": name, "label": name} for name in categories
        ],
        "hire_price_floor": min(entry.base_price for entry in entries),
        "hire_price_ceiling": max(entry.base_price for entry in entries),
        # Preserve the selected entry's identity in the hire dialog's hidden fields.
        "hire_dialog_choices": ["Chainsword"],
        "hire_dialog_fields": [
            {"name": "profile", "value": "ganger"},
            {"name": "ganger:1", "value": "1"},
        ],
        # Display sample gang limits without enforcing them in the gallery.
    }


# ------------------------------------------------------------------ gang sheet

# Use the production GangSheet dataclass so component input changes also affect the
# gallery.


@dataclass(frozen=True)
class _Counter:
    """Stands in for library.Counter: something a CounterReading can name."""

    name: str
    drawn: bool = True

    def __str__(self):
        return self.name


def _reading(name, value):
    """Build the CounterReading structure used by GangSheet.counters."""
    from n26.core.effects import CounterReading

    return CounterReading(thing=_Counter(name), value=value)


#: Keep stash entries flat; the component groups them by kind. Kind labels use lower-case
#: verbose names and are capitalised only when rendered as headings.
STASH = [
    StashLine(name="Lasgun", rating=15, kind="weapon"),
    StashLine(name="Shotgun", rating=30, kind="weapon"),
    StashLine(name="Stub gun", rating=5, kind="weapon"),
    # Stack identical wargear with a count and unit rating. Weapons remain separate
    # because their profiles, accessories and choices can differ.
    StashLine(name="Mesh armour", rating=15, kind="wargear", count=2),
    StashLine(name="Photo-goggles", rating=35, kind="wargear"),
    # Name the pet granted by the collar; its model card appears on the gang sheet.
    StashLine(
        name="Cyber-mastiff (pet)", rating=100, kind="wargear", brought_in=("Rust",)
    ),
    # Display modifier-granted equipment with its provenance marker.
    StashLine(
        name="Respirator",
        rating=0,
        kind="wargear",
        provenance=Provenance(
            computed=True, source="Ash Wastes Nomads", source_kind="gang type"
        ),
    ),
    # Include equipment that is both granted and rated to exercise a tooltip trigger
    # with a price.
    StashLine(
        name="Blindsnake pouch",
        rating=60,
        kind="wargear",
        provenance=Provenance(
            computed=True, source="Ash Wastes Nomads", source_kind="gang type"
        ),
    ),
    # Supply unsorted kinds to verify that dictsort groups equal kinds before Django
    # regroup processes consecutive entries.
    StashLine(name="Fighting knife", rating=15, kind="weapon"),
]


#: Use # for editable choices and an empty URL for display-only offers without stored
#: assignments.
CHOICES = [
    ChoiceLine(kind_label="Skill trees", chosen="Ferocity, Brawn, Cunning", href="#"),
    # Long selected values must wrap within one choice control on narrow screens.
    ChoiceLine(
        kind_label="Variant",
        chosen="Genestealer Cult Corrupted, Chaos Corrupted, Malstrain Corrupted",
        href="#",
    ),
    # Inform rather than police. Display unresolved choices without treating them as
    # errors.
    ChoiceLine(kind_label="Territory", chosen=None, href="#"),
    ChoiceLine(kind_label="Alliance", chosen=None),
]


def gang_sheet():
    """Build a GangSheet with counters, granted stash equipment and campaign provenance.
    Include unresolved, multi-value and unlinked choices to exercise their display
    states.
    """
    return GangSheet(
        name="The Ashen Choir",
        campaign=CampaignBlock(
            name="Dust Falls",
            campaign_id="dust-falls",
            choices=[ChoiceLine(kind_label="Faction", chosen="Nomads", href="#")],
            # Provide URLs to exercise linked campaign assets; empty URLs render plain
            # text.
            href="#",
            assets_href="#",
            lines=[
                CampaignAssetLine(
                    type_label="Settlement",
                    type_plural="Settlements",
                    asset_type_id="settlement",
                    display_group="Territories",
                    name="Settlement",
                    provenance=Provenance(
                        source="Territory campaign", source_kind="campaign type"
                    ),
                )
            ],
            # Provide adjustment URLs to show owner counter controls.
            counters=[
                CounterLine(
                    name="Reputation",
                    value=3,
                    tallied=3,
                    assignment_id="reputation",
                    href="#",
                    back="#",
                    provenance=Provenance(
                        source="Territory campaign", source_kind="campaign type"
                    ),
                ),
                # This territory contributes the full displayed value through rules; its
                # stored counter remains zero.
                CounterLine(
                    name="Income",
                    value=30,
                    tallied=0,
                    assignment_id="income",
                    href="#",
                    back="#",
                    provenance=Provenance(
                        source="Territory campaign", source_kind="campaign type"
                    ),
                ),
            ],
            holdings=[
                CampaignAssetLine(
                    type_label="Territory",
                    type_plural="Territories",
                    asset_type_id="territory",
                    display_group="Territories",
                    name="Old Ruins",
                    income=30,
                    campaign_asset_id="old-ruins",
                )
            ],
        ),
        gang_type="Escher (HoB)",
        rating=360,
        credits=1037,
        wealth=1397,
        # Provide both visit state and remaining Trade Points; otherwise the strip
        # displays an unset value.
        visiting_trading_post=True,
        trade_points_left=3,
        colour="violet",
        rows=[
            AssignableLine(name="Founded in Cycle 3"),
            AssignableLine(name="Escher house list"),
        ],
        # Show direct and founding-granted assignments with distinct provenance.
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


#: Use stored editor markup so note previews follow the card's sanitising path.
CARD_NOTES = (
    "<p>Base needs redoing after the sump run — the flock came off. "
    "Owes Kaine a favour from the Ash Wastes job.</p>"
)
CARD_LORE = (
    "<p>Came up through the Choir's third dome and never lost the accent. "
    "Took the Matriarch's needle pistol off a body nobody has claimed, which is "
    "the only reason anyone remembers her name.</p>"
)


#: Use a generated SVG data URI to exercise image rendering without a stored upload.
CARD_IMAGE = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 250'%3E"
    "%3Crect width='200' height='250' fill='%23433a52'/%3E"
    "%3Ccircle cx='100' cy='95' r='45' fill='%23d8cde8'/%3E"
    "%3Cpath d='M30 250c0-50 31-80 70-80s70 30 70 80z' fill='%23d8cde8'/%3E"
    "%3C/svg%3E"
)


def model_card_as(variant, **changes):
    """Copy the sample card with a distinct anchor ID and the supplied changes. Each
    rendered variant needs a unique ID; the pet links to the single base card.
    """
    return replace(model_card(), id=f"vesna-krail-{variant}", **changes)


def model_card_digital():
    """Build the digital card variant with its own anchor."""
    return model_card_as("digital")


def model_card_unwritten():
    """Build a card with empty Lore and Notes tabs and their Edit actions."""
    return model_card_as("unwritten")


def model_card_founding():
    """Build a founding card showing the model's remaining Trade Points."""
    return model_card_as("founding", founding_budget=True, trade_points_left=3)


def model_card_actions_waiting():
    """Build an owner card with several pending actions for its summary strip."""
    return model_card_as(
        "actions-waiting",
        action_names=("Advancement", "Suit Evolution"),
    )


def model_card_written():
    """Build a card with a picture and populated Lore and Notes tabs."""
    return model_card_as(
        "written", notes=CARD_NOTES, lore=CARD_LORE, image_url=CARD_IMAGE
    )


def model_card_in_recovery():
    """Build a card displaying the In Recovery status."""
    return model_card_as("in-recovery", status="recovery", status_label="In Recovery")


def model_card_pet():
    """Build a pet card with a link to its owner's card on the same gallery page."""
    return ModelCard(
        id="fang",
        name="Fang",
        profile_name="Phyrr Cat",
        rating=15,
        profile_type="Fighter",
        subtypes=_printed("Exotic Beast"),
        statline=_fighter_statline(),
        skills=_printed("Dodge"),
        equipment=_printed("Spiked collar (15¢)"),
        owned_by="Vesna Krail",
        owned_by_id="vesna-krail",
        xp=0,
        xp_target=6,
    )


def model_card_in_the_stash():
    """Build a pet card identifying the stash as the location of its granting collar."""
    return replace(
        model_card_pet(),
        id="fang-in-the-stash",
        owned_by=None,
        owned_by_id="",
        in_stash=True,
    )


def model_card_dead():
    """Build a dead card with its status styling and excluded rating."""
    return model_card_as(
        "dead",
        rating=0,
        status="dead",
        status_label="Dead",
    )


#: Short and long model and owner names exercise header wrapping.
SHORT_HEADER_NAME = "Vesna Krail"
LONG_HEADER_NAME = "Vashti Corvinus-Kane the Thrice-Wounded"
SHORT_HEADER_OWNER = "Yolanda"
LONG_HEADER_OWNER = "Archregent Hollis Varn-Mortenkeep"


def _header_card(name, owned_by, **changes):
    """Build a minimal statline card for header layout checks. Omit its ID to avoid tabs
    and anchors; optional status fields select the active control or status badge.
    """
    return ModelCard(
        name=name,
        profile_name="Escher Death-Maiden",
        rating=390,
        profile_type="Fighter",
        statline=_fighter_statline(),
        owned_by=owned_by,
        # The header demo supplies the link to this model separately.
        owned_by_id="vesna-krail",
        founding_budget=True,
        trade_points_left=3,
        image_url=CARD_IMAGE,
        xp=0,
        xp_target=6,
        **changes,
    )


def model_card_header_short():
    """Build a header with short model and owner names."""
    return _header_card(SHORT_HEADER_NAME, SHORT_HEADER_OWNER)


def model_card_header_long_name():
    """Build a header with a long model name."""
    return _header_card(LONG_HEADER_NAME, SHORT_HEADER_OWNER)


def model_card_header_long_owner():
    """Build a header with a long owner name."""
    return _header_card(SHORT_HEADER_NAME, LONG_HEADER_OWNER)


def model_card_header_long_both():
    """Build a header with long model and owner names."""
    return _header_card(LONG_HEADER_NAME, LONG_HEADER_OWNER)


def model_card_header_badged():
    """Build a header combining long names with a long status badge."""
    return _header_card(
        LONG_HEADER_NAME,
        LONG_HEADER_OWNER,
        status=Status.CRITICAL,
        status_label=label_for(Status.CRITICAL),
    )


def model_card_editable():
    """Build the model-page card with counter and equipment actions. Keep these controls
    out of the base card used for sheets, hire previews and printing; gallery targets
    use #.
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

    card = model_card_as("edit")
    card.dismissed_choices = [
        ChoiceLine(
            kind_label="Archetype", chosen=None, dismissed=True, restore_href="#"
        )
    ]

    card.counters = [replace(line, href="#", adjust_href="#") for line in card.counters]
    # Expand stacked equipment into individual assignments so each receives its own
    # action menu.
    card.equipment = [
        replace(line, sell=sell, more=more, count=1)
        for line in card.equipment
        for _ in range(line.count)
    ]
    for weapon in card.weapons:
        weapon.sell = sell
        weapon.more = more
        weapon.accessorise = accessorise
        weapon.choices = [replace(choice, href="#") for choice in weapon.choices]
        weapon.accessories = [
            replace(line, sell=sell, more=part_more) for line in weapon.accessories
        ]
        for profile in weapon.named_profiles:
            profile.sell = sell
            profile.more = part_more
    return card


def gang_sheet_context():
    """Prepare the gang sheet and its surrounding demo controls."""
    from n26.core.founding import FoundingBudget
    from n26.core.models import Activity
    from n26.core.render import RosterGroup, RosterLine, RosterSummary

    sheet = gang_sheet()
    members = [
        ("Vesna Krail", "Escher Gang Queen", 135),
        ("Sister Yara", "Death Maiden", 105),
        ("Ilse Vandt", "Matriarch", 95),
        ("Vex", "Ganger", 55),
        ("Sull", "Ganger", 55),
    ]
    # Match the summary count and rating to the model cards rendered by this demo.
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
    founding_open = open_card(
        Activity.Kind.FOUNDING,
        "#",
        help=FOUNDING_HELP,
        about=FOUNDING_ABOUT,
        marked=True,
    )
    a_visit = VisitLine(trade_points_left=3, href="#")
    post_battle_steps = steps_waiting(sheet, post_battle_at="#post-battle")
    recovery_sheet = replace(sheet, models=[model_card_in_recovery()])
    return {
        "gang": sheet,
        # Use the production action-card builder to show visits with figures and
        # founding without them.
        "sample_action_visit": open_card(
            Activity.Kind.TRADING_POST_VISIT, "#", help=VISIT_HELP, facts=visit_facts
        ),
        "sample_action_founding": founding_open,
        # Offer founding only in samples without an open founding action.
        "sample_square_empty": ActivitiesSquare(start_founding="#", history_href="#"),
        "sample_square_founding": ActivitiesSquare(
            founding=founding_open, history_href="#"
        ),
        "sample_square_visit": ActivitiesSquare(
            visit=a_visit, start_founding="#", history_href="#"
        ),
        "sample_square_both": ActivitiesSquare(
            founding=founding_open, visit=a_visit, history_href="#"
        ),
        # Keep the history link available even when the gang has no recorded actions.
        "sample_square_no_history": ActivitiesSquare(
            start_founding="#", history_href="#"
        ),
        "sample_square_post_battle": ActivitiesSquare(
            history_href="#", to_do=post_battle_steps
        ),
        "sample_square_post_battle_empty": ActivitiesSquare(
            history_href="#", to_do=post_battle_steps
        ),
        "sample_square_all_actions": ActivitiesSquare(
            founding=founding_open,
            visit=a_visit,
            history_href="#",
            to_do=steps_waiting(
                recovery_sheet,
                ransoms=(("Vex", "#ransom"),),
                clean_house_at="#clean-house",
                post_battle_at="#post-battle",
            ),
        ),
        # Show a model founding allowance alongside an open gang visit using the
        # production budget structure.
        "sample_founding_budget": FoundingBudget(
            activity=Activity(kind=Activity.Kind.FOUNDING), granted=5, spent=2
        ),
        "sample_founding_model": {"name": "Yolanda Kray"},
        # Include a gang without an open visit to exercise the start-visit action.
        "sample_sheet_no_visit": replace(
            sheet, visiting_trading_post=False, trade_points_left=None
        ),
        # Exercise a simple visit tally and an overspend confirmation with two
        # emphasised totals.
        "tally_facts": visit_facts,
        "tally_overspend": (
            Fact("Available", "4"),
            Fact("Spent", "3"),
            Fact("Remaining", "1", ruled=True, strong=True),
            Fact("This purchase", "3"),
            Fact("Remaining after", "-2", ruled=True, strong=True),
        ),
        # Use distinct copies and anchor IDs for each model in the roster grid. Include
        # two models sharing a profile to exercise separate personal names.
        "gang_members": [
            replace(
                sheet.models[0],
                id=slugify(name),
                name=name,
                profile_name=profile,
                rating=rating,
            )
            for name, profile, rating in members
        ],
        "gang_owner": OWNER,
    }


# --------------------------------------------------------------------- campaign

#: Include per-gang Settlements and transferable Territories.
CAMPAIGN_ASSET_TYPES = [
    AssetTypeColumn(
        asset_type_id="settlement",
        label="Settlement",
        plural="Settlements",
        holding=False,
        display_group="Territories",
    ),
    AssetTypeColumn(
        asset_type_id="territory",
        label="Territory",
        plural="Territories",
        holding=True,
        display_group="Territories",
    ),
]


#: Supply a rolled table to exercise campaign roll controls.
SELECTION_TABLE = HeldTable(
    table_id="territory-selection-table",
    name="Territory Selection Table",
    asset_type_id="territory",
    dice="d66",
    die="D66",
)


def campaign_sheet():
    """Build a campaign sheet with varied gangs, missing counters and held or unclaimed
    assets. Use # targets to display arbitrator controls without writing data.
    """
    return CampaignSheet(
        name="Dust Falls",
        campaign_id="dust-falls",
        campaign_type="Territory campaign",
        campaign_type_description=(
            "Gangs fight over territories, each bringing income to the gang holding it."
        ),
        arbitrator=OWNER,
        budget=1250,
        summary=(
            "<p>Six weeks of raids over the eastern sumps. Territories change "
            "hands after every battle; the arbitrator settles ties at the "
            "table.</p>"
        ),
        add_asset_type_href="#",
        add_counter_href="#",
        add_label_href="#",
        counter_columns=["Reputation", "Income", "Meat"],
        label_columns=["Alignment", "Campaign objective"],
        asset_types=CAMPAIGN_ASSET_TYPES,
        gangs=[
            CampaignGangLine(
                gang_id="gravebolt-kin",
                name="Gravebolt Kin",
                gang_type="Goliath (HoC)",
                owner=SampleUser("marta"),
                rating=1180,
                credits=95,
                wealth=1275,
                colour="orange",
                over_budget=True,
                counters=[
                    CounterLine(
                        name="Reputation",
                        value=4,
                        tallied=4,
                        assignment_id="gravebolt-reputation",
                        href="#",
                        back="#",
                    ),
                    CounterLine(
                        name="Income",
                        value=20,
                        tallied=0,
                        assignment_id="gravebolt-income",
                        href="#",
                        back="#",
                    ),
                    CounterLine(
                        name="Meat",
                        value=2,
                        tallied=2,
                        assignment_id="gravebolt-meat",
                        href="#",
                        back="#",
                    ),
                ],
                labels=["Outlaw", "Control the trade routes through the eastern sump"],
                assets=[["Settlement"], ["Toll Crossing"]],
                href="#",
            ),
            CampaignGangLine(
                gang_id="pit-of-teeth",
                name="Pit of Teeth",
                gang_type="Cawdor (HoF)",
                owner=SampleUser("ossian"),
                rating=940,
                credits=210,
                wealth=1150,
                colour="teal",
                counters=[
                    CounterLine(
                        name="Reputation",
                        value=1,
                        tallied=1,
                        assignment_id="pit-reputation",
                        href="#",
                        back="#",
                    ),
                    CounterLine(
                        name="Income",
                        value=0,
                        tallied=0,
                        assignment_id="pit-income",
                        href="#",
                        back="#",
                    ),
                    None,
                ],
                labels=["", ""],
                assets=[["Settlement"], []],
                href="#",
            ),
            CampaignGangLine(
                gang_id="the-ashen-choir",
                name="The Ashen Choir",
                gang_type="Escher (HoB)",
                owner=SampleUser(OWNER),
                rating=1037,
                credits=160,
                wealth=1197,
                colour="violet",
                counters=[
                    CounterLine(
                        name="Reputation",
                        value=3,
                        tallied=3,
                        assignment_id="choir-reputation",
                        href="#",
                        back="#",
                    ),
                    CounterLine(
                        name="Income",
                        value=60,
                        tallied=0,
                        assignment_id="choir-income",
                        href="#",
                        back="#",
                    ),
                    CounterLine(
                        name="Meat",
                        value=0,
                        tallied=0,
                        assignment_id="choir-meat",
                        href="#",
                        back="#",
                    ),
                ],
                labels=["Law Abiding", "Hold the lower sump"],
                assets=[["Settlement"], ["Old Ruins", "Old Ruins by the sump"]],
                starting_rolls=[
                    StartingRoll(
                        asset_type_id="territory",
                        label="Roll starting territory",
                        tables=[SELECTION_TABLE],
                        href="#",
                    )
                ],
                href="#",
                yours=True,
            ),
        ],
        tables_href="#",
        territories_to_generate=9,
        assets=[
            CampaignAssetTable(
                asset_type_id="territory",
                label="Territory",
                plural="Territories",
                add_href="#",
                create_href="#",
                roll_href="#",
                tables=[SELECTION_TABLE],
                entries=[
                    CampaignAssetEntry(
                        campaign_asset_id="old-ruins",
                        name="Old Ruins",
                        income=30,
                        held=True,
                        holder="The Ashen Choir",
                        holder_gang_id="the-ashen-choir",
                        holder_href="#",
                        holder_yours=True,
                        unassign_href="#",
                        transfer_href="#",
                    ),
                    CampaignAssetEntry(
                        campaign_asset_id="old-ruins-sump",
                        name="Old Ruins by the sump",
                        asset_name="Old Ruins",
                        income=30,
                        held=True,
                        holder="The Ashen Choir",
                        holder_gang_id="the-ashen-choir",
                        holder_href="#",
                        holder_yours=True,
                        unassign_href="#",
                    ),
                    CampaignAssetEntry(
                        campaign_asset_id="toll-crossing",
                        name="Toll Crossing",
                        income=20,
                        held=True,
                        holder="Gravebolt Kin",
                        holder_gang_id="gravebolt-kin",
                        holder_href="#",
                        unassign_href="#",
                    ),
                    CampaignAssetEntry(
                        campaign_asset_id="collapsed-dome",
                        name="Collapsed Dome",
                        income=10,
                        assign_href="#",
                        remove_href="#",
                    ),
                ],
            ),
        ],
        battles_fought=7,
    )


def campaign_sheet_context():
    """Prepare the campaign sheet and its surrounding shell context."""
    from n26.core.history import Act, Span
    from n26.core.navigation import Switcher, SwitcherItem

    now = timezone.now()
    # Render the campaign from its arbitrator's perspective: their actions use You,
    # while others use account names and badges.
    acts = [
        Act(
            when=now - timedelta(minutes=minutes),
            actor="You" if actor == OWNER else actor,
            actor_user=SampleUser(actor) if actor not in ("", OWNER) else None,
            spans=tuple(Span(text) for text in spans),
            category="campaign",
            gang_name=gang_name,
        )
        for minutes, actor, spans, gang_name in (
            (12, "", ("Old Ruins", " went to The Ashen Choir"), ""),
            (40, "marta", ("hired Brakk, a Ganger",), "Gravebolt Kin"),
            (95, OWNER, ("recorded a battle fought on 4 September",), ""),
            (3 * 60, OWNER, ("added the asset Collapsed Dome",), ""),
            (26 * 60, "ossian", ("accepted the invitation",), ""),
            (27 * 60, OWNER, ("invited ossian",), ""),
            (48 * 60, OWNER, ("set the campaign up on Territory campaign",), ""),
        )
    ]
    return {
        "campaign_sheet": campaign_sheet(),
        "campaign_acts": acts,
        "campaign_players": [
            {"user": SampleUser("marta"), "state": "accepted"},
            {"user": SampleUser("ossian"), "state": "accepted"},
            {"user": SampleUser("vey"), "state": "invited"},
        ],
        "campaign_battles": [
            {
                "date": now - timedelta(days=1),
                "gangs": "Gravebolt Kin, The Ashen Choir",
            },
            {"date": now - timedelta(days=8), "gangs": "Pit of Teeth, The Ashen Choir"},
        ],
        "campaign_switcher": Switcher(
            label="Dust Falls",
            href="#dust-falls",
            heading="Your campaigns",
            menu_label="Switch to another campaign",
            placeholder="Search campaigns",
            empty="No campaigns match",
            items=(
                SwitcherItem(label="Dust Falls", href="#dust-falls", current=True),
                SwitcherItem(label="The Long Descent", href="#the-long-descent"),
            ),
        ),
    }


# -------------------------------------------------------------------- dashboard

# Use GangSheet inputs for c-n26.wealth so dashboard amounts share the production
# display structure.


#: Synthetic monochrome SVG artwork inherits the surrounding text colour.
SAMPLE_GANG_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path d="M12 2 3 6v6c0 5.1 3.8 8.8 9 10 5.2-1.2 9-4.9 9-10V6l-9-4Zm0 2.2 '
    '7 3.1V12c0 4.1-2.9 7.1-7 8.1-4.1-1-7-4-7-8.1V7.3l7-3.1Z"/>'
    '<path d="M9 9h6v2H9Zm2 3h2v5h-2Z"/></svg>'
)

#: Only one type has artwork so the table also exercises alignment without a badge.
GANG_TYPE_ICONS = {"Goliath (HoC)": SAMPLE_GANG_ICON}


def _gang_summary(
    name, gang_type, rating, credits, stash_rating, colour="", model_count=0
):
    return GangSheet(
        name=name,
        gang_type=gang_type,
        rating=rating,
        credits=credits,
        stash_rating=stash_rating,
        wealth=rating + credits + stash_rating,
        colour=colour,
        model_count=model_count,
    )


#: Vary name length, repeated types, zero stash rating and missing colours to exercise
#: table filtering and alignment.
GANGS = [
    _gang_summary(
        "The Ashen Choir", "Escher (HoB)", 360, 1037, 100, "violet", model_count=4
    ),
    _gang_summary(
        "Rust in Peace", "Goliath (HoC)", 1240, 85, 0, "amber", model_count=11
    ),
    _gang_summary(
        "The Silent Ledger and the Long Count",
        "Delaque (HoS)",
        980,
        210,
        45,
        model_count=9,
    ),
    _gang_summary(
        "Sump City Rats", "Underhive Outcasts", 1475, 12, 260, "teal", model_count=15
    ),
    _gang_summary("Cog and Coil", "Goliath (HoC)", 1105, 430, 75, model_count=8),
]

#: Long changelog summaries exercise the two-line clamp.
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

# Use production owned-equipment structures and conversion helpers for catalogue entries
# and dialogs. Placeholder URLs keep the demos on the gallery page.


@dataclass(frozen=True)
class _Roster:
    """Minimal model offered by the move dialog."""

    pk: str
    name: str


def carried():
    """Build OwnedThing instances keyed by content identity for build_catalogue. Include
    repeated weapons, a paid weapon part and selected mount options to exercise owned-
    entry states.
    """
    from n26.core.owned import OwnedPart, OwnedThing, thing_key

    def entry(name, rating, index=0, parts=(), chosen=(), fit_href=""):
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
        entry("Meltagun", 135, parts=(round_,)),
        entry("Stub gun", 5, index=0),
        entry("Stub gun", 5, index=1),
        # Include a mount with one selected option from each group, alongside an unowned
        # mount that still offers purchase controls.
        entry(
            "Ridge-runner",
            125,
            chosen=("Ridge-runner harpoon", "Ridge-runner spikes"),
        ),
        # An unattached accessory offers fitting to one of the owned weapons.
        entry("Infra-sight", 40, fit_href="#"),
    ):
        held.setdefault(key, []).append(thing)
    return held


def _stock(name):
    """Find a catalogue assignable or paid part by name."""
    for line in trading_post().all_lines():
        if line.name == name:
            return line.thing
        for part in line.parts:
            if part.name == name:
                return part.thing
    raise KeyError(name)


def owned_context():
    """Prepare owned equipment and its sale, refund, fitting and option dialogs."""
    from n26.core.listing import copy_row, pick_group_props, pick_groups

    named = {"cancel_url": "#", "action": "#", "list": "", "name": "Meltagun"}
    held_options = {"Ridge-runner harpoon", "Ridge-runner spikes"}
    choices = pick_groups(
        _offered_choices("Ridge-runner"),
        "library.wargear:ridge-runner",
        taken=held_options,
    )
    return {
        "owned_copies": [
            copy_row(thing) for entries in carried().values() for thing in entries
        ],
        # Sale proceeds include the gun and its paid ammunition.
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
        # Offer fitting dialogs with and without eligible weapons; the empty case omits
        # submission. The refund below returns the 120 credits paid, independently of
        # the 155-credit rating.
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
            "sum": "You get 120¢ back — the amount paid, not its rating.",
            "submit_label": "Refund",
            "submit_variant": "danger",
        },
        # Keeping the sight yields 78 credits for the gun; selling both yields 91.
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
        # Use the production option loader with the mount's existing harpoon and spike
        # selections.
        "owned_rechoose_dialog": {
            **named,
            "kind": "rechoose",
            "name": "Ridge-runner",
            "title": "Change Ridge-runner's options",
            "choices": choices,
            "price_preview": {
                "changing": True,
                "choices": pick_group_props(choices),
                "before": 35,
                "held": sorted(held_options),
                "refunds": [],
                "resolution": [
                    {
                        "choose": group.choose,
                        "options": [
                            {"setKey": option.set_key, "price": option.price}
                            for option in group.options
                        ],
                    }
                    for group in choices
                ],
            },
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
            "remove_note": (
                "No credits are returned. Use Refund instead to recover the "
                "amount paid."
            ),
            "submit_label": "Delete",
            "submit_variant": "danger",
        },
    }


def dashboard_context():
    """Prepare gang sheets, type artwork and changelog entries. Wrap each sheet with its
    type artwork so markup stays outside GangSheet.
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
        # Preserve type order from the displayed gangs when removing duplicates for the
        # filter.
        "dashboard_types": [
            {"value": name, "label": name}
            for name in dict.fromkeys(gang.gang_type for gang in GANGS)
        ],
        "dashboard_changelog": CHANGELOG,
        "dashboard_username": OWNER,
    }
