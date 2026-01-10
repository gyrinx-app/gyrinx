"""Campaign battles views."""

from django.shortcuts import get_object_or_404, render

from gyrinx.core.models.campaign import Campaign


def campaign_battles(request, id):
    """
    View all battles in a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose battles are being viewed.
    ``battles``
        QuerySet of :model:`core.Battle` objects for this campaign.

    **Template**

    :template:`core/campaign/campaign_battles.html`
    """
    campaign = get_object_or_404(Campaign.objects.prefetch_related("lists"), id=id)

    battles = (
        campaign.battles.select_related("owner")
        .prefetch_related("participants", "winners")
        .order_by("-date", "-created")
    )

    return render(
        request,
        "core/campaign/campaign_battles.html",
        {
            "campaign": campaign,
            "battles": battles,
        },
    )
