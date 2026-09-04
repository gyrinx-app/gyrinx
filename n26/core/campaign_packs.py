"""Give every campaign what founding writes, and every playing gang what
joining writes.

A campaign is founded on a type and owns a pack holding its additions
type (``CampaignOperation.found``); a gang that joins is assigned both
types, with the shared type's built-ins landing caused by its carrier
(``Operation.join_campaign``). Campaigns and memberships written before
either existed have none of it, and this fills the gap: each campaign
missing a type is put on the **N26 core** type, the one type every
install has and the only thing a campaign could have been played as
before there was a choice; each missing a pack or an additions type is
given one, named for the campaign as founding names them; and each open
membership missing a carrier is given it, with the type's built-ins
landed and a Reputation counter opening at its member's amount.

The assignments are written here rather than through an operation
because a migration runs on historical model classes, which an operation
cannot drive. What is written is the shape ``Operation.assign`` and
``reconcile_defaults`` give a free gang-hosted grant: the assignment with
its roots set, a zero-priced ledger entry, a granted event naming the
campaign, and provenance on every built-in copy so a later propagation
pass recognises them as satisfied. Nothing is priced, so no gang's rating
or credits move and the ledger still reconciles.

What an operation does beyond writing rows is not done here: no stored
effect runs, and a weapon lands without its free firing lines. Nor are
two shapes of built-in followed: an extra firing line, which needs a gun
to land on, and a built-in with built-ins of its own. None of these is
in the N26 core type, whose built-ins are a counter and an asset. Each
is reported rather than half-written, and the propagation pass catches
up whatever it can.

Everything is matched on what already stands and left alone if it is
there, so running this twice changes nothing the second time. Written
against whatever model classes it is handed, so a migration can run it
on historical ones.
"""

from uuid import uuid4

from django.conf import settings

from n26.core.models.ledger import Reason
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

#: ``LedgerEvent.Kind.GRANTED``, by value: the history's word for a thing
#: that arrived because something else brought it.
GRANTED = "granted"


def give_campaigns_their_packs(apps):
    """Fill in what founding and joining write, for every campaign, and
    return one line per row created, so a caller can say what happened."""
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
    """The N26 core campaign type, created along with the rest of the core
    campaign content if a database lacks it."""
    CampaignType = apps.get_model("library", "CampaignType")

    def find():
        return CampaignType.objects.filter(
            pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
            name__iexact=CAMPAIGN_TYPE,
            qualifier="",
        ).first()

    core = find()
    if core is None:
        seed_core_campaign(apps)
        core = find()
    return core


def _carry(apps, membership, campaign_type, batch, lines):
    """One campaign type onto one gang, with its built-ins, as joining
    writes it. Returns the carrier."""
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
                f"{campaign_type.name}: a built-in firing line for "
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
        thing = getattr(member, field)
        if getattr(thing, "built_ins_id", None) is not None:
            lines.append(
                f"{campaign_type.name}: {thing} has built-ins of its own, "
                f"not landed for {gang.name}"
            )
    return carrier


def _grant(apps, membership, batch, reason, **fields):
    """One free gang-hosted assignment with its entry and event — what
    ``Operation.assign`` writes for a grant, on historical classes."""
    Assignment = apps.get_model("n26", "Assignment")
    LedgerEntry = apps.get_model("n26", "LedgerEntry")
    LedgerEvent = apps.get_model("n26", "LedgerEvent")

    gang = membership.gang
    # The roots are derived by the live model's save and by nothing else,
    # so a gang-hosted assignment written here names its gang as its root
    # by hand.
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


def _names(member):
    """Which assignable column this set member fills, or None."""
    for field in DEFAULT_ASSIGNABLE_FIELDS:
        if getattr(member, f"{field}_id", None) is not None:
            return field
    return None
