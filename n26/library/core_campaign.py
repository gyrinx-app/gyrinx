"""The Territory campaign type — the one campaign type every install has.

The core rulebook's campaign is a fight over Territory: every gang keeps
a Settlement, one Territory is drawn for it at the start, each Territory
held gives its holder a Boon, and the campaign runs Occupation, Downtime
and Takeover before Triumphs are awarded. Reputation is a counter every
campaign type in the books tracks, so it ships in the system pack. The
Territory campaign type declares the two asset kinds that campaign deals
in — a Settlement every gang holds, and Territories that change hands —
with one Settlement asset under the Settlement kind, and gives every
member gang Reputation at 0 and that Settlement through its built-ins.
See design/campaign-assets.md.

Everything is matched on its natural key and left alone if it is
already there, so this can run against a database that has some of it,
and running it twice changes nothing the second time. Names are matched
without regard to case, because that is how the library's own
uniqueness is stated. Written against whatever model classes it is
handed, so a migration can run it on historical ones.
"""

from django.conf import settings

REPUTATION = "Reputation"
CAMPAIGN_TYPE = "Territory campaign"
#: What the type was called before it took the rulebook's own subject as
#: its name. ``rename_core_campaign`` moves a row under this name across.
FORMER_NAME = "N26 core"
#: ``(label, plural, mode, position)`` for each kind the core type has.
ASSET_KINDS = (
    ("Settlement", "Settlements", "held-one-each", 0),
    ("Territory", "Territories", "pooled", 1),
)
SETTLEMENT = "Settlement"
#: Named as ``authoring.add_built_in`` would name it, so the set reads
#: like every other type's on the authoring pages.
BUILT_INS = f"{CAMPAIGN_TYPE} built-ins"
FORMER_BUILT_INS = f"{FORMER_NAME} built-ins"

#: What the arbitrator setting a campaign up reads. Our own words about
#: the core rulebook's campaign, never the book's.
DESCRIPTION = (
    "The core rulebook's campaign: gangs fight for control of Territory. "
    "Every gang keeps a Settlement it cannot lose and starts with one "
    "Territory drawn from the campaign's table. Each Territory a gang "
    "holds gives it a Boon, such as income, Reputation or equipment. The "
    "campaign has three phases: Occupation, Downtime and Takeover. It ends "
    "with Triumphs awarded for the most Territories, the highest Reputation, "
    "the most battles fought, the most enemies taken out of action and the "
    "highest Wealth."
)
#: What a content author reads on the authoring pages.
LIBRARY_AUTHOR_HELP = (
    "The campaign type from the core rulebook. Settlement is held one "
    "each: every gang is given one when it joins and keeps it. Territory "
    "changes hands. Add each Territory as an asset under that kind, with "
    "its income figure and its Boons as modifiers. Reputation at 0 and the "
    "Settlement are built in, so every gang that joins starts with both."
)


def seed_core_campaign(apps):
    """Create what is missing of the Territory campaign type, and return
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
        fields = {"pack": pack, "name": CAMPAIGN_TYPE}
        fields.update(_words_for(CampaignType))
        campaign_type = CampaignType.objects.create(**fields)
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
        lines.append(f"created the {SETTLEMENT} asset under the {SETTLEMENT} kind")

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


def rename_core_campaign(apps):
    """Move a system-pack type standing under the former name to the
    current one, with its built-ins set, and give the type its words where
    it has none. Returns one line per change, so a caller can say what
    happened.

    Nothing is renamed while a row already holds the current name: two
    types cannot share it, and which of the two is the real one is a
    question for a person. A type already renamed, or created under the
    current name, only gains whichever of its two texts is still blank —
    so this runs as often as it likes and never overwrites an author's
    own words.
    """
    lines = []
    ContentPack = apps.get_model("library", "ContentPack")
    CampaignType = apps.get_model("library", "CampaignType")
    DefaultAssignmentSet = apps.get_model("library", "DefaultAssignmentSet")

    pack = ContentPack.objects.filter(slug=settings.DEFAULT_CONTENT_PACK_SLUG).first()
    if pack is None:
        return lines
    types = CampaignType.objects.filter(pack=pack, qualifier="")
    current = types.filter(name__iexact=CAMPAIGN_TYPE).first()
    former = types.filter(name__iexact=FORMER_NAME).first()

    if current is None and former is not None:
        former.name = CAMPAIGN_TYPE
        former.save(update_fields=["name"])
        lines.append(f"renamed the {FORMER_NAME} campaign type to {CAMPAIGN_TYPE}")
        current = former

    if current is None:
        return lines
    # The set follows the type, whichever run renamed the type: a set
    # still under the former name is renamed as long as the new name is
    # free, so the authoring pages read it as the type's own.
    built_ins = DefaultAssignmentSet.objects.filter(
        pack=pack, name__iexact=FORMER_BUILT_INS
    ).first()
    taken = DefaultAssignmentSet.objects.filter(
        pack=pack, name__iexact=BUILT_INS
    ).exists()
    if built_ins is not None and not taken:
        built_ins.name = BUILT_INS
        built_ins.save(update_fields=["name"])
        lines.append(f"renamed the {FORMER_BUILT_INS} set to {BUILT_INS}")
    changed = []
    for field, words in _words_for(CampaignType).items():
        if not getattr(current, field):
            setattr(current, field, words)
            changed.append(field)
    if changed:
        current.save(update_fields=changed)
        lines.append(f"gave {CAMPAIGN_TYPE} its {' and '.join(changed)}")
    return lines


def _words_for(CampaignType):
    """The type's two texts, keyed by field — only the fields this model
    class has, so the seed can run on a historical class from before the
    description existed."""
    names = {field.name for field in CampaignType._meta.get_fields()}
    words = {
        "description": DESCRIPTION,
        "library_author_help": LIBRARY_AUTHOR_HELP,
    }
    return {name: text for name, text in words.items() if name in names}
