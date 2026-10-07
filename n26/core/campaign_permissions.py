"""Permission shared by campaign recording pages and their operations."""


def may_record_campaign(campaign, user):
    """The arbitrator and accepted players may record battles and dice rolls."""
    from n26.core.models import CampaignParticipant

    if user is None or not user.is_authenticated or campaign.archived:
        return False
    return (
        campaign.owner_id == user.pk
        or campaign.participants.filter(
            user=user, state=CampaignParticipant.State.ACCEPTED
        ).exists()
    )


def may_record_outcome(battle, user):
    """Whether this reader may record a battle's outcome on its own page.

    The arbitrator may, and so may an accepted player whose gang fought
    it, while no outcome is recorded. Changing an outcome once recorded,
    and everything else about a battle, stays with the arbitrator.
    """
    from n26.core.models import Battle

    if battle.result != Battle.Result.NOT_RECORDED:
        return False
    if not may_record_campaign(battle.campaign, user):
        return False
    return (
        battle.campaign.owner_id == user.pk or battle.gangs.filter(owner=user).exists()
    )
