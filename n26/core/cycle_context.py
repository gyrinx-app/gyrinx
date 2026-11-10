"""Pinned cycle attribution shared by action records and their ledger effects.

Admit a new context before taking gang locks. Later action lifecycle steps use
its saved identity without resolving the gang's current membership or acquiring
another campaign lock. A context grants no rewards or per-cycle allowances.
"""

from dataclasses import dataclass

from n26 import flags
from n26.core.fields import to_ulid
from n26.core.models import Campaign, CampaignCycle, CampaignMembership
from n26.core.operations import Refusal


@dataclass(frozen=True)
class CycleContext:
    campaign_id: str
    cycle_id: str

    @classmethod
    def from_cycle(cls, cycle):
        return cls(str(cycle.campaign_id), str(cycle.pk))

    def resolve(self):
        try:
            campaign_id, cycle_id = to_ulid(self.campaign_id), to_ulid(self.cycle_id)
        except ValueError:
            raise Refusal("Select a cycle from this campaign.") from None
        cycle = (
            CampaignCycle.objects.select_related("phase")
            .filter(pk=cycle_id, campaign_id=campaign_id)
            .first()
        )
        if cycle is None:
            raise Refusal("Select a cycle from this campaign.")
        return cycle


def lock_campaign(context, actor):
    """Called inside the operation transaction, before any gang is locked."""
    if not isinstance(context, CycleContext):
        raise Refusal("Select a cycle from this campaign.")
    if not flags.enabled(flags.CYCLE_TRACKING, actor):
        raise Refusal("Cycle tracking is not available to this account.")
    try:
        identity = to_ulid(context.campaign_id)
    except ValueError:
        raise Refusal("Select a cycle from this campaign.") from None
    campaign = (
        Campaign.objects.select_for_update(no_key=True).filter(pk=identity).first()
    )
    if campaign is None or campaign.archived:
        raise Refusal("Select a cycle from this campaign.")
    return context.resolve()


def require_membership(cycle, gang):
    if (
        gang is None
        or not CampaignMembership.objects.filter(
            campaign_id=cycle.campaign_id, gang=gang, left__isnull=True
        ).exists()
    ):
        raise Refusal("Select a cycle from the gang's current campaign.")
