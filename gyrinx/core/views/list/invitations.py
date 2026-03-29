"""List invitation views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.core.views.auth import group_membership_required
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def list_invitations(request, id):
    """
    Display invitations for a list.

    Shows all pending campaign invitations for a list that the user owns.

    **Context**

    ``list``
        The :model:`core.List` whose invitations are being displayed.
    ``invitations``
        Pending :model:`core.CampaignInvitation` objects.

    **Template**

    :template:`core/list/list_invitations.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Get pending invitations for this list
    from gyrinx.core.models.invitation import CampaignInvitation

    invitations = CampaignInvitation.objects.filter(
        list=lst, status=CampaignInvitation.PENDING
    ).select_related("campaign", "campaign__owner")

    return render(
        request,
        "core/list/list_invitations.html",
        {
            "list": lst,
            "invitations": invitations,
        },
    )


@login_required
@transaction.atomic
def accept_invitation(request, id, invitation_id):
    """
    Accept a campaign invitation.

    Allows a list owner to accept an invitation to join a campaign.

    **Context**

    ``list``
        The :model:`core.List` being invited.
    ``invitation``
        The :model:`core.CampaignInvitation` being accepted.

    **Template**

    None - redirects after processing.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    from gyrinx.core.models.invitation import CampaignInvitation

    invitation = get_object_or_404(
        CampaignInvitation,
        id=invitation_id,
        list=lst,
        status=CampaignInvitation.PENDING,
    )

    # Check if the campaign is completed
    if invitation.campaign.is_post_campaign:
        messages.error(
            request, "This campaign has ended. You cannot join a completed campaign."
        )
        return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))

    # Accept the invitation
    try:
        if invitation.accept():
            # Log the acceptance event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_INVITATION,
                verb=EventVerb.APPROVE,
                object=invitation,
                request=request,
                campaign_id=str(invitation.campaign.id),
                campaign_name=invitation.campaign.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="invitation_accepted",
            )

            messages.success(
                request, f"You have joined the campaign '{invitation.campaign.name}'."
            )

            # Redirect to pack setup if the campaign has packs the list doesn't
            suggested = lst.get_suggested_campaign_packs().filter(
                campaigns=invitation.campaign
            )
            if suggested.exists():
                return HttpResponseRedirect(
                    reverse(
                        "core:invitation-pack-setup",
                        args=(lst.id, invitation.campaign.id),
                    )
                )
        else:
            messages.error(request, "Unable to accept the invitation.")
    except ValueError as e:
        messages.error(request, str(e))

    return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))


@login_required
@group_membership_required(["Custom Content"])
def invitation_pack_setup(request, id, campaign_id):
    """Show campaign packs for subscription after accepting an invitation."""
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    from gyrinx.core.models.campaign import Campaign

    campaign = get_object_or_404(Campaign, id=campaign_id)

    # Verify this list is associated with this campaign (directly or as a clone source)
    in_campaign = (
        campaign.lists.filter(id=lst.id).exists()
        or campaign.lists.filter(original_list=lst).exists()
    )
    if not in_campaign:
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Compute suggestions from campaign packs directly — works even when the
    # list is only associated via a clone (in-progress campaigns).
    subscribed_ids = set(lst.packs.values_list("id", flat=True))
    suggested_packs = campaign.packs.exclude(id__in=subscribed_ids)

    if request.method == "POST":
        pack_ids = request.POST.getlist("pack_ids")
        if pack_ids:
            from gyrinx.core.models.pack import CustomContentPack

            packs_to_add = list(
                CustomContentPack.objects.filter(
                    id__in=pack_ids, archived=False
                ).filter(campaigns=campaign)
            )
            for pack in packs_to_add:
                lst.packs.add(pack)
            # For in-progress campaigns, the participant is a clone — add packs there too
            campaign_clone = campaign.lists.filter(original_list=lst).first()
            if campaign_clone:
                for pack in packs_to_add:
                    campaign_clone.packs.add(pack)
            if packs_to_add:
                pack_names = ", ".join(p.name for p in packs_to_add)
                messages.success(request, f"Subscribed to {pack_names}")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list/invitation_pack_setup.html",
        {
            "list": lst,
            "campaign": campaign,
            "suggested_packs": suggested_packs,
        },
    )


@login_required
@transaction.atomic
def decline_invitation(request, id, invitation_id):
    """
    Decline a campaign invitation.

    Allows a list owner to decline an invitation to join a campaign.

    **Context**

    ``list``
        The :model:`core.List` being invited.
    ``invitation``
        The :model:`core.CampaignInvitation` being declined.

    **Template**

    None - redirects after processing.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    from gyrinx.core.models.invitation import CampaignInvitation

    invitation = get_object_or_404(
        CampaignInvitation,
        id=invitation_id,
        list=lst,
        status=CampaignInvitation.PENDING,
    )

    # Decline the invitation
    if invitation.decline():
        # Log the decline event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_INVITATION,
            verb=EventVerb.REJECT,
            object=invitation,
            request=request,
            campaign_id=str(invitation.campaign.id),
            campaign_name=invitation.campaign.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="invitation_declined",
        )

        messages.info(
            request,
            f"You have declined the invitation to '{invitation.campaign.name}'.",
        )
    else:
        messages.error(request, "Unable to decline the invitation.")

    return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))
