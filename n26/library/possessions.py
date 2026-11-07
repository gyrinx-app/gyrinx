"""Give enabled inherent assets through campaign-type built-in sets.

Joining and catch-up propagation create each gang's assignment. Disabling
distribution, deleting or archiving an asset stops future defaults while
preserving existing assignments.

Assets in the asset type's pack use its campaign type as giver. Assets in
a campaign's own pack use that campaign's additions type, even when their
asset type is shared. This prevents campaign-specific content reaching other
campaigns. ``build_in_missing`` accepts historical model classes.
"""

from itertools import chain, count

from django.apps import apps as live_models
from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models import Max

#: The stored value of ``AssetType.Ownership.POSSESSION``, spelt out so
#: this can run against historical model classes, which carry no enum.
POSSESSION = "held-one-each"


def giver_of(asset, apps):
    """Resolve the campaign type giving an asset, or return ``None``.

    Use the asset type's campaign type when packs match. Otherwise look for the
    additions type of the campaign owning the asset's pack. Query the campaign
    model only on that path to support older historical states.
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


@transaction.atomic
def give_back(asset):
    """Restore automatic distribution of an eligible unarchived inherent asset.

    Revive an archived membership to preserve provenance and prevent duplicate
    catch-up grants. Create a new membership only if no archived one remains.
    Skip assets already distributed, archived, transferable or disabled.
    """
    from n26.core.propagation import file_propagation_task
    from n26.library.authoring import add_built_in
    from n26.library.models import AssetType, DefaultAssignment

    if (
        asset.asset_type.ownership != AssetType.Ownership.POSSESSION
        or not asset.given_to_every_gang
        or asset.archived
    ):
        return
    members = DefaultAssignment.objects.filter(asset=asset)
    if members.filter(archived=False).exists():
        return
    revived = list(members.filter(archived=True))
    for member in revived:
        member.unarchive()
        file_propagation_task(member.default_set)
    if revived:
        return
    giver = giver_of(asset, live_models)
    if giver is not None:
        add_built_in(giver, asset, pack=asset.pack)


def _field(model, *names):
    """Resolve the first available field name across supported historical model states."""
    have = {field.name for field in model._meta.get_fields()}
    return next(name for name in names if name in have)


def build_in_missing(apps, campaign_type=None):
    """Create missing live built-in memberships for eligible inherent assets.

    Return created members so the caller can schedule propagation. Skip archived
    assets and existing live memberships. ``campaign_type`` optionally limits
    the pass. Write directly to support historical model classes.
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

    if any(field.name == "given_to_every_gang" for field in Asset._meta.fields):
        assets = assets.filter(given_to_every_gang=True)

    made = []
    # Reuse one campaign type instance per giver so its newly created built-in
    # set is visible when processing subsequent assets.
    givers = {}
    for asset in assets.order_by("name"):
        # Normalise historical field names for the remainder of the pass.
        if asset_type_field != "asset_type":
            asset.asset_type = getattr(asset, asset_type_field)
        giver = giver_of(asset, apps)
        if giver is None:
            continue
        giver = givers.setdefault(giver.pk, giver)
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
    """Find or create the campaign type's named built-in set in its own pack."""
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
