"""Fill missing campaign types, owned packs, additions and membership carriers.

Use the Territory campaign type for campaigns without one. Create missing
packs and additions using founding's naming rules. Give open memberships
their missing shared-type and additions carriers, including built-ins and
counter opening values.

Accept historical model classes for migrations. Write the free gang-hosted
assignment shape directly: roots, zero-valued ledger entry, campaign-linked
grant event and member provenance. These writes move no credits or rating.

Do not run stored effects, create free weapon profiles, or recursively
materialise nested built-ins. Report omitted extra ammunition and nested grants instead of attempting them. The standard Territory type
requires none of these shapes. Existing objects remain unchanged on rerun.
"""

from uuid import uuid4

from django.conf import settings

from n26.core.models.ledger import Reason
from n26.library.core_campaign import (
    CAMPAIGN_TYPE,
    FORMER_NAME,
    seed_core_campaign,
)
from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

#: ``LedgerEvent.Kind.GRANTED``, by value: the history's word for a thing
#: that arrived because something else brought it.
GRANTED = "granted"


def give_campaigns_their_packs(apps):
    """Create missing founding and joining structures and return a creation report."""
    lines = []
    Campaign = apps.get_model("n26", "Campaign")
    CampaignMembership = apps.get_model("n26", "CampaignMembership")
    ContentPack = apps.get_model("library", "ContentPack")
    CampaignType = apps.get_model("library", "CampaignType")

    core = None
    for campaign in Campaign.objects.order_by("created"):
        changed = []
        if campaign.campaign_type_id is None:
            core = core or _core_type(apps)
            campaign.campaign_type = core
            changed.append("campaign_type")
        if campaign.pack_id is None:
            campaign.pack = ContentPack.objects.create(
                name=campaign.name,
                slug=f"campaign-{str(campaign.pk).lower()}",
                owner_id=campaign.owner_id,
            )
            changed.append("pack")
        if campaign.additions_id is None:
            campaign.additions = CampaignType.objects.create(
                pack=campaign.pack, name=campaign.name
            )
            changed.append("additions")
        if changed:
            campaign.save(update_fields=[*changed, "modified"])
            lines.append(f"{campaign.name}: set {', '.join(changed)}")

        playing = CampaignMembership.objects.filter(
            campaign=campaign, left__isnull=True
        ).select_related("gang")
        for membership in playing:
            carried = []
            batch = uuid4()
            if membership.type_carrier_id is None:
                membership.type_carrier = _carry(
                    apps, membership, campaign.campaign_type, batch, lines
                )
                carried.append("type_carrier")
            if membership.additions_carrier_id is None:
                membership.additions_carrier = _carry(
                    apps, membership, campaign.additions, batch, lines
                )
                carried.append("additions_carrier")
            if carried:
                membership.save(update_fields=[*carried, "modified"])
                lines.append(
                    f"{campaign.name}: {membership.gang.name} now carries "
                    f"{', '.join(carried)}"
                )
    return lines


def _core_type(apps):
    """Find or create the standard Territory type, recognising its stored alias."""
    CampaignType = apps.get_model("library", "CampaignType")

    def find():
        system = CampaignType.objects.filter(
            pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG, qualifier=""
        )
        return (
            system.filter(name__iexact=CAMPAIGN_TYPE).first()
            or system.filter(name__iexact=FORMER_NAME).first()
        )

    core = find()
    if core is None:
        seed_core_campaign(apps)
        core = find()
    return core


def _carry(apps, membership, campaign_type, batch, lines):
    """Create a campaign type carrier and supported built-ins for a gang."""
    Assignment = apps.get_model("n26", "Assignment")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    CounterValue = apps.get_model("n26", "CounterValue")

    gang = membership.gang
    carrier = _grant(
        apps, membership, batch, Reason.GRANTED, campaign_type=campaign_type
    )
    if campaign_type.built_ins_id is None:
        return carrier

    members = DefaultAssignment.objects.filter(
        default_set_id=campaign_type.built_ins_id, archived=False
    ).order_by("position")
    for member in members:
        field = _names(member)
        if field is None or field == "weapon_profile":
            lines.append(
                f"{campaign_type.name}: a built-in weapon profile for "
                f"{gang.name} was not landed — nothing here is its gun"
            )
            continue
        if field == "slot" and member.default_pickable_id is not None:
            lines.append(
                f"{campaign_type.name}: a built-in slot with a starting pick "
                f"for {gang.name} was landed without its pick"
            )
        if Assignment.objects.filter(
            materialised_from=member, materialised_for=carrier
        ).exists():
            continue
        copy = _grant(
            apps,
            membership,
            batch,
            Reason.DEFAULT,
            caused_by=carrier,
            materialised_from=member,
            materialised_for=carrier,
            **{f"{field}_id": getattr(member, f"{field}_id")},
        )
        if field == "counter":
            CounterValue.objects.create(assignment=copy, value=member.amount)
            _open_counter(apps, membership, copy, member.amount, batch)
        thing = getattr(member, field)
        if getattr(thing, "built_ins_id", None) is not None:
            lines.append(
                f"{campaign_type.name}: {thing} has built-ins of its own, "
                f"not landed for {gang.name}"
            )
    return carrier


def _grant(apps, membership, batch, reason, **fields):
    """Write a free gang-hosted assignment with its entry and event using historical models."""
    Assignment = apps.get_model("n26", "Assignment")
    LedgerEntry = apps.get_model("n26", "LedgerEntry")
    LedgerEvent = apps.get_model("n26", "LedgerEvent")

    gang = membership.gang
    # Historical saves cannot derive roots; set the gang root explicitly.
    assignment = Assignment.objects.create(gang=gang, gang_root=gang, **fields)
    LedgerEntry.objects.create(assignment=assignment, reason=reason)
    LedgerEvent.objects.create(
        assignment=assignment,
        gang=gang,
        campaign_id=membership.campaign_id,
        kind=GRANTED,
        batch=batch,
    )
    return assignment


def _open_counter(apps, membership, assignment, value, batch):
    """Write an opening only when the counter journal is active."""
    try:
        CounterTracking = apps.get_model("n26", "CounterTracking")
    except LookupError:
        # Historical states without tracking leave openings to activation.
        return
    if not CounterTracking.objects.filter(pk=1, activated_at__isnull=False).exists():
        return
    LedgerEvent = apps.get_model("n26", "LedgerEvent")
    LedgerEvent.objects.create(
        assignment=assignment,
        gang=membership.gang,
        campaign_id=membership.campaign_id,
        kind="counter_opened",
        batch=batch,
        counter_before=0,
        counter_delta=value,
        counter_after=value,
    )


def _names(member):
    """Which assignable column this set member fills, or None."""
    for field in DEFAULT_ASSIGNABLE_FIELDS:
        if getattr(member, f"{field}_id", None) is not None:
            return field
    return None
