from django.shortcuts import get_object_or_404
from django.views import generic

from gyrinx.core.models.campaign import Campaign


class Campaigns(generic.ListView):
    template_name = "core/campaign/campaigns.html"
    context_object_name = "campaigns"

    def get_queryset(self):
        return Campaign.objects.filter(public=True)


class CampaignDetailView(generic.DetailView):
    """
    Display a single :model:`core.Campaign` object.

    **Context**

    ``campaign``
        The requested :model:`core.Campaign` object.

    **Template**

    :template:`core/campaign/campaign.html`
    """

    template_name = "core/campaign/campaign.html"
    context_object_name = "campaign"

    def get_object(self):
        """
        Retrieve the :model:`core.Campaign` by its `id`.
        """
        return get_object_or_404(Campaign, id=self.kwargs["id"])
