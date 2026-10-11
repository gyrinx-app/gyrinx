"""Manual campaign progression, recorded under the campaign operation."""

from django.db.models import Max
from django.utils import timezone

from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignCycle, CampaignEvent
from n26.core.operations import Refusal


def current_cycle(campaign):
    return campaign.cycles.filter(ended__isnull=True).first()


def start_cycle(campaign, *, actor, name="", previous=None, leave_pending=False):
    with campaign_operation(campaign, actor=actor) as act:
        _may_manage(campaign, actor)
        active = current_cycle(campaign)
        if (str(active.pk) if active else None) != previous:
            raise Refusal(
                "The current cycle changed. Refresh the page before continuing."
            )
        if active:
            from n26.core.cycle_rewards import pending_gangs

            if pending_gangs(active) and not leave_pending:
                raise Refusal(
                    "Review the unapplied boons or confirm that they will stay unapplied."
                )
            active.ended = timezone.now()
            active.save(update_fields=["ended", "modified"])
        number = (campaign.cycles.aggregate(value=Max("number"))["value"] or 0) + 1
        cycle = CampaignCycle(campaign=campaign, number=number, name=name.strip())
        cycle.full_clean()
        cycle.save()
        act.event(CampaignEvent.Kind.CYCLE_STARTED, note=cycle.label)
        return cycle


def rename_cycle(cycle, *, actor, name):
    with campaign_operation(cycle.campaign, actor=actor) as act:
        _may_manage(act.campaign, actor)
        cycle.refresh_from_db()
        if cycle.ended is not None:
            raise Refusal("This cycle has ended. You can rename the current cycle.")
        was = cycle.label
        cycle.name = name.strip()
        cycle.full_clean()
        cycle.save(update_fields=["name", "modified"])
        act.event(CampaignEvent.Kind.CYCLE_RENAMED, note=f"{was} → {cycle.label}")
        return cycle


def _may_manage(campaign, actor):
    if actor is None or campaign.owner_id != actor.pk:
        raise Refusal("Only the campaign arbitrator can manage its cycles.")
    if campaign.archived:
        raise Refusal("You cannot change an archived campaign's cycles.")
