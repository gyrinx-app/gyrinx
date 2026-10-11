"""Gang progress within a campaign cycle."""


def pending_gangs(cycle):
    return list(
        cycle.campaign.memberships.filter(left__isnull=True)
        .select_related("gang")
        .order_by("gang__name")
    )
