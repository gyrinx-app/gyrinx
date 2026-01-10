"""List invitation views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
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
    else:
        messages.error(request, "Unable to accept the invitation.")

    return HttpResponseRedirect(reverse("core:list-invitations", args=(lst.id,)))


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
