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
