"""Who may record one gang's crew or results, independent of page layout."""


def may_record_gang(*, gang, actor, campaign=None, active_gang_ids=None):
    """Owners keep authority; an arbitrator's authority ends when the gang leaves."""
    if not actor or not actor.is_authenticated or gang.archived:
        return False
    if campaign is not None and campaign.archived:
        return False
    if gang.owner_id == actor.pk:
        return True
    if campaign is None or campaign.owner_id != actor.pk:
        return False
    if active_gang_ids is not None:
        return gang.pk in active_gang_ids
    return gang.campaign_memberships.filter(
        campaign=campaign, left__isnull=True
    ).exists()
