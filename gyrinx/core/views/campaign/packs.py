"""Campaign pack management views."""

from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.auth import group_membership_required


@login_required
@group_membership_required(["Custom Content"])
def campaign_packs(request, id):
    """
    Manage content packs for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose packs are being managed.
    ``campaign_packs``
        Packs currently allowed in this campaign.
    ``available_packs``
        Packs that can be added (owned by user or listed).
    ``is_owner``
        Whether current user owns the campaign.

    **Template**

    :template:`core/campaign/campaign_packs.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    user = request.user

    campaign_packs_qs = campaign.packs.select_related("owner").order_by("name")

    available_packs = (
        CustomContentPack.objects.filter(
            models.Q(owner=user) | models.Q(listed=True),
            archived=False,
        )
        .exclude(id__in=campaign_packs_qs.values_list("id", flat=True))
        .select_related("owner")
        .order_by("name")
    )

    search_query = request.GET.get("q", "").strip()
    if search_query:
        available_packs = available_packs.filter(name__icontains=search_query)

    return render(
        request,
        "core/campaign/campaign_packs.html",
        {
            "campaign": campaign,
            "campaign_packs": campaign_packs_qs,
            "available_packs": available_packs,
            "is_owner": True,  # Only campaign owner can access this view
            "search_query": search_query,
        },
    )


@login_required
@group_membership_required(["Custom Content"])
def campaign_pack_add(request, id, pack_id):
    """Add a pack to the campaign's allowed packs."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(id,)))

    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    pack = get_object_or_404(CustomContentPack, id=pack_id, archived=False)

    if campaign.archived:
        messages.error(request, "Cannot modify packs for an archived Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    if not pack.listed and pack.owner != request.user:
        messages.error(request, "You don't have access to this pack.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    campaign.packs.add(pack)
    messages.success(request, f"Added {pack.name} to Campaign.")

    return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))


@login_required
@group_membership_required(["Custom Content"])
def campaign_pack_remove(request, id, pack_id):
    """Remove a pack from the campaign's allowed packs."""
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    pack = get_object_or_404(CustomContentPack, id=pack_id)

    if campaign.archived:
        messages.error(request, "Cannot modify packs for an archived Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    if request.method == "POST":
        campaign.packs.remove(pack)
        messages.success(request, f"Removed {pack.name} from Campaign.")
        return HttpResponseRedirect(reverse("core:campaign-packs", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_pack_remove.html",
        {
            "campaign": campaign,
            "pack": pack,
        },
    )
