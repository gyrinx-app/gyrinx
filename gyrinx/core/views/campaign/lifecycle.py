"""Campaign lifecycle management views (start, end, reopen, archive)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from gyrinx import messages
from gyrinx.core.handlers.campaign_operations import (
    campaign_start_group_key,
    handle_campaign_start,
)
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.core.utils import safe_redirect, toggle_membership
from gyrinx.tasks.groups import enqueue_in_group
from gyrinx.tracker import track
from gyrinx.core.views.campaign.common import get_campaign_admin_or_404


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
    campaign = get_campaign_admin_or_404(request, id)

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
                    list_count=len(result.stub_lists),
                )

                messages.success(
                    request,
                    f"Campaign has been started! {len(result.stub_lists)} "
                    "gang(s) are joining — they'll be ready in a moment.",
                )
        except ValidationError as e:
            messages.validation(request, e)

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_start_campaign():
        messages.error(request, "This campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Pre-campaign gangs are linked via the `lists` M2M; the `campaign` FK on List is only
    # populated when clones are created at start, so it must not be used here (see #1886).
    lists = campaign.lists.select_related("owner")

    return render(
        request,
        "core/campaign/campaign_start.html",
        {"campaign": campaign, "lists": lists},
    )


@login_required
@require_POST
def retry_campaign_list_clone(request, id, list_id):
    """Re-enqueue the background clone task for a gang stuck "joining" (#1222).

    Only a campaign admin (owner or shared admin) may retry. Idempotent:
    the clone task no-ops if the stub has since finished, so a double-click is harmless.
    """
    campaign = get_object_or_404(Campaign, id=id)
    if not campaign.is_admin(request.user):
        messages.error(
            request, "Only a campaign admin can retry a gang that's still joining."
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    stub = get_object_or_404(List, id=list_id, campaign=campaign)
    if not stub.is_cloning:
        messages.info(request, f"{stub.name} has already finished joining.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    if stub.original_list_id is None:
        messages.error(
            request,
            f"{stub.name} can't be retried automatically — its original gang is missing.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    original_list_id = str(stub.original_list_id)
    campaign_id = str(campaign.id)
    stub_id = str(stub.id)
    label = stub.name
    owner_id = str(campaign.owner_id)
    group_key = campaign_start_group_key(campaign_id)

    def _enqueue():
        from gyrinx.core.tasks import complete_campaign_list_clone

        try:
            # Same group as the original start, so the poller/status endpoint sees the retry.
            enqueue_in_group(
                complete_campaign_list_clone,
                group_key=group_key,
                label=label,
                stub_id=stub_id,
                original_list_id=original_list_id,
                campaign_id=campaign_id,
                user_id=owner_id,
            )
        except Exception as e:
            track(
                "task_enqueue_failed",
                stub_id=stub_id,
                campaign_id=campaign_id,
                error=str(e),
            )

    transaction.on_commit(_enqueue)
    track("campaign_list_clone_retry", campaign_id=campaign_id, list_id=stub_id)
    messages.success(request, f"Retrying {stub.name} — it'll be ready in a moment.")
    return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))


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
    campaign = get_campaign_admin_or_404(request, id)

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
    campaign = get_campaign_admin_or_404(request, id)

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
    campaign = get_campaign_admin_or_404(request, id)

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


@login_required
@require_POST
def toggle_campaign_pin(request, id):
    """
    Toggle whether the current user has pinned a :model:`core.Campaign`.

    Pins are private to each user and surface the campaign on their home page
    and on the campaigns page sidebar. Campaign admins and any participant (a
    user with a list in the campaign) may pin it. POST only; redirects back to where
    the request came from.
    """
    campaign = get_object_or_404(Campaign, id=id)
    if (
        not campaign.is_admin(request.user)
        and not campaign.lists.filter(owner=request.user).exists()
    ):
        raise Http404("Campaign not found")
    pinned = toggle_membership(campaign.pinned_by, request.user)
    track("campaign_pin_toggle", campaign_id=str(campaign.id), pinned=pinned)

    return safe_redirect(
        request,
        request.META.get("HTTP_REFERER"),
        fallback_url=reverse("core:campaign", args=(campaign.id,)),
    )


@login_required
@require_POST
def toggle_campaign_star(request, id):
    """
    Toggle whether the current user has starred a :model:`core.Campaign`.

    Stars are public and counted. Any logged-in user who can see the campaign
    may star it. POST only; redirects back to where the request came from.
    """
    campaign = get_object_or_404(Campaign, id=id)
    starred = toggle_membership(campaign.starred_by, request.user)
    track("campaign_star_toggle", campaign_id=str(campaign.id), starred=starred)

    return safe_redirect(
        request,
        request.META.get("HTTP_REFERER"),
        fallback_url=reverse("core:campaign", args=(campaign.id,)),
    )
