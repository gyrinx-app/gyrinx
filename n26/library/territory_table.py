"""The Territory Selection Table — the core rulebook's table of Territories.

The Territory campaign type deals in Territories, and the Arbitrator
generates a campaign's Territories by rolling a D66 on one table of them.
That table is content: an ``AssetTable`` of the Territory asset type in
the system pack, with one entry per Territory claiming its band of
rolls. Every Territory it names is an asset of that type; one the seed
does not find is created with no income and no boons, for the content
pass that follows to fill in. Creating the table builds it into the
Territory campaign type by the rule every table follows
(``n26/library/tables.py``), so every gang that joins a campaign of that
type holds the table and may roll on it.

Everything is matched on its natural key and left alone if it is already
there, so this can run against a database that has some of it, and
running it twice changes nothing the second time. Written against
whatever model classes it is handed, so a migration can run it on
historical ones.
"""

from django.conf import settings

from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.tables import build_in_missing

TABLE = "Territory Selection Table"
TERRITORY = "Territory"
#: The die the table is rolled on — the stored value of ``Dice.D66``,
#: spelt out so this can run against historical classes.
DICE = "d66"
#: ``(roll_low, roll_high, territory)`` for every entry, in the book's
#: order. The bands cover every roll a D66 can make, once each.
ENTRIES = (
    (11, 12, "Bullet Den"),
    (13, 14, "Rogue Doc Shop"),
    (15, 16, "Mess Shack"),
    (21, 22, "Drinking Hole"),
    (23, 24, "Fence Hangout"),
    (25, 26, "Bounty Den"),
    (31, 32, "Generatorium"),
    (33, 34, "Corpse Farm"),
    (35, 36, "Tunnels"),
    (41, 42, "Tech Bazaar"),
    (43, 44, "Promethium Cache"),
    (45, 46, "Collapsed Dome"),
    (51, 52, "Bone Shrine"),
    (53, 54, "Mine Workings"),
    (55, 56, "Gambling Den"),
    (61, 62, "Synth Still"),
    (63, 64, "Old Ruins"),
    (65, 66, "Fighting Pit"),
)


def seed_territory_table(apps):
    """Create what is missing of the Territory Selection Table, and return
    ``(lines, made)``: one line per row created or skipped, so a caller
    can say what happened, and the built-in members this run made, so a
    caller can file the propagation those sets are owed.

    The Territory campaign type and its Territory asset type are created
    first where they are missing (``seed_core_campaign``), so this runs on
    a fresh database as readily as on one that has the type already. An
    asset is matched on the columns its uniqueness is stated in — pack and
    name — so a same-named asset already standing under another asset
    type is found rather than collided with; its entry is skipped, and
    the line says so, for a person to sort out.
    """
    lines = seed_core_campaign(apps)
    ContentPack = apps.get_model("library", "ContentPack")
    CampaignType = apps.get_model("library", "CampaignType")
    Asset = apps.get_model("library", "Asset")
    AssetTable = apps.get_model("library", "AssetTable")
    AssetTableEntry = apps.get_model("library", "AssetTableEntry")

    pack = ContentPack.objects.get(slug=settings.DEFAULT_CONTENT_PACK_SLUG)
    campaign_type = CampaignType.objects.get(
        pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
    )
    territory = campaign_type.asset_types.get(label_singular__iexact=TERRITORY)

    table = AssetTable.objects.filter(
        pack=pack, name__iexact=TABLE, qualifier=""
    ).first()
    if table is None:
        table = AssetTable.objects.create(
            pack=pack, name=TABLE, asset_type=territory, dice=DICE
        )
        lines.append(f"created the {TABLE} under the {TERRITORY} asset type")

    for position, (roll_low, roll_high, name) in enumerate(ENTRIES):
        asset = Asset.objects.filter(pack=pack, name__iexact=name, qualifier="").first()
        if asset is None:
            asset = Asset.objects.create(pack=pack, name=name, asset_type=territory)
            lines.append(f"created the {name} {TERRITORY}")
        elif asset.asset_type_id != territory.pk:
            lines.append(
                f"skipped {name}: an asset of that name already stands under "
                f"another asset type, so no entry was made for it"
            )
            continue
        if not table.entries.filter(asset=asset).exists():
            AssetTableEntry.objects.create(
                pack=pack,
                table=table,
                asset=asset,
                position=position,
                roll_low=roll_low,
                roll_high=roll_high,
            )
            lines.append(f"{name} lands on {roll_low}-{roll_high}")

    made = build_in_missing(apps, campaign_type)
    for member in made:
        lines.append(f"built the {member.asset_table.name} into {CAMPAIGN_TYPE}")
    return lines, made
