"""A possession is given to every gang without an author's step.

An asset of a Possession asset type — a Settlement, a home territory —
is something every gang in a campaign has its own of. The way a campaign
type gives anything to every gang that joins is its built-ins, so the
asset has to be a member of the type's built-in set; before this module
an author created the asset and then had to remember to add it there,
and a Settlement appeared twice on the type's page. Now creating the
asset builds it in, and deleting or archiving the asset takes it out.
The member is an ordinary ``DefaultAssignment`` naming the asset, so
joining, catch-up propagation and the gang sheet need nothing new.

Which campaign type gives an asset is decided by the asset's pack. An
asset in its asset type's own pack is given by that asset type's
campaign type: the system Settlement by the Territory campaign type, an
arbitrator's own asset type's asset by that campaign's additions type.
An asset written into a campaign's own pack under a *shared* asset type
is given by that campaign's additions type instead — building it into
the shared type would hand one campaign's asset to every campaign
founded on it.

``authoring.create_asset`` applies the rule to live models and files
the propagation pass. ``build_in_missing`` applies it to whatever
already stands, written against the model classes it is handed so the
seed and a data migration can run it on historical ones.
"""

from itertools import chain, count

from django.core.exceptions import FieldError
from django.db.models import Max

#: The stored value of ``AssetType.Ownership.POSSESSION``, spelt out so
#: this can run against historical model classes, which carry no enum.
POSSESSION = "held-one-each"


def giver_of(asset, apps):
    """The campaign type whose built-ins give this asset, or None where
    nothing does.

    The asset type's own campaign type when the asset is in that type's
    pack; otherwise the additions type of the campaign whose pack the
    asset is in. An asset in a pack no campaign owns and no campaign
    type shares is nobody's to give. ``apps`` is asked for the campaign
    model only on that second path, so the seed can run on a historical
    state from before campaigns had a pack.
    """
    campaign_type = asset.asset_type.campaign_type
    if campaign_type.pack_id == asset.pack_id:
        return campaign_type
    try:
        Campaign = apps.get_model("n26", "Campaign")
        campaign = (
            Campaign.objects.filter(pack_id=asset.pack_id)
            .select_related("additions")
            .first()
        )
    except LookupError, FieldError:
        return None
    return campaign.additions if campaign is not None else None


def _field(model, *names):
    """The first of ``names`` that is a field on ``model`` — the asset
    type and its ownership took their present names in a later
    migration than the one that first runs the seed."""
    have = {field.name for field in model._meta.get_fields()}
    return next(name for name in names if name in have)


def build_in_missing(apps, campaign_type=None):
    """Build every possession asset into its giver's built-ins where no
    live member names it, and return the members made.

    Idempotent: an asset already given is left alone, so this can run
    over a database that has some of it. Archived assets are skipped —
    an archived asset is one taken out on purpose. ``campaign_type``
    narrows to the assets of one type's asset types, for the seed.

    Members are written directly rather than through the authoring
    verb, because the classes handed in may be historical ones; the
    caller files whatever propagation the sets that changed are owed.
    """
    Asset = apps.get_model("library", "Asset")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    DefaultAssignmentSet = apps.get_model("library", "DefaultAssignmentSet")
    asset_type_field = _field(Asset, "asset_type", "kind")
    AssetType = Asset._meta.get_field(asset_type_field).related_model
    ownership_field = _field(AssetType, "ownership", "mode")

    assets = Asset.objects.filter(
        **{f"{asset_type_field}__{ownership_field}": POSSESSION}, archived=False
    ).select_related(f"{asset_type_field}__campaign_type")
    if campaign_type is not None:
        assets = assets.filter(**{f"{asset_type_field}__campaign_type": campaign_type})

    made = []
    for asset in assets.order_by("name"):
        # Read through one name whichever the class uses, so the rest of
        # the pass need not know which migration it is running in.
        if asset_type_field != "asset_type":
            asset.asset_type = getattr(asset, asset_type_field)
        giver = giver_of(asset, apps)
        if giver is None:
            continue
        built_ins = _built_ins_of(giver, DefaultAssignmentSet)
        if built_ins.members.filter(asset=asset, archived=False).exists():
            continue
        last = built_ins.members.aggregate(last=Max("position"))["last"]
        made.append(
            DefaultAssignment.objects.create(
                pack_id=asset.pack_id,
                default_set=built_ins,
                asset=asset,
                position=0 if last is None else last + 1,
            )
        )
    return made


def _built_ins_of(campaign_type, DefaultAssignmentSet):
    """The type's built-in set, founded in the type's pack where it has
    none yet — named as the authoring verb names one, so it reads like
    every other type's on the authoring pages."""
    if campaign_type.built_ins_id is not None:
        return campaign_type.built_ins
    taken = DefaultAssignmentSet.objects.filter(pack_id=campaign_type.pack_id)
    tries = chain(
        (
            f"{campaign_type.name} built-ins",
            f"{campaign_type.name} (campaign type) built-ins",
        ),
        (f"{campaign_type.name} (campaign type) built-ins {n}" for n in count(2)),
    )
    name = next(
        option for option in tries if not taken.filter(name__iexact=option).exists()
    )
    built_ins = DefaultAssignmentSet.objects.create(
        pack_id=campaign_type.pack_id, name=name
    )
    campaign_type.built_ins = built_ins
    campaign_type.save(update_fields=["built_ins"])
    return built_ins
