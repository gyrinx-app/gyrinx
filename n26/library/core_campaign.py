"""The N26 core campaign type — the one campaign type every install has.

Reputation is a counter every campaign type in the books tracks, so it
ships in the system pack. The N26 core type declares the two asset kinds
the core rules deal in — a Settlement every gang holds, and Territories
held one at a time from a pool — and gives every member gang Reputation
at 0 and a Settlement through its built-ins. See
design/campaign-assets.md.

Everything is matched on its natural key and left alone if it is
already there, so this can run against a database that has some of it,
and running it twice changes nothing the second time. Names are matched
without regard to case, because that is how the library's own
uniqueness is stated. Written against whatever model classes it is
handed, so a migration can run it on historical ones.
"""

from django.conf import settings

REPUTATION = "Reputation"
CAMPAIGN_TYPE = "N26 core"
#: ``(label, plural, mode, position)`` for each kind the core type deals in.
ASSET_KINDS = (
    ("Settlement", "Settlements", "held-one-each", 0),
    ("Territory", "Territories", "pooled", 1),
)
SETTLEMENT = "Settlement"
#: Named as ``authoring.add_built_in`` would name it, so the set reads
#: like every other type's on the authoring pages.
BUILT_INS = f"{CAMPAIGN_TYPE} built-ins"


def seed_core_campaign(apps):
    """Create what is missing of the N26 core campaign type, and return
    one line per row created, so a caller can say what happened."""
    lines = []
    ContentPack = apps.get_model("library", "ContentPack")
    Counter = apps.get_model("library", "Counter")
    CampaignType = apps.get_model("library", "CampaignType")
    AssetKind = apps.get_model("library", "AssetKind")
    Asset = apps.get_model("library", "Asset")
    DefaultAssignmentSet = apps.get_model("library", "DefaultAssignmentSet")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")

    pack, _ = ContentPack.objects.get_or_create(
        slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        defaults={"name": settings.DEFAULT_CONTENT_PACK_NAME},
    )

    reputation = Counter.objects.filter(
        pack=pack, name__iexact=REPUTATION, qualifier=""
    ).first()
    if reputation is None:
        reputation = Counter.objects.create(pack=pack, name=REPUTATION)
        lines.append(f"created the {REPUTATION} counter")

    campaign_type = CampaignType.objects.filter(
        pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
    ).first()
    if campaign_type is None:
        campaign_type = CampaignType.objects.create(pack=pack, name=CAMPAIGN_TYPE)
        lines.append(f"created the {CAMPAIGN_TYPE} campaign type")

    kinds = {}
    for label, plural, mode, position in ASSET_KINDS:
        kind = AssetKind.objects.filter(
            campaign_type=campaign_type, label_singular__iexact=label
        ).first()
        if kind is None:
            kind = AssetKind.objects.create(
                pack=pack,
                campaign_type=campaign_type,
                label_singular=label,
                label_plural=plural,
                mode=mode,
                position=position,
            )
            lines.append(f"created the {label} asset kind")
        kinds[label] = kind

    settlement = Asset.objects.filter(
        pack=pack, name__iexact=SETTLEMENT, qualifier=""
    ).first()
    if settlement is None:
        settlement = Asset.objects.create(
            pack=pack, name=SETTLEMENT, kind=kinds[SETTLEMENT]
        )
        lines.append(f"created the {SETTLEMENT} asset")
    if not campaign_type.assets.filter(pk=settlement.pk).exists():
        campaign_type.assets.add(settlement)
        lines.append(f"offered {SETTLEMENT} from {CAMPAIGN_TYPE}")

    built_ins = campaign_type.built_ins
    if built_ins is None:
        built_ins = DefaultAssignmentSet.objects.filter(
            pack=pack, name__iexact=BUILT_INS
        ).first()
        if built_ins is None:
            built_ins = DefaultAssignmentSet.objects.create(pack=pack, name=BUILT_INS)
            lines.append(f"created the {BUILT_INS} set")
        campaign_type.built_ins = built_ins
        campaign_type.save(update_fields=["built_ins"])

    members = built_ins.members
    if not members.filter(counter=reputation).exists():
        DefaultAssignment.objects.create(
            pack=pack, default_set=built_ins, counter=reputation, amount=0, position=0
        )
        lines.append(f"built {REPUTATION} at 0 into {CAMPAIGN_TYPE}")
    if not members.filter(asset=settlement).exists():
        DefaultAssignment.objects.create(
            pack=pack, default_set=built_ins, asset=settlement, position=1
        )
        lines.append(f"built the {SETTLEMENT} into {CAMPAIGN_TYPE}")
    return lines
