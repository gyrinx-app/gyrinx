"""Campaign lifecycle management views (start, end, reopen, archive)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.handlers.campaign_operations import handle_campaign_start
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.tracker import track


@login_required
def start_campaign(request, id):
    """
    Start a campaign (transition from pre-campaign to in-progress).

    Only the campaign owner can start a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be started.

    **Template**

    :template:`core/campaign/campaign_start.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        try:
            with transaction.atomic():
                # Handle campaign start (creates ListActions and CampaignActions)
                result = handle_campaign_start(
                    user=request.user,
                    campaign=campaign,
                )

                # Log the campaign start event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="started",
                )

                track(
                    "campaign_started",
                    campaign_id=str(campaign.id),
                    list_count=len(result.list_results),
                )

                messages.success(
                    request,
                    f"Campaign has been started! {len(result.list_results)} gang(s) joined.",
                )
        except ValidationError as e:
            messages.validation(request, e)

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_start_campaign():
        messages.error(request, "This campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Prefetch lists with latest actions for efficient facts_with_fallback() in template
    lists = (
        List.objects.filter(campaign=campaign)
        .select_related("owner")
        .with_latest_actions()
    )

    return render(
        request,
        "core/campaign/campaign_start.html",
        {"campaign": campaign, "lists": lists},
    )


@login_required
def end_campaign(request, id):
    """
    End a campaign (transition from in-progress to post-campaign).

    Only the campaign owner can end a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be ended.

    **Template**

    :template:`core/campaign/campaign_end.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if campaign.end_campaign():
                # Log the campaign end action
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Ended: {campaign.name} has concluded",
                    outcome="Campaign transitioned from active to post-campaign status",
                )

                # Log the campaign end event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.DEACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="ended",
                )

                track("campaign_ended", campaign_id=str(campaign.id))

                messages.success(request, "Campaign has been ended!")
            else:
                messages.error(request, "Campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_end_campaign():
        messages.error(request, "This campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_end.html",
        {"campaign": campaign},
    )


@login_required
def reopen_campaign(request, id):
    """
    Reopen a campaign (transition from post-campaign back to in-progress).

    Only the campaign owner can reopen a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be reopened.

    **Template**

    :template:`core/campaign/campaign_reopen.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if campaign.reopen_campaign():
                # Log the campaign reopen action
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Reopened: {campaign.name} is active again",
                    outcome="Campaign transitioned from post-campaign back to active status",
                )

                # Log the campaign reopen event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="reopened",
                )

                track("campaign_reopened", campaign_id=str(campaign.id))

                messages.success(request, "Campaign has been reopened!")
            else:
                messages.error(request, "Campaign cannot be reopened.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_reopen_campaign():
        messages.error(request, "This campaign cannot be reopened.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_reopen.html",
        {"campaign": campaign},
    )


@login_required
def archive_campaign(request, id):
    """
    Archive or unarchive a :model:`core.Campaign`.

    Only the campaign owner can archive a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be archived or unarchived.

    **Template**

    :template:`core/campaign/campaign_archive.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if request.POST.get("archive") == "1":
                # Prevent archiving in-progress campaigns
                if campaign.is_in_progress:
                    messages.error(
                        request,
                        f"Cannot archive {campaign.name} while it is in progress. Please end the campaign first.",
                    )
                    return HttpResponseRedirect(
                        reverse("core:campaign", args=(campaign.id,))
                    )

                campaign.archive()

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Archived: {campaign.name} has been archived",
                    outcome="Campaign has been archived",
                )

                # Log the archive event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ARCHIVE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                )

                messages.success(request, "Campaign has been archived.")
            else:
                campaign.unarchive()

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Unarchived: {campaign.name} has been unarchived",
                    outcome="Campaign has been unarchived",
                )

                # Log the unarchive event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.RESTORE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                )

                messages.success(request, "Campaign has been unarchived.")

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_archive.html",
        {"campaign": campaign},
    )
