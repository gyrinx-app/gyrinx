"""Campaign arbitrator (shared admin) management views."""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from gyrinx import messages
from gyrinx.core.forms.campaign import AddArbitratorForm
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.views.campaign.common import get_campaign_admin_or_404


@login_required
def campaign_arbitrators(request, id):
    """
    Manage the arbitrators (shared admins) of a campaign.

    Lists the current arbitrators, and lets any campaign admin grant another
    user admin rights by username or revoke an existing grant. The owner is
    always an arbitrator and cannot be removed.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being managed.
    ``admins``
        The current shared admins (excluding the owner), ordered by username.
    ``form``
        AddArbitratorForm for granting another user admin rights.

    **Template**

    :template:`core/campaign/campaign_arbitrators.html`
    """
    campaign = get_campaign_admin_or_404(request, id)

    if request.method == "POST":
        form = AddArbitratorForm(request.POST, campaign=campaign)
        if form.is_valid():
            new_admin = form.user_to_add
            # Granting admin is a trust-boundary change: the grant and its
            # audit record must land together.
            with transaction.atomic():
                campaign.admins.add(new_admin)
                CampaignAction.objects.create(
                    campaign=campaign,
                    user=request.user,
                    description=f"Arbitrator added: {new_admin.username}",
                    owner=request.user,
                )
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.ASSIGN,
                object=campaign,
                request=request,
                campaign_name=campaign.name,
                arbitrator_username=new_admin.username,
            )
            messages.success(request, f"{new_admin.username} is now an arbitrator.")
            return HttpResponseRedirect(
                reverse("core:campaign-arbitrators", args=(campaign.id,))
            )
    else:
        form = AddArbitratorForm(campaign=campaign)

    return render(
        request,
        "core/campaign/campaign_arbitrators.html",
        {
            "campaign": campaign,
            # The owner should never be in admins, but exclude defensively so
            # weird data can't render them twice or make them removable.
            "admins": campaign.admins.exclude(id=campaign.owner_id).order_by(
                "username"
            ),
            "form": form,
        },
    )


@login_required
@require_POST
def campaign_arbitrator_remove(request, id, user_id):
    """
    Revoke a user's arbitrator (shared admin) rights on a campaign.

    Any campaign admin may remove an arbitrator, including themselves. The
    owner is not in ``admins`` and so can never be removed.
    """
    campaign = get_campaign_admin_or_404(request, id)
    User = get_user_model()
    # Excluding the owner keeps them irremovable even if weird data ever put
    # them in the admins M2M.
    admin_to_remove = get_object_or_404(
        User.objects.exclude(id=campaign.owner_id),
        id=user_id,
        administered_campaigns=campaign,
    )
    removing_self = admin_to_remove == request.user

    with transaction.atomic():
        campaign.admins.remove(admin_to_remove)
        CampaignAction.objects.create(
            campaign=campaign,
            user=request.user,
            description=f"Arbitrator removed: {admin_to_remove.username}",
            owner=request.user,
        )
    log_event(
        user=request.user,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.UNASSIGN,
        object=campaign,
        request=request,
        campaign_name=campaign.name,
        arbitrator_username=admin_to_remove.username,
    )
    messages.success(request, f"{admin_to_remove.username} is no longer an arbitrator.")

    # Someone who just removed themselves can no longer see the manage page.
    if removing_self:
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    return HttpResponseRedirect(
        reverse("core:campaign-arbitrators", args=(campaign.id,))
    )
