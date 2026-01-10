"""Campaign list management views."""

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.invitation import CampaignInvitation
from gyrinx.core.models.list import List
from gyrinx.tracker import track


@login_required
def campaign_add_lists(request, id):
    """
    Add lists to a campaign.

    Allows the campaign owner to search for and add lists to their campaign.
    Only available for campaigns in pre-campaign or in-progress status.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being edited.
    ``lists``
        Available :model:`core.List` objects that can be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_add_lists.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Check if campaign is in a state where lists can be added
    if campaign.is_post_campaign:
        messages.error(request, "Lists cannot be added to a completed campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        if list_id:
            try:
                list_to_add = List.objects.get(id=list_id)
                # Check if user can add this list (either owner or public)
                if list_to_add.owner == request.user or list_to_add.public:
                    # Check if list is in campaign mode (cannot be cloned-from)
                    if list_to_add.status == List.CAMPAIGN_MODE:
                        error_message = (
                            "Lists in campaign mode cannot be added to other campaigns."
                        )
                    else:
                        # Check if an invitation already exists
                        invitation, created = CampaignInvitation.objects.get_or_create(
                            campaign=campaign,
                            list=list_to_add,
                            defaults={"owner": request.user},
                        )

                        # Check for auto-accept condition (same owner)
                        if campaign.owner == list_to_add.owner:
                            # If invitation was declined, reset to pending so it can be accepted
                            if invitation.is_declined:
                                invitation.status = CampaignInvitation.PENDING
                                invitation.save()  # Required to persist the status change

                            # Try to accept the invitation
                            if invitation.accept():
                                messages.success(
                                    request,
                                    f"{list_to_add.name} has been added to the campaign.",
                                )

                                # Log the auto-accept event regardless of whether the invitation was just created
                                log_event(
                                    user=request.user,
                                    noun=EventNoun.CAMPAIGN_INVITATION,
                                    verb=EventVerb.CREATE
                                    if created
                                    else EventVerb.UPDATE,
                                    object=invitation,
                                    request=request,
                                    campaign_name=campaign.name,
                                    list_invited_id=str(list_to_add.id),
                                    list_invited_name=list_to_add.name,
                                    list_owner=list_to_add.owner.username,
                                    action="invitation_auto_accepted",
                                )

                                track(
                                    "campaign_list_added",
                                    campaign_id=str(campaign.id),
                                )
                            else:
                                # If accept() returned False, the invitation was already accepted
                                if (
                                    invitation.is_accepted
                                    and list_to_add in campaign.lists.all()
                                ):
                                    messages.info(
                                        request,
                                        f"{list_to_add.name} is already in the campaign.",
                                    )
                                else:
                                    # Should not happen if we handled declined above, but fallback
                                    messages.info(
                                        request, f"Could not add {list_to_add.name}."
                                    )

                        elif created:
                            # Log the invitation creation event
                            log_event(
                                user=request.user,
                                noun=EventNoun.CAMPAIGN_INVITATION,
                                verb=EventVerb.CREATE,
                                object=invitation,
                                request=request,
                                campaign_name=campaign.name,
                                list_invited_id=str(list_to_add.id),
                                list_invited_name=list_to_add.name,
                                list_owner=list_to_add.owner.username,
                                action="invitation_sent",
                            )

                            # Show success message
                            messages.success(
                                request,
                                f"Invitation sent to {list_to_add.name}.",
                            )
                        else:
                            # Check if the invitation is still pending
                            if invitation.is_pending:
                                messages.info(
                                    request,
                                    f"An invitation for {list_to_add.name} is already pending.",
                                )
                            elif invitation.is_accepted:
                                # Check if the list is actually in the campaign
                                if list_to_add in campaign.lists.all():
                                    messages.info(
                                        request,
                                        f"{list_to_add.name} has already accepted the invitation and is in the campaign.",
                                    )
                                else:
                                    # List was removed, reset invitation to pending
                                    invitation.status = CampaignInvitation.PENDING
                                    invitation.save()
                                    messages.success(
                                        request,
                                        f"Invitation re-sent to {list_to_add.name}.",
                                    )
                            elif invitation.is_declined:
                                # Reset declined invitation to pending
                                invitation.status = CampaignInvitation.PENDING
                                invitation.save()
                                messages.success(
                                    request,
                                    f"Invitation re-sent to {list_to_add.name}.",
                                )
                        # Redirect to the same page with the search params preserved
                        query_params = []
                        if request.GET.get("q"):
                            query_params.append(f"q={request.GET.get('q')}")
                        if request.GET.get("owner"):
                            query_params.append(f"owner={request.GET.get('owner')}")
                        query_str = "&".join(query_params)
                        return HttpResponseRedirect(
                            reverse("core:campaign-add-lists", args=(campaign.id,))
                            + (f"?{query_str}" if query_str else "")
                        )
                else:
                    error_message = "You can only add your own lists or public lists."
            except List.DoesNotExist:
                error_message = "List not found."

    # Get lists that can be added (user's own lists or public lists)
    # Only show lists in list building mode and not archived
    lists = List.objects.filter(
        (models.Q(owner=request.user) | models.Q(public=True))
        & models.Q(status=List.LIST_BUILDING)
        & models.Q(archived=False)
    )

    # When we show the set of available lists, we want to exclude those that are already
    # in the campaign, and those that have pending/accepted invitations.

    # First, get the most recent invitation for each list to this campaign

    # Subquery to get the most recent invitation's ID for each list
    most_recent_invitation = (
        CampaignInvitation.objects.filter(campaign=campaign, list=OuterRef("list_id"))
        .order_by("-created")
        .values("id")[:1]
    )

    # Get the list IDs where the most recent invitation is pending
    pending_invitation_list_ids = CampaignInvitation.objects.filter(
        id__in=Subquery(most_recent_invitation),
        status=CampaignInvitation.PENDING,
    ).values_list("list_id", flat=True)

    # Exclude both pending invitations and lists that are already in the campaign
    excluded_list_ids = list(pending_invitation_list_ids)

    # If the campaign has started, exclude lists that have been cloned into it
    if campaign.is_in_progress or campaign.is_post_campaign:
        # The campaign lists have original_list pointing to the source lists
        cloned_original_ids = campaign.lists.values_list("original_list_id", flat=True)
        lists = lists.exclude(id__in=cloned_original_ids)
    else:
        # Pre-campaign: exclude lists that are directly added
        lists = lists.exclude(id__in=campaign.lists.values_list("id", flat=True))

    # Apply search filter if provided
    if request.GET.get("q"):
        search_query = SearchQuery(request.GET.get("q"))
        lists = lists.annotate(
            search=SearchVector("name", "content_house__name", "owner__username")
        ).filter(Q(search=search_query) | Q(name__icontains=request.GET.get("q")))

    # Filter by owner type
    owner_filter = request.GET.get("owner", "all")
    if owner_filter == "mine":
        lists = lists.filter(owner=request.user)
    elif owner_filter == "others":
        # Only show public lists from other users
        lists = lists.filter(public=True).exclude(owner=request.user)

    # Exclude and order by name, prefetch latest actions for facts system
    lists = (
        lists.exclude(id__in=excluded_list_ids)
        .with_latest_actions()
        .select_related("content_house", "owner")
        .order_by("name")
    )

    # Paginate the results
    paginator = Paginator(lists, 20)  # Show 20 lists per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get current campaign lists for display
    current_lists = campaign.lists.select_related("owner", "content_house").order_by(
        "name"
    )

    # Get pending invitations for display
    pending_invitations = (
        CampaignInvitation.objects.filter(
            campaign=campaign, status=CampaignInvitation.PENDING
        )
        .select_related("list", "list__owner", "list__content_house")
        .order_by("-created")
    )

    return render(
        request,
        "core/campaign/campaign_add_lists.html",
        {
            "campaign": campaign,
            "lists": page_obj,  # Pass the page object instead of the full queryset
            "page_obj": page_obj,  # Also pass page_obj for pagination controls
            "error_message": error_message,
            "current_lists": current_lists,
            "pending_invitations": pending_invitations,
        },
    )


@login_required
@transaction.atomic
def campaign_remove_list(request, id, list_id):
    """
    Remove a list from a campaign.

    Allows the campaign owner or list owner to remove a list from a campaign.
    The list is disconnected from the campaign and archived if in campaign mode.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being edited.
    ``list``
        The :model:`core.List` being removed.

    **Template**

    :template:`core/campaign/campaign_remove_list.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    list_to_remove = get_object_or_404(List, id=list_id)

    # Check permissions - campaign owner or list owner can remove
    if request.user != campaign.owner and request.user != list_to_remove.owner:
        messages.error(
            request, "You don't have permission to remove this list from the campaign."
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if the list is actually in this campaign
    if list_to_remove not in campaign.lists.all():
        messages.error(request, "This list is not in this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Don't allow removal from post-campaign
    if campaign.is_post_campaign:
        messages.error(request, "Lists cannot be removed from a completed campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    if request.method == "POST":
        # Store list info for logging before removal
        list_name = list_to_remove.name
        list_house = (
            list_to_remove.content_house.name if list_to_remove.content_house else ""
        )
        list_owner_username = list_to_remove.owner.username

        # Un-assign any campaign assets held by this list
        assets_unassigned_count = 0
        for asset in CampaignAsset.objects.filter(
            holder=list_to_remove, asset_type__campaign=campaign
        ):
            asset.holder = None
            asset.save()
            assets_unassigned_count += 1

        # Create campaign action for list removal
        CampaignAction.objects.create(
            campaign=campaign,
            user=request.user,
            list=list_to_remove,
            description=f"Gang '{list_name}' has been removed from the campaign by {request.user.username}",
            owner=request.user,
        )

        # Remove the list from the campaign
        campaign.lists.remove(list_to_remove)

        # If the list is in campaign mode, archive it
        archive_message = ""
        if list_to_remove.status == List.CAMPAIGN_MODE:
            list_to_remove.archived = True
            list_to_remove.campaign = None  # Clear the campaign field
            list_to_remove.save()
            archive_message = " and archived"

        # Log the removal event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN,
            verb=EventVerb.REMOVE,
            object=campaign,
            request=request,
            campaign_name=campaign.name,
            list_removed_id=str(list_to_remove.id),
            list_removed_name=list_name,
            list_owner=list_owner_username,
        )

        track("campaign_list_removed", campaign_id=str(campaign.id))

        # Show success message
        house_text = f" ({list_house})" if list_house else ""
        messages.success(
            request,
            f"{list_name}{house_text} has been removed from the campaign{archive_message}.",
        )

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # GET request - show confirmation page
    return render(
        request,
        "core/campaign/campaign_remove_list.html",
        {
            "campaign": campaign,
            "list": list_to_remove,
        },
    )
