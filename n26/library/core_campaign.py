"""Seed the Territory campaign type and its standard content.

The type defines inherent Settlements and transferable Territories.
Its built-ins give joining gangs Reputation at one, Income at zero and a
Settlement. Asset modifiers contribute to Income; see design/campaign-assets.md.

Match natural keys case-insensitively and preserve existing records.
Accept historical classes and resolve renamed fields dynamically.
"""

from django.conf import settings

from n26.library.income import INCOME
from n26.library.possessions import build_in_missing

REPUTATION = "Reputation"
CAMPAIGN_TYPE = "Territory campaign"
#: The historical name matched by rename_core_campaign.
FORMER_NAME = "N26 core"
#: ``(label, plural, ownership, position)`` for each asset type the core
#: type has. The ownership is the stored value, which is the same
#: whichever name the field has on the class the seed is handed.
ASSET_TYPES = (
    ("Settlement", "Settlements", "held-one-each", 0),
    ("Territory", "Territories", "pooled", 1),
)
SETTLEMENT = "Settlement"
#: Named as ``authoring.add_built_in`` would name it, so the set reads
#: like every other type's on the authoring pages.
BUILT_INS = f"{CAMPAIGN_TYPE} built-ins"
FORMER_BUILT_INS = f"{FORMER_NAME} built-ins"

#: Original introductory copy shown during campaign setup.
DESCRIPTION = (
    "The core rulebook's campaign: gangs fight for control of Territory. "
    "Every gang keeps a Settlement it cannot lose and starts with one "
    "Territory drawn from the campaign's table. The "
    "campaign has three phases: Occupation, Downtime and Takeover. It ends "
    "with Triumphs awarded for the most Territories, the highest Reputation, "
    "the most battles fought, the most enemies taken out of action and the "
    "highest Wealth."
)
#: What a content author reads on the authoring pages.
LIBRARY_AUTHOR_HELP = (
    "The campaign type from the core rulebook. Settlement is a possession: "
    "every gang has its own. Territory is a holding: one gang "
    "holds it at a time. Add each Territory as an asset under that asset "
    "type, with its income in the Income box. "
    "Reputation at 1, Income at 0 and the Settlement are built in, so every "
    "gang that joins starts with all three."
)


def _asset_type_model(apps):
    """The asset type model, under whichever name the handed classes give it."""
    try:
        return apps.get_model("library", "AssetType")
    except LookupError:
        return apps.get_model("library", "AssetKind")


def _field(model, *names):
    """The first of ``names`` that is a field on ``model``."""
    have = {field.name for field in model._meta.get_fields()}
    return next(name for name in names if name in have)


def seed_core_campaign(apps):
    """Create what is missing of the Territory campaign type, and return
    one line per row created, so a caller can say what happened."""
    lines = []
    ContentPack = apps.get_model("library", "ContentPack")
    Counter = apps.get_model("library", "Counter")
    CampaignType = apps.get_model("library", "CampaignType")
    AssetType = _asset_type_model(apps)
    Asset = apps.get_model("library", "Asset")
    DefaultAssignmentSet = apps.get_model("library", "DefaultAssignmentSet")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    ownership_field = _field(AssetType, "ownership", "mode")
    asset_type_field = _field(Asset, "asset_type", "kind")

    pack, _ = ContentPack.objects.get_or_create(
        slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        defaults={"name": settings.DEFAULT_CONTENT_PACK_NAME},
    )

    counters = {}
    for counter_name in (REPUTATION, INCOME):
        counter = Counter.objects.filter(
            pack=pack, name__iexact=counter_name, qualifier=""
        ).first()
        if counter is None:
            counter = Counter.objects.create(pack=pack, name=counter_name)
            lines.append(f"created the {counter_name} counter")
        counters[counter_name] = counter

    campaign_type = CampaignType.objects.filter(
        pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
    ).first()
    if campaign_type is None:
        fields = {"pack": pack, "name": CAMPAIGN_TYPE}
        fields.update(_words_for(CampaignType))
        campaign_type = CampaignType.objects.create(**fields)
        lines.append(f"created the {CAMPAIGN_TYPE} campaign type")

    asset_types = {}
    for label, plural, ownership, position in ASSET_TYPES:
        asset_type = AssetType.objects.filter(
            campaign_type=campaign_type, label_singular__iexact=label
        ).first()
        if asset_type is None:
            asset_type = AssetType.objects.create(
                pack=pack,
                campaign_type=campaign_type,
                label_singular=label,
                label_plural=plural,
                position=position,
                **{ownership_field: ownership},
                **(
                    {"display_group": "Territories"}
                    if any(
                        field.name == "display_group"
                        for field in AssetType._meta.get_fields()
                    )
                    else {}
                ),
            )
            lines.append(f"created the {label} asset type")
        asset_types[label] = asset_type

    settlement = Asset.objects.filter(
        pack=pack, name__iexact=SETTLEMENT, qualifier=""
    ).first()
    if settlement is None:
        settlement = Asset.objects.create(
            pack=pack, name=SETTLEMENT, **{asset_type_field: asset_types[SETTLEMENT]}
        )
        lines.append(
            f"created the {SETTLEMENT} asset under the {SETTLEMENT} asset type"
        )

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

    def build_in_counter(counter_name, position):
        counter = counters[counter_name]
        if not members.filter(counter=counter).exists():
            DefaultAssignment.objects.create(
                pack=pack,
                default_set=built_ins,
                counter=counter,
                amount=1 if counter_name == REPUTATION else 0,
                position=position,
            )
            lines.append(f"built {counter_name} into {CAMPAIGN_TYPE}")

    # Keep Reputation, possessions and Income in display order.
    # The possession pass adds all missing possession assets, including the
    # Settlement on a fresh database.
    build_in_counter(REPUTATION, 0)
    for member in build_in_missing(apps, campaign_type):
        lines.append(f"built the {member.asset.name} into {CAMPAIGN_TYPE}")
    build_in_counter(INCOME, 2)
    if any(field.name == "minimum" for field in Counter._meta.get_fields()):
        lines.extend(seed_reputation_rules(apps))
    return lines


def rename_core_campaign(apps):
    """Rename a system campaign type and its default set when the target name is free.

    Populate only blank description and author-help fields, preserving authored
    text. Return report lines for each change.
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
    # Rename the built-in set to match its campaign type when that name is free.
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
    """Return description fields supported by the supplied historical model class."""
    names = {field.name for field in CampaignType._meta.get_fields()}
    words = {
        "description": DESCRIPTION,
        "library_author_help": LIBRARY_AUTHOR_HELP,
    }
    return {name: text for name, text in words.items() if name in names}


REPUTATION_INCOME = "Reputation income"


def seed_reputation_rules(apps):
    """Configure the system campaign without changing recorded gang values."""
    Counter = apps.get_model("library", "Counter")
    CampaignType = apps.get_model("library", "CampaignType")
    Modifier = apps.get_model("library", "Modifier")
    TargetsGang = apps.get_model("library", "TargetsGang")
    ContributesToCounter = apps.get_model("library", "ContributesToCounter")
    system = dict(pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG, qualifier="")
    reputation = Counter.objects.filter(**system, name__iexact=REPUTATION).first()
    income = Counter.objects.filter(**system, name__iexact=INCOME).first()
    campaign_type = CampaignType.objects.filter(
        **system, name__iexact=CAMPAIGN_TYPE
    ).first()
    if reputation is None or income is None or campaign_type is None:
        return []
    lines = []
    former_help = LIBRARY_AUTHOR_HELP.replace("Reputation at 1", "Reputation at 0")
    if campaign_type.library_author_help == former_help:
        campaign_type.library_author_help = LIBRARY_AUTHOR_HELP
        campaign_type.save(update_fields=["library_author_help"])
        lines.append("updated the Territory campaign authoring help")
    if reputation.minimum == 0:
        reputation.minimum = 1
        reputation.save(update_fields=["minimum"])
        lines.append("set the Reputation minimum to 1")
    if campaign_type.built_ins_id:
        changed = campaign_type.built_ins.members.filter(
            counter=reputation, amount=0
        ).update(amount=1)
        if changed:
            lines.append("set opening Reputation to 1")
    rule = Modifier.objects.filter(
        pack_id=reputation.pack_id, name__iexact=REPUTATION_INCOME
    ).first()
    if rule is None:
        scope = TargetsGang.objects.create(echoes=False)
        effect = ContributesToCounter.objects.create(
            counter=income, amount=10, per_counter=reputation
        )
        rule = Modifier.objects.create(
            pack_id=reputation.pack_id,
            name=REPUTATION_INCOME,
            targets_gang=scope,
            contributes_to_counter=effect,
        )
        lines.append("created Reputation income")
    elif (
        rule.contributes_to_counter_id is None
        or rule.contributes_to_counter.counter_id != income.pk
        or rule.contributes_to_counter.per_counter_id != reputation.pk
        or rule.contributes_to_counter.amount != 10
        or rule.targets_gang_id is None
    ):
        raise ValueError("Reputation income conflicts with existing content.")
    if not campaign_type.modifiers.filter(pk=rule.pk).exists():
        campaign_type.modifiers.add(rule)
        lines.append("added Reputation income to the Territory campaign")
    return lines
