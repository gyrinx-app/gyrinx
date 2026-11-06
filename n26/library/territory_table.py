"""Seed the core Territory Selection Table and its D66 asset entries.

Create missing territories with no income or boons. Build the table into
the Territory campaign type so joining gangs receive it.

Match natural keys and preserve existing content. The functions accept
historical model classes for migration use.
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
    """Create missing Territory table content and return ``(lines, made)``.

    ``lines`` reports each created or skipped record; ``made`` contains built-in
    members requiring propagation. Seed the campaign and asset type first.
    If a same-named asset belongs to another type, skip its entry and report it
    instead of violating the pack-and-name uniqueness constraint.
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
