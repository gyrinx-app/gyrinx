"""Campaign CRUD views."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core.forms.campaign import EditCampaignForm, NewCampaignForm
from gyrinx.core.models.campaign import Campaign, CampaignResourceType
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.tracker import track


@login_required
def new_campaign(request):
    """
    Create a new :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A NewCampaignForm for entering the name and details of the new campaign.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_new.html`
    """
    error_message = None
    if request.method == "POST":
        form = NewCampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.owner = request.user
            campaign.save()

            # Automatically create a "Reputation" resource type for all campaigns
            CampaignResourceType.objects.create(
                campaign=campaign,
                name="Reputation",
                description="Gang reputation gained during the campaign",
                default_amount=1,
                owner=request.user,
            )

            # Log the campaign creation event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.CREATE,
                object=campaign,
                request=request,
                campaign_name=campaign.name,
                public=campaign.public,
            )

            track("campaign_created", campaign_id=str(campaign.id))

            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = NewCampaignForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/campaign/campaign_new.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def edit_campaign(request, id):
    """
    Edit an existing :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A EditCampaignForm for editing the campaign's details.
    ``campaign``
        The :model:`core.Campaign` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditCampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            # Pass user to save() for phase change logging
            updated_campaign = form.save(user=request.user)

            # Log the campaign update event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.UPDATE,
                object=updated_campaign,
                request=request,
                campaign_name=updated_campaign.name,
            )

            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = EditCampaignForm(instance=campaign)

    return render(
        request,
        "core/campaign/campaign_edit.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )
